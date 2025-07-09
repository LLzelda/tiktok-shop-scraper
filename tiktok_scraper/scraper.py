import asyncio, logging, os, random, time, json, datetime as dt
import sqlalchemy as sa
from playwright.async_api import async_playwright
from proxy import pool_from_env
from producer import KafkaWriter
from config import DB_URL, MAX_REQ_PER_MIN, SCROLL_PAGES, RANDOM_SLEEP_MIN, RANDOM_SLEEP_MAX
from models import ProductList, ProductDetail, ENGINE

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ITEM_DETAIL      = "https://www.tiktok.com/api/shop/item_detail/?item_id={product_id}"
GET_SHOP_DETAIL  = "https://www.tiktok.com/api/shop/get_shop_detail/?seller_id={seller_id}"

async def fetch_seller_seeds(limit=50):
    with ENGINE.begin() as cx:
        rows = cx.execute(sa.text("SELECT seller_id FROM seller_seed ORDER BY added_at DESC LIMIT :n"), {"n": limit})
        return [r[0] for r in rows]

async def upsert_latest(cx, row: dict):
    sql = sa.text("""
        INSERT INTO product_list (product_id, seller_id, shop_id, title, price_cents, currency, sold_count, inventory, rating)
        VALUES (:product_id,:seller_id,:shop_id,:title,:price_cents,:currency,:sold_count,:inventory,:rating)
        ON CONFLICT (product_id)
        DO UPDATE SET
          price_cents = EXCLUDED.price_cents,
          sold_count  = EXCLUDED.sold_count,
          inventory   = EXCLUDED.inventory,
          rating      = EXCLUDED.rating,
          updated_at  = now()
    """)
    cx.execute(sql, row)

async def insert_daily(cx, row: dict):
    sql = sa.text("""
        INSERT INTO product_detail (product_id, snapshot_date, seller_id, shop_id, title, price_cents, currency, sold_count, inventory, rating)
        VALUES (:product_id,:snapshot_date,:seller_id,:shop_id,:title,:price_cents,:currency,:sold_count,:inventory,:rating)
        ON CONFLICT (product_id, snapshot_date) DO NOTHING
    """)
    cx.execute(sql, row)

async def scrape_product(page, product_id, seller_id, shop_id, kafka):
    j = await (await page.request.get(ITEM_DETAIL.format(product_id=product_id))).json()
    basic = j.get("basicInfo", {})
    row = {
        "product_id": int(product_id),
        "seller_id": int(seller_id),
        "shop_id": int(shop_id) if shop_id else None,
        "title": basic.get("title"),
        "price_cents": int(float(basic.get("price", 0)) * 100),
        "currency": basic.get("currency", "USD"),
        "sold_count": basic.get("sales", 0),
        "inventory": basic.get("stock", 0),
        "rating": basic.get("rating", None),
        "snapshot_date": dt.date.today(),
    }

    # send to Kafka as well(optional for downstream stream consumers)
    await kafka.send(row)

    #write to DB
    with ENGINE.begin() as cx:
        await asyncio.get_event_loop().run_in_executor(None, upsert_latest, cx, row)
        await asyncio.get_event_loop().run_in_executor(None, insert_daily, cx, row)

async def crawl_seller(seller_id: int, kafka, proxy_pool):
    proxy = await proxy_pool.next()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True,
            proxy={"server": f"http://{proxy}"} if proxy else None,
            args=["--no-sandbox"])
        page = await browser.new_page()

        meta = await page.request.get(GET_SHOP_DETAIL.format(seller_id=seller_id))
        sj = await meta.json()
        shop_id = sj.get("shop_info", {}).get("shop_id") or None
        product_ids = sj.get("shop_info", {}).get("featured_product_ids", [])[:20]

        for pid in product_ids:
            await scrape_product(page, pid, seller_id, shop_id, kafka)
            await asyncio.sleep(random.uniform(RANDOM_SLEEP_MIN, RANDOM_SLEEP_MAX))

        await browser.close()

async def main():
    kafka = KafkaWriter("tiktok_raw")
    await kafka.start()

    proxy_pool = pool_from_env([])
    sellers = await fetch_seller_seeds()
    await asyncio.gather(*(crawl_seller(s, kafka, proxy_pool) for s in sellers))

    await kafka.stop()

if __name__ == "__main__":
    asyncio.run(main())