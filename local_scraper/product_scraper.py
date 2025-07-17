#!/usr/bin/env python3
"""
product_scraper.py
==================
Scrape TikTok Shop PDP JSON from a list of product links.

Usage
-----
python product_scraper.py \
       --links pdp_links.csv \
       --output products.jsonl \
       --concurrency 8 \
       --retry 2
"""
from __future__ import annotations
import argparse, asyncio, csv, json, random, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from playwright.async_api import async_playwright, Page, TimeoutError

PAGE_DATA_PATH = "/api/shop/pdp_desktop/page_data"
PRODUCT_RE     = re.compile(r'"product_module"')

###############################################################################
# helpers
def load_cookies() -> List[dict]:
    p = Path("cookies.txt")
    if not p.exists(): return []
    pairs = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [{"name": n, "value": v, "domain": ".tiktok.com", "path": "/"} for n, v in pairs]

def find_product_module(node: Any):
    if isinstance(node, dict):
        if "product_module" in node:
            return node["product_module"]
        for v in node.values():
            found = find_product_module(v)
            if found: return found
    elif isinstance(node, list):
        for item in node:
            found = find_product_module(item)
            if found: return found
    return None

###############################################################################
# core scraper
#######
async def scrape_one(url: str, page: Page, retries: int) -> dict | None:
    for attempt in range(retries + 1):
        try:
            await page.goto(url, timeout=12_000, wait_until="domcontentloaded")

            # 1) any JSON XHR whose body includes "product_module"
            try:
                resp = await page.wait_for_event(
                    "response",
                    predicate=lambda r:
                        r.headers.get("content-type", "").startswith("application/json"),
                    timeout=10_000,
                )
                txt = await resp.text()
                if '"product_module"' in txt:
                    data = json.loads(txt)
                    product = find_product_module(data)
                    if product:
                        break
            except TimeoutError:
                pass

            # 2) __UNIVERSAL_DATA__ (2025 rollout)
            try:
                await page.wait_for_function(
                    "() => window.__UNIVERSAL_DATA__ && "
                    "window.__UNIVERSAL_DATA__.productInfo && "
                    "window.__UNIVERSAL_DATA__.productInfo.product_module",
                    timeout=8_000,
                )
                product = await page.evaluate(
                    "window.__UNIVERSAL_DATA__.productInfo.product_module")
                break
            except TimeoutError:
                pass

            # 3) legacy __NEXT_DATA__
            await page.wait_for_function(
                "() => window.__NEXT_DATA__ && "
                "window.__NEXT_DATA__.props && "
                "window.__NEXT_DATA__.props.pageProps && "
                "window.__NEXT_DATA__.props.pageProps.productInfo && "
                "window.__NEXT_DATA__.props.pageProps.productInfo.product_module",
                timeout=8_000,
            )
            product = await page.evaluate(
                "window.__NEXT_DATA__.props.pageProps.productInfo.product_module")
            break

        except TimeoutError as e:
            if attempt < retries:
                await page.wait_for_timeout(random.randint(600, 1500))
                continue
            print(f"[WARN] {url} … {e}", file=sys.stderr)
            return None

    return {
        "product_id": product.get("id"),
        "url": url,
        "scrape_ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "product_module": product,
    }


###############################################################################
# worker pool
###############################################################################
async def worker(q: asyncio.Queue, out: Path, page_ctor, retries: int):
    page = await page_ctor()
    while not q.empty():
        url = await q.get()
        res = await scrape_one(url, page, retries)
        if res:
            out.write_text(json.dumps(res, ensure_ascii=False) + "\n", append=True)
        q.task_done()
    await page.close()

###############################################################################
# main
async def main(args):
    urls: list[str] = []
    with args.links.open(newline="", encoding="utf-8") as fh:
        sniff = fh.readline()
        fh.seek(0)
        if sniff.lower().startswith("http"):          # no header
            urls = [ln.strip() for ln in fh if ln.strip().startswith("http")]
        else:                                         # assume csv w/ header
            reader = csv.DictReader(fh)
            urls = [row[next(k for k in row if "url" in k.lower())].strip()
                    for row in reader if "url" in row and row["url"].startswith("http")]

    print(f"Loaded {len(urls):,} PDP URLs")

    cookies = load_cookies()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        if cookies: await ctx.add_cookies(cookies)

        out_path = args.output
        if out_path.exists(): out_path.unlink()
        out_path.touch()

        async def new_page():
            return await ctx.new_page()

        q: asyncio.Queue[str] = asyncio.Queue()
        for u in urls: q.put_nowait(u)

        workers = [worker(q, out_path, new_page, args.retry)
                   for _ in range(args.concurrency)]
        await asyncio.gather(*workers)

        await ctx.close(); await browser.close()
    print(f"✓  Scraped {out_path.stat().st_size/1024:.1f} KB → {out_path}")

###############################################################################
# CLI
###############################################################################
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", type=Path, default=Path("pdp_links.csv"))
    ap.add_argument("--output", type=Path, default=Path("products.jsonl"))
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--retry", type=int, default=1, help="retry per URL on fail")
    main_args = ap.parse_args()
    asyncio.run(main(main_args))
