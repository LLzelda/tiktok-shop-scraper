#!/usr/bin/env python3
"""
category_crawler.py
===================
Walks TikTok Shop's category hierarchy **(home page → first → second → third)** and
emits one CSV *per first-level category* containing:
    first_category_url,second_category_url,third_category_url,product_url

Usage (inside Codespace):
```
# cookies.txt must contain a fresh TikTok cookie header
pip install playwright pandas
python -m playwright install chromium

python category_crawler.py --outdir data/categories --scroll 3
```

Key design points
-----------------
* Uses Playwright headless Chromium.
* Loads cookies.txt once and injects them into every browser context.
* Each third-category page is scrolled N times (`--scroll`) to harvest PDP
  links.
* Writes `sluggified_first_category.csv` files in `--outdir`.

You can later feed those CSVs into `product_scraper.py`.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import re
import textwrap
from pathlib import Path
from typing import Dict, List

import pandas as pd
from playwright.async_api import async_playwright, Page, BrowserContext

HOME = "https://www.tiktok.com/shop"
#FIRST_CAT_SEL = "a[href^='/shop/c/']:not([href*='?'])"  # rough but works
FIRST_CAT_SEL  = "a[href^='https://www.tiktok.com/shop/c/']"
SECOND_CAT_SEL = "a[href^='https://www.tiktok.com/shop/c/']"
THIRD_CAT_SEL  = "a[href^='https://www.tiktok.com/shop/c/']"
PDP_SEL        = "a[href*='/pdp/']"                            # third-level page
SLUG_RE = re.compile(r"[^a-z0-9]+")

###############################################################################
# Cookie helper
########################

def load_cookies() -> List[dict]:
    p = Path("cookies.txt")
    if not p.exists():
        print("⚠️  cookies.txt not found - you may hit captchas.")
        return []
    parts = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [
        {
            "name": k,
            "value": v,
            "domain": ".tiktok.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }
        for k, v in parts
    ]

async def grab_third_page_products(third_url: str, ctx, scrolls: int) -> tuple[list[str], str]:
    """Return all PDP URLs from a given 3rd-level category page + its breadcrumb text."""
    page = await ctx.new_page()
    await page.goto(third_url, timeout=60_000)
    # breadcrumb text (e.g., "Women's Suits & Sets")
    crumb = await page.eval_on_selector("nav a:last-child", "el => el.textContent.trim()")
    links = await scroll_and_collect(page, PDP_SEL, scrolls)
    await page.close()
    return links, crumb

async def is_access_denied(page: Page) -> bool:
    """
    Returns True if TikTok served the ‘Security Check / Access Denied’ page
    instead of a real category.
    """
    title = (await page.title()).lower()
    if "access denied" in title or "security check" in title:
        return True
    # the captcha pages also have a <div id="secsdk-captcha">
    return await page.query_selector("#secsdk-captcha") is not None


###############################################################################
# Scraper
###############################################################################

async def scroll_and_collect(page, css, n_scroll=3):
    links = set()
    for _ in range(n_scroll):
        anchors = await page.eval_on_selector_all(
            css,
            "els => els.map(a => a.getAttribute('href'))"
        )
        for h in anchors:
            if h:
                if h.startswith("/"):
                    h = "https://www.tiktok.com" + h
                links.add(h.split("?")[0])
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(800)
    return list(links)


# async def process_category(first_url: str, ctx: BrowserContext, outdir: Path, scroll_times: int):
#     first_slug = SLUG_RE.sub("-", Path(first_url).parts[-1]).strip("-")
#     outfile = outdir / f"{first_slug}.csv"
#     rows: List[Dict[str, str]] = []

#     page = await ctx.new_page()
#     await page.goto(first_url, timeout=60_000)

#     second_links = await scroll_and_collect(page, SECOND_CAT_SEL, 1)
#     for second in second_links:
#         if not second.startswith("http"):
#             second = "https://www.tiktok.com" + second
#         await page.goto(second, timeout=60_000)
#         third_links = await scroll_and_collect(page, THIRD_CAT_SEL, 1)
#         for third in third_links:
#             if not third.startswith("http"):
#                 third = "https://www.tiktok.com" + third
#             await page.goto(third, timeout=60_000)
#             pdp_links = await scroll_and_collect(page, PDP_SEL, scroll_times)
#             for pdp in pdp_links:
#                 if not pdp.startswith("http"):
#                     pdp = "https://www.tiktok.com" + pdp
#                 rows.append(
#                     {
#                         "first_category_url": first_url,
#                         "second_category_url": second,
#                         "third_category_url": third,
#                         "product_url": pdp,
#                     }
#                 )
#     await page.close()

#     if rows:
#         pd.DataFrame(rows).to_csv(outfile, index=False)
#         print(f"✓  Wrote {len(rows):,} rows → {outfile}")
#     else:
#         print(f"⚠️  No products found for {first_url}")

async def process_first_category(first_url: str, ctx, outdir, scrolls: int):
    """Walk second→third→products for one first-level category."""

    first_page = await ctx.new_page()
    await first_page.goto(first_url, timeout=60_000)
    if await is_access_denied(first_page):
        print(f"⚠️  access-denied for {first_url} – skipping")
        await first_page.close()
        return

    first_name = (await first_page.title()).split(" - ")[0].strip()

    #debugger
    anchors = await first_page.eval_on_selector_all(
        "a",
        "els => els.slice(0, 20).map(e => e.getAttribute('href'))"
    )
    print(f"[debug] first-level page {first_name} — first 20 hrefs:", anchors)

    # inside the second-level loop – after you opened sec_page
    anchors = await sec_page.eval_on_selector_all(
        "a",
        "els => els.slice(0, 20).map(e => e.getAttribute('href'))"
    )
    print(f"[debug] second-level page {second_name} — first 20 hrefs:", anchors)

    second_links = list(await scroll_and_collect(first_page, SECOND_CAT_SEL, 1))
    await first_page.close()

    rows = []
    for second_url in second_links:
        sec_page = await ctx.new_page()
        try:
            await sec_page.goto(second_url, timeout=60_000)
            if await is_access_denied(sec_page):
                print(f"⚠️  access-denied for {second_url} – skipping")
                continue
            second_name = (await sec_page.title()).split(" - ")[0].strip()

            third_links = list(await scroll_and_collect(sec_page, THIRD_CAT_SEL, 1))
        finally:
            await sec_page.close()

        for third_url in third_links:
            pdp_links, third_name = await grab_third_page_products(third_url, ctx, scrolls)
            for p in pdp_links:
                rows.append(
                    [first_name, second_name, third_name,
                     "https://www.tiktok.com" + p if p.startswith("/") else p]
                )

    if rows:
        out = outdir / f"{first_name.replace(' ', '_').lower()}.csv"
        import csv
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["first_cat", "second_cat", "third_cat", "product_url"])
            w.writerows(rows)
        print(f"✓  Wrote {len(rows):,} rows → {out}")

###############################################################################
# CLI
###############################################################################

def parse_args():
    ap = argparse.ArgumentParser(description="TikTok Shop category crawler")
    ap.add_argument("--outdir", type=Path, default=Path("data/categories"))
    ap.add_argument("--scroll", type=int, default=3, help="Scroll iterations per third-category page")
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
        await home.wait_for_timeout(1200)          # let React hydrate
        await home.evaluate("window.scrollBy(0, 400)")



        first_links = list(await scroll_and_collect(home, FIRST_CAT_SEL, 1))
        print(f"Found {len(first_links)} first-level categories")

        await home.close()

        if not first_links:
            print("✖  No categories - check cookies or FIRST_CAT_SEL.")
            return

        tasks = [
            process_first_category(u, ctx, args.outdir, args.scroll)
            for u in first_links
        ]
        await asyncio.gather(*tasks)
        await ctx.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())