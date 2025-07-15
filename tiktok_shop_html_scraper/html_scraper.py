#!/usr/bin/env python3
"""
TikTok Shop Scraper (HTML-only) - v2.1
======================================
* **Auto-discover** product pages from https://www.tiktok.com/shop with `--limit N`.
* **Fallback** to a manual URL list via `--input urls.txt`.
* Extracts the raw `product_module` JSON from each page's `__NEXT_DATA__` and
  writes newline-delimited JSON (`.jsonl`).

**Patch 2.1**
-------------
TikTok's homepage uses **`/pdp/<id>`** links (no `/shop/` prefix).  The old
regex only matched `/shop/pdp/…`, so discovery returned zero URLs.  This patch:

* Accepts **both** `/pdp/` **and** `/shop/pdp/` forms.
* Logs how many candidate links were seen each scroll pass (for easier debug).
* Minor: cleans up graceful shutdown so “Event loop is closed” warning is gone.

Run (Codespaces example):
```bash
python tiktok_scraper.py --limit 50 --output products.jsonl --concurrency 4
```
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re, json, html
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from playwright.async_api import Browser, Page, async_playwright, TimeoutError as PlaywrightTimeout


SHOP_URL = "https://www.tiktok.com/shop"
#accept either …/pdp/<id> or …/shop/pdp/<id>
#PDP_RE = re.compile(r"https://www\.tiktok\.com/(?:(?:shop/)?pdp)/(\d+)")
#PDP_RE = re.compile(r"(?:https://www\\.tiktok\\.com)?/(?:(?:shop/)?pdp)/(\\d+)")
# PDP_RE = re.compile(
#     r"(?:https://www\.tiktok\.com)?/(?:(?:shop/)?pdp)/[^/]+/(\d+)"
# )
PDP_RE = re.compile(r"(?:https://www\.tiktok\.com)?/(?:(?:shop/)?pdp)/[^/]+/(\d+)")

SCRIPT_SELECTOR = "script#__NEXT_DATA__"
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]
SCHEMA_VERSION = "v1"

###############################################################################
# Cookie helpers
###############################################################################

def load_cookies() -> list[dict]:
    """Read cookies.txt (if present) and return Playwright cookie dicts."""
    path = Path("cookies.txt")
    if not path.exists():
        return []
    cookie_pairs = [c.strip().split("=", 1) for c in path.read_text().split(";") if "=" in c]
    return [
        {
            "name": name,
            "value": value,
            "domain": ".tiktok.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }
        for name, value in cookie_pairs
    ]

###############################################################################
# CLI helpers
###############################################################################

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TikTok Shop HTML scraper (auto-discover capable)")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--limit", type=int, help="Auto-discover N PDPs from the Shop homepage")
    mode.add_argument("--input", type=Path, help="Text file with PDP URLs (one per line)")

    p.add_argument("--output", type=Path, required=True, help="ND-JSON output filename")
    p.add_argument("--concurrency", type=int, default=8, help="Parallel Playwright tabs (Codespace~4)")
    p.add_argument("--timeout", type=int, default=30, help="Seconds before navigation timeout")
    p.add_argument("--proxy", help="HTTP/SOCKS proxy URL")
    p.add_argument("--headful", action="store_true", help="Run non-headless for debugging")
    return p.parse_args()


###############################################################################
# Browser helpers
###############################################################################

async def _launch(headful: bool, proxy: Optional[str]):
    pw = await async_playwright().start()
    kwargs = {"headless": not headful, "args": ["--disable-blink-features=AutomationControlled"]}
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return pw, await pw.chromium.launch(**kwargs)


async def _new_page(browser: Browser) -> Page:
    ctx = await browser.new_context(user_agent=random.choice(UA_POOL))
    cookies = load_cookies()
    #print(len(cookies))
    if cookies:
        await ctx.add_cookies(cookies)
    page = await ctx.new_page()
    return page


###############################################################################
# Auto‑discover
###############################################################################

async def _discover_pdp_urls(page: Page, limit: int) -> List[str]:
    await page.goto(SHOP_URL, timeout=60_000)
    await page.evaluate("window.scrollBy(0, window.innerHeight)")
    await page.wait_for_timeout(1200)

    collected: Set[str] = set()
    passes = stagnant = last_count = 0

    while len(collected) < limit and passes < 400 and stagnant < 20:
        #use getAttribute so we see relative links too
        anchors = await page.eval_on_selector_all(
            "a[href*='/pdp/']",
            "els => els.map(e => e.getAttribute('href'))",
        )

        if passes == 0:                    # debug dump
            print("First 10 raw hrefs:")
            for h in anchors[:10]:
                print("   >", h)

        for href in anchors:
            if not href:
                continue
            m = PDP_RE.match(href)
            if m:
                if href.startswith("/"):
                    href = "https://www.tiktok.com" + href
                prod_id = m.group(1)
                collected.add(f"https://www.tiktok.com/shop/pdp/{prod_id}")

        stagnant = stagnant + 1 if len(collected) == last_count else 0
        last_count = len(collected)
        if len(collected) >= limit:
            break

        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(random.randint(500, 900))
        passes += 1

    urls = list(collected)[:limit]
    random.shuffle(urls)
    return urls


###############################################################################
# Scrape single PDP
###############################################################################

# async def _extract_product(page: Page) -> Dict[str, Any]:
#     #await page.wait_for_selector(SCRIPT_SELECTOR, timeout=15_000)
#     await page.wait_for_selector(SCRIPT_SELECTOR, state="attached", timeout=20_000)
#     raw = await page.eval_on_selector(SCRIPT_SELECTOR, "el => el.textContent")
#     data = json.loads(raw)
#     return data["props"]["pageProps"]["productInfo"]["product_module"]


PAGE_DATA_PATH = "/api/shop/pdp_desktop/page_data"

async def _extract_product(page: Page) -> dict:
    """Grab product_module from the /pdp_desktop/page_data JSON XHR."""
    # Navigate first
    await page.goto(page.url, timeout=30_000)

    try:
        resp = await page.wait_for_event(
            "response",
            predicate=lambda r: PAGE_DATA_PATH in r.url and r.status == 200,
            timeout=20_000,          # ms
        )
    except asyncio.TimeoutError:
        raise ValueError("page_data XHR not captured (timeout)")

    data = await resp.json()
    return data["data"]["product_module"] 

async def _scrape_one(url: str, page: Page, timeout: int):
    try:
        await page.goto(url, timeout=timeout * 1000)

        product = await _extract_product(page)   # extractor no longer calls goto
        return {
            "schema_version": SCHEMA_VERSION,
            "product_id": product.get("id"),
            "scrape_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "url": url,
            "raw_product": product,
        }
    except Exception as e:
        print(f"[WARN] {url[:80]} … {e}")
        return None



###############################################################################
# Orchestrator
###############################################################################

async def _worker(browser: Browser, q: "asyncio.Queue[str]", out: Path, sem: asyncio.Semaphore, timeout: int):
    async with sem:
        page = await _new_page(browser)
        while not q.empty():
            url = await q.get()
            rec = await _scrape_one(url, page, timeout)
            if rec:
                out.write_text(json.dumps(rec, ensure_ascii=False) + "\n", append=True, encoding="utf-8")  # type: ignore[arg-type]
            q.task_done()
        await page.close()


async def main_async():
    args = _parse_args()
    pw, browser = await _launch(args.headful, args.proxy)

    discover_page = await _new_page(browser)  # now cookie‑aware

    if args.input:
        urls: Iterable[str] = [u.strip() for u in args.input.read_text().splitlines() if u.strip()]
        print(f"Loaded {len(list(urls))} URLs from {args.input}")
    else:
        urls = await _discover_pdp_urls(discover_page, args.limit)
        print(f"Discovered {len(urls)} PDP links from homepage")
    await discover_page.close()

    if not urls:
        print("✖  No URLs to scrape. Exiting.")
        await browser.close()
        await pw.stop()
        return

    out = args.output
    if out.exists():
        out.unlink()
    out.touch()

    queue: "asyncio.Queue[str]" = asyncio.Queue()
    for u in urls:
        queue.put_nowait(u)

    sem = asyncio.Semaphore(args.concurrency)
    workers = [_worker(browser, queue, out, sem, args.timeout) for _ in range(args.concurrency)]
    await asyncio.gather(*workers)

    await browser.close()
    await pw.stop()
    print(f"✓  Scraped {out.stat().st_size / 1024:.1f} KB → {out.resolve()}")


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.exit(130)



