# probe_shop_page.py
import asyncio, json, textwrap, re
from pathlib import Path
from playwright.async_api import async_playwright

SHOP_URL = "https://www.tiktok.com/shop"
PDP_RE   = re.compile(r"/pdp/")

def load_cookies():
    p = Path("cookies.txt")
    if not p.exists():
        return []
    pairs = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [
        {"name": n, "value": v, "domain": ".tiktok.com", "path": "/",
         "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for n, v in pairs
    ]

async def main():
    cookies = load_cookies()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        if cookies:
            await ctx.add_cookies(cookies)
        page = await ctx.new_page()
        await page.goto(SHOP_URL, timeout=60000)
        html = await page.content()
        hrefs = await page.eval_on_selector_all(
            "a[href*='/pdp/']",
            "els => els.map(e => e.getAttribute('href'))"
        )
        print("Loaded shop page ✱")
        print("  cookies sent:", len(cookies))
        print("  anchors found:", len(hrefs))
        # show the first few hrefs (may be None)
        for h in hrefs[:5]:
            print("   >", h)
        await browser.close()

asyncio.run(main())
