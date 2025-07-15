import asyncio, textwrap, json
from pathlib import Path
from playwright.async_api import async_playwright
SHOP_URL = "https://www.tiktok.com/shop"

def load_cookies():
    p = Path("cookies.txt")
    if not p.exists(): return []
    pairs = [c.strip().split("=", 1) for c in p.read_text().split(";") if "=" in c]
    return [{"name": n, "value": v, "domain": ".tiktok.com", "path": "/"} for n, v in pairs]

async def main():
    cookies = load_cookies()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        if cookies: await ctx.add_cookies(cookies)
        page = await ctx.new_page()
        await page.goto(SHOP_URL, timeout=60000)
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(1500)

        # Grab the first 40 link elements’ outerHTML
        links = await page.eval_on_selector_all(
            "a",
            "els => els.slice(0, 40).map(e => e.outerHTML)"
        )
        for i, outer in enumerate(links, 1):
            print(f'[{i:02}]', textwrap.shorten(outer, 120))
        await b.close()

asyncio.run(main())
