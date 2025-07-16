"""
category_crawler.py  •  v1.1
============================
Crawls TikTok Shop **category hierarchy** and writes one CSV **per first‑level
category** that contains:

    first_url,second_url,third_url,product_url

* We click the *Categories* row on the homepage → collect first‑level links.
* For each first-level link → collect **second-level** links.
* For each second-level link → collect **third-level** links.
* For each third-level link → scroll N times and harvest every PDP link.

Only product links discovered on **third-level pages** are saved.

Run
----
```bash
pip install playwright pandas
python -m playwright install chromium

python category_crawler.py --outdir data/categories --scroll 3 --concurrency 4
```

You need a fresh `cookies.txt` in the script directory (whole `cookie` header
from a logged-in browser) so TikTok serves the real pages.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import random
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd
from playwright.async_api import async_playwright, BrowserContext, Page

HOME = "https://www.tiktok.com/shop"
FIRST_SEL  = "a[href^='https://www.tiktok.com/shop/c/'][data-id]"
SECOND_SEL = "a[href^='https://www.tiktok.com/shop/c/'][data-id]"
THIRD_SEL  = "a[href^='https://www.tiktok.com/shop/c/'][data-id]"
PDP_SEL    = "a[href*='/pdp/']"
SLUG_RE    = re.compile(r"[^a-z0-9]+")

###############################################################################
# Helpers
###############################################################################

def load_cookies() -> List[dict]:
    p = Path("cookies.txt")
    if not p.exists():
        return []
    pairs = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [
        {"name": k, "value": v, "domain": ".tiktok.com", "path": "/", "secure": True}
        for k, v in pairs
    ]

async def scroll_and_collect(page: Page, selector: str, scrolls: int) -> List[str]:
    links: Set[str] = set()
    for _ in range(scrolls):
        anchors = await page.eval_on_selector_all(selector, "els => els.map(e => e.getAttribute('href'))")
        for h in anchors:
            if h:
                links.add(h)
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(random.randint(600, 900))
    return sorted(links)

###############################################################################
# Core crawler
###############################################################################

async def crawl_first(first_url: str, ctx: BrowserContext, outdir: Path, scroll: int):
    first_slug = SLUG_RE.sub("-", Path(first_url).parts[-1]).strip("-")
    outfile = outdir / f"{first_slug}.csv"
    rows: List[Dict[str, str]] = []

    page = await ctx.new_page()
    await page.goto(first_url, timeout=60_000)
    second_links = await scroll_and_collect(page, SECOND_SEL, 1)

    for second in second_links:
        if not second.startswith("http"):
            second = "https://www.tiktok.com" + second
        await page.goto(second, timeout=60_000)
        third_links = await scroll_and_collect(page, THIRD_SEL, 1)

        # If page already shows PDP cards (no deeper sub‑cats), treat current as third
        if not third_links:
            third_links = [second]

        for third in third_links:
            if not third.startswith("http"):
                third = "https://www.tiktok.com" + third
            await page.goto(third, timeout=60_000)
            pdp_links = await scroll_and_collect(page, PDP_SEL, scroll)
            for pdp in pdp_links:
                if not pdp.startswith("http"):
                    pdp = "https://www.tiktok.com" + pdp
                rows.append({
                    "first_url": first_url,
                    "second_url": second,
                    "third_url": third,
                    "product_url": pdp,
                })
    await page.close()

    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(outfile, index=False)
        print(f"✓  {outfile.name}: {len(rows):,} product links")
    else:
        print(f"⚠️  No products found for {first_url}")

###############################################################################
# CLI + entry
###############################################################################

def parse_args():
    ap = argparse.ArgumentParser(description="TikTok Shop category crawler (third‑level)")
    ap.add_argument("--outdir", type=Path, default=Path("data/categories"))
    ap.add_argument("--scroll", type=int, default=3, help="Scroll repeats on third‑level pages")
    ap.add_argument("--concurrency", type=int, default=4)
    return ap.parse_args()

async def main():
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookies()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        if cookies:
            await ctx.add_cookies(cookies)

        home = await ctx.new_page()
        await home.goto(HOME, timeout=60_000)
        await home.wait_for_timeout(1200)
        await home.evaluate("window.scrollBy(0, 400)")
        first_links = await scroll_and_collect(home, FIRST_SEL, 1)
        print(f"Found {len(first_links)} first-level categories")
        await home.close()

        if not first_links:
            print("✖  No categories detected – selector may need update.")
            await ctx.close(); await browser.close(); return

        sem = asyncio.Semaphore(args.concurrency)
        tasks = []
        for first in first_links:
            if not first.startswith("http"):
                first = "https://www.tiktok.com" + first
            tasks.append(crawl_first(first, ctx, args.outdir, args.scroll))
        await asyncio.gather(*tasks)
        await ctx.close(); await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
