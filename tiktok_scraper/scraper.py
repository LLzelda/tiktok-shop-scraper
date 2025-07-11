import os, asyncio, json, logging, random, time
from datetime import datetime, date
from typing import List

import sqlalchemy as sa
from playwright.async_api import async_playwright, Response, Error as PwError, TimeoutError as PwTimeout

from .proxy import pool_from_env, ProxyPool
from .producer import KafkaWriter
from etl.models import ENGINE, ProductList, ProductDetail
#from .signer import sign_url

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

DB_RETRIES = 10

from contextlib import asynccontextmanager

@asynccontextmanager
async def seller_session(playwright, proxy):
    browser = await playwright.chromium.launch(headless=True, **proxy)
    ctx     = await browser.new_context()
    page    = await ctx.new_page()
    try:
        # small page to set cookies & JS bundle
        await page.goto("https://www.tiktok.com/about", wait_until="domcontentloaded")
        yield page
    finally:
        await browser.close()

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ------------------------------------------------------------
def wait_engine(max_wait: int = 30) -> sa.Engine:
    """Block until Postgres is reachable (container-start race)."""
    for _ in range(DB_RETRIES):
        try:
            with ENGINE.connect():
                return ENGINE
        except sa.exc.OperationalError as e:
            logger.info("DB not ready: %s – retrying…", e.args[0].split("\n")[0])
            time.sleep(3)
    raise RuntimeError("Postgres never became ready")

async def fetch_json(page, url: str, *, retries: int = 3, wait: int = 3) -> dict:
    """GET → JSON with retries, bans CAPTCHA/HTML bodies."""
    for i in range(retries):
        try:
            resp: Response = await page.request.get(url, timeout=15_000)
            if resp.ok:
                try:
                    return await resp.json()
                except Exception:
                    text = await resp.text()
                    logger.warning("Bad JSON (%s chars) on %s", len(text), url)
            else:
                logger.warning("HTTP %s on %s", resp.status, url)
        except PwError as e:
            logger.warning("Playwright error %s on %s", e, url)
        await asyncio.sleep(wait)
    raise RuntimeError(f"Failed to fetch JSON after {retries} attempts: {url}")

# endpoint that works for ALL sellers (even FBT)
SELLER_ITEMS = (
    "https://www.tiktok.com/api/shop/seller_product_list/"
    "?seller_id={seller_id}&count=100&cursor={cursor}"
)
async def signed_fetch(page, url: str) -> dict:

    return await page.evaluate(
        """async u => {
               const r = await fetch(u, {credentials: 'include'});
               if (!r.ok) throw new Error('HTTP ' + r.status);
               return await r.json();
        }""",
        url
    )
# ──────────────────────────────────────────────────────────────────────────────
# Core crawler
# ──────────────────────────────────────────────────────────────────────────────
# no sign..
async def crawl_seller(seller_id: int, kafka: KafkaWriter, pool: ProxyPool):
    proxy = await pool.next()
    pw_kwargs = {"proxy": {"server": f"http://{proxy}"}} if proxy else {}

    playwright = await async_playwright().start()
    browser    = await playwright.chromium.launch(headless=True, **pw_kwargs)
    context    = await browser.new_context()
    page       = await context.new_page()

    try:
        # hit a trivial page once to set msToken cookie
        await page.goto("https://www.tiktok.com/about", wait_until="domcontentloaded")

        async def trigger_catalog(cur: int):
            await page.evaluate(
                """async ({sid, cur}) => {
                       const url = `/api/shop/seller_product_list/?seller_id=${sid}&count=100&cursor=${cur}`;
                       await fetch(url, {credentials:'include'});
                }""",
                {"sid": seller_id, "cur": cur}
            )

        def is_catalog(resp):
            u = resp.url
            return "seller_product_list" in u and f"seller_id={seller_id}" in u

        cursor   = 0
        batch_no = 0

        while True:
            # ▼ wait up to 60 s, log all outgoing URLs
            try:
                page.on("request", lambda req: 
                        req.url.endswith("seller_product_list") and logger.debug("REQ %s", req.url))
                async with page.expect_response(is_catalog, timeout=60_000) as wait:
                    await trigger_catalog(cursor)
                resp = await wait.value
            # except PwTimeout:
            #     logger.warning("seller %s - catalogue timeout, rotating proxy", seller_id)
            #     await pool.ban(proxy)
            #     return
            #brutallllll
            except PwTimeout:
                logger.warning("seller %s - catalogue timeout, rotating proxy", seller_id)
                await pool.ban(proxy)
                proxy = await pool.next()
                await context.close()
                context = await browser.new_context(proxy={"server": f"http://{proxy}"} if proxy else None)
                page    = await context.new_page()
                await page.goto("https://www.tiktok.com/about", wait_until="domcontentloaded")
                continue
                              # retry with the new proxy
            j = await resp.json()
            print(j)

            # soft-ban guard
            if "data" not in j or "products" not in j["data"]:
                logger.warning("seller %s - missing data key, rotating proxy", seller_id)
                await pool.ban(proxy)
                return

            items = j["data"]["products"]
            if not items:
                break

            now      = datetime.utcnow()
            batch_no += 1

            # ── push to Kafka
            await kafka.send_many([
                {
                    "product_id":  it["product_id"],
                    "seller_id":   seller_id,
                    "price":       it["price"],
                    "currency":    it.get("currency", "USD"),
                    "snapshot_ts": now.isoformat()
                }
                for it in items
            ])

            # ── upsert DB
            with ENGINE.begin() as cx:
                for it in items:
                    price_cents = int(float(it["price"]) * 100)
                    cx.execute(sa.insert(ProductList).values(
                        product_id   = it["product_id"],
                        seller_id    = seller_id,
                        price_cents  = price_cents,
                        currency     = it.get("currency", "USD"),
                        updated_at   = now
                    ).on_conflict_do_update(
                        index_elements=[ProductList.product_id],
                        set_={
                            "price_cents": price_cents,
                            "currency":    it.get("currency", "USD"),
                            "updated_at":  now
                        }
                    ))
                    cx.execute(sa.insert(ProductDetail).values(
                        product_id   = it["product_id"],
                        seller_id    = seller_id,
                        snap_date    = date.today(),
                        price_cents  = price_cents,
                        currency     = it.get("currency", "USD"),
                        stock        = None
                    ).on_conflict_do_nothing())

            if not j["data"].get("has_more"):
                break
            cursor = j["data"]["cursor"]
            await asyncio.sleep(random.uniform(2, 4))

        logger.info("seller %s done - %d batch(es)", seller_id, batch_no)

    finally:
        await browser.close()
        await playwright.stop()

# ──────────────────────────────────────────────────────────────────────────────
# Seed fetch
# ──────────────────────────────────────────────────────────────────────────────
async def fetch_seller_seeds(limit: int = 5) -> List[int]:
    eng = wait_engine()
    with eng.begin() as cx:
        rows = cx.execute(
            sa.text("SELECT seller_id FROM seller_seed ORDER BY added_at DESC LIMIT :n"),
            {"n": limit}
        )
        return [r[0] for r in rows]

# ──────────────────────────────────────────────────────────────────────────────
# Main entry
# ──────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    kafka = KafkaWriter(os.getenv("KAFKA_TOPIC", "tiktok_raw"))
    await kafka.start()

    try:
        proxy_pool = pool_from_env(os.getenv("PROXY_POOL", "").split(","))
        sellers = await fetch_seller_seeds()
        if not sellers:
            logger.warning("No seller_seed rows – nothing to crawl.")
            return

        await asyncio.gather(*(crawl_seller(s, kafka, proxy_pool) for s in sellers))
    finally:
        await kafka.stop()


if __name__ == "__main__":
    asyncio.run(main())
