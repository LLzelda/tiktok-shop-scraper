import asyncio, json, logging, re, os, sys
from playwright.async_api import async_playwright
from .config import SHOP_BATCH_SIZE
from .proxy import pool_from_env, PROXY_POOL
#from .proxy import pool_from_env 
from .producer import KafkaWriter
import sqlalchemy as sa, pandas as pd
from .config import POSTGRES_DSN

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scraper")

ITEM_RX = re.compile(r"/api/shop/item_list")
REVIEW_RX = re.compile(r"/api/review/list")



async def fetch_shops(limit=SHOP_BATCH_SIZE):
    engine = sa.create_engine(POSTGRES_DSN)
    with engine.begin() as cx:
        rows = cx.execute(sa.text("SELECT shop_id FROM shop_seed ORDER BY added_at DESC LIMIT :n"), {"n": limit})
        return [str(r[0]) for r in rows]



async def scrape_shop(shop_id: str, proxy: str | None):
    TARGET = f"https://www.tiktok.com/@{shop_id}/shop" if shop_id.isdigit() else shop_id
    products = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy} if proxy else None,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await ctx.new_page()

        async def handle_response(resp):
            url = resp.url
            if ITEM_RX.search(url) or REVIEW_RX.search(url):
                try:
                    body = await resp.json()
                    products.append({"url": url, "data": body})
                except Exception:
                    log.exception("Decode fail for %s", url)
        page.on("response", handle_response)

        await page.goto(TARGET, timeout=0)
        for _ in range(10):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(2)
        await browser.close()
    return products

async def main():
    shops = await fetch_shops()
    if not shops:
        log.warning("No shop IDs seeded. Add via scripts/seed_shops.py")
        return

    tasks = []
    proxy_pool = pool_from_env(PROXY_POOL)
    async with KafkaWriter() as kw:
        for shop_id in shops:
            proxy = await proxy_pool.next()
            tasks.append(scrape_shop(shop_id, proxy))

        for coro in asyncio.as_completed(tasks):
            try:
                batch = await coro
                for rec in batch:
                    await kw.send(rec)
            except Exception:
                log.exception("Scrape task failed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit()