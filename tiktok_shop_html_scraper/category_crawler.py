#!/usr/bin/env python3
"""
category_crawler.py  (v3)
Crawls TikTok Shop starting from the public site-map page:
    sitemap  ➜  second-level pages  ➜  third-level pages  ➜  PDP links
Writes one CSV per second-level category.
"""
from __future__ import annotations
import argparse, asyncio, csv, re
from pathlib import Path
from typing import List
from playwright.async_api import async_playwright, Page

# ── constants ───────────────────────────────────────────────────────────────
SITEMAP_URL    = "https://www.tiktok.com/shop/c?source=ecommerce_category"
SEC_CAT_SEL    = "a[href^='https://www.tiktok.com/shop/c/']"
THIRD_CAT_SEL  = "a[href^='https://www.tiktok.com/shop/c/']"
# SEC_CAT_SEL = "a[data-id][href*='/shop/c/']"
THIRD_CAT_SEL  = "a[data-id][href*='/shop/c/']"
PDP_SEL        = "a[href*='/pdp/']"
SLUG_RE        = re.compile(r"[^a-z0-9]+")

# ── cookie helper 
def load_cookies() -> List[dict]:
    p = Path("cookies.txt")
    if not p.exists(): return []
    pairs = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [{"name": n, "value": v, "domain": ".tiktok.com", "path": "/"} for n, v in pairs]

# ── scrolling collector ────────────────────────────────────────────────────
async def scroll_and_collect(page: Page, css: str, n_scroll: int = 2) -> list[str]:
    links = set()
    for _ in range(n_scroll + 1):        # initial + n_scroll
        anchors = await page.eval_on_selector_all(
            css, "els => els.map(e => e.getAttribute('href'))"
        )
        for h in anchors:
            if not h:
                continue
            if h.startswith("/"):
                h = "https://www.tiktok.com" + h
            links.add(h.split("?")[0])
        # do extra scroll only if we still need more
        if _ < n_scroll:
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)
    return list(links)

async def is_denied(page: Page) -> bool:
    title = (await page.title()).lower()
    if "access denied" in title or "security check" in title:
        return True
    return await page.query_selector("#secsdk-captcha") is not None

# ── processor for each second-level category ────────────────────────────────
async def process_second(sec_url: str, ctx, outdir: Path, scrolls: int):
    sec_page = await ctx.new_page()
    try:
        await sec_page.goto(sec_url, timeout=60_000)
        if await is_denied(sec_page):
            print(f"⚠️  captcha on second-level page – skipped: {sec_url}")
            return

        sec_name = (await sec_page.title()).split(" - ")[0].strip()

        # Wait until at least one third-level anchor appears
        try:
            await sec_page.wait_for_selector(THIRD_CAT_SEL, timeout=5000)
        except:
            print(f"⚠️  no third categories visible on {sec_name} – skipped")
            return

        third_links = await scroll_and_collect(sec_page, THIRD_CAT_SEL, 1)

    finally:
        await sec_page.close()

    rows = []
    for third in third_links:
        t_page = await ctx.new_page()
        try:
            await t_page.goto(third, timeout=60_000)
            if await is_denied(t_page):
                print(f"⚠️  captcha on third-level page – skipped: {third}")
                continue

            third_name = (await t_page.title()).split(" - ")[0].strip()
            pdps = await scroll_and_collect(t_page, PDP_SEL, scrolls)
            if not pdps:
                print(f"⚠️  no PDP links in {third_name}")
                continue

            for p in pdps:
                rows.append([sec_url, third_name, p])
        finally:
            await t_page.close()

    if rows:
        slug = SLUG_RE.sub("-", sec_name.lower()).strip("-")
        out = outdir / f"{slug}.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([["second_cat_url", "third_cat_name", "product_url"]] + rows)
        print(f"✓  {sec_name:40} » {len(rows):,} products")

# ── main ────────────────────────────────────────────────────────────────────
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=Path("data/categories"))
    ap.add_argument("--scroll", type=int, default=3, help="scrolls per third page")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookies()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        if cookies: await ctx.add_cookies(cookies)

        site = await ctx.new_page()
        await site.goto(SITEMAP_URL, timeout=60_000)
        sec_links = await scroll_and_collect(site, SEC_CAT_SEL, 0)
        print(f"Found {len(sec_links)} second-level categories in sitemap")
        await site.close()

        sem = asyncio.Semaphore(args.concurrency)
        tasks = []
        for url in sec_links:
            if not url.startswith("http"):
                url = "https://www.tiktok.com" + url
            tasks.append(process_second(url, ctx, args.outdir, args.scroll))
        await asyncio.gather(*tasks)

        await ctx.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
