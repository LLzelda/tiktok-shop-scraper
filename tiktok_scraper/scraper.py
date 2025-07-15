import os, asyncio, json, logging, random, time, re, html as html_lib
from datetime import datetime, date
from pathlib import Path
from typing import List

import sqlalchemy as sa
from playwright.async_api import async_playwright, TimeoutError as PwTimeout

from .proxy import pool_from_env, ProxyPool
from .producer import KafkaWriter
from etl.models import ENGINE, ProductList, ProductDetail

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ──── Cookie helpers 
SAMESITE_MAP = {
    "unspecified": "Lax",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}
def chrome_to_playwright(raw: list[dict]) -> list[dict]:
    fixed = []
    for c in raw:
        c["domain"] = ".tiktok.com" ## force correct scope
        if c.get("expiry"):
            c["expires"] = int(c.pop("expiry"))
        ss = c.get("sameSite")
        if ss:
            c["sameSite"] = SAMESITE_MAP.get(ss.lower(), "Lax")
        for k in ("hostOnly", "creation", "lastAccessed", "priority",
                  "sameParty", "sourceScheme", "sourcePort", "session"):
            c.pop(k, None)
        fixed.append(c)
    return fixed

#PDP HTML JSON extractor
SCRIPT_RX_JSON = re.compile(
    r'<script[^>]+type=["\']application/json["\'][^>]*>(\{.*?})</script>',
    re.S,
)
SCRIPT_RX_JS = re.compile(
    r'<script[^>]*>(?:[^<{]|<(?!/script))*?\b(_SSR_DATA_|__NEXT_DATA__)\b[^<]*?=\s*({.*?})\s*;?\s*</script>',
    re.S,
)

def extract_pdp_json(page_html: str) -> dict | None:
    """
    1. Look for <script type="application/json">…</script>
    2. Look for window._SSR_DATA_ = {…};
    Return first dict that has product_id & seller_info.
    """
    blk = None
    m = SCRIPT_RX_JSON.search(page_html) or SCRIPT_RX_JS.search(page_html)
    if m:
        blk = m.group(2) if m.lastindex == 2 else m.group(1)

    if not blk:
        return None
    try:
        data = json.loads(html_lib.unescape(blk))
    except Exception as e:
        logger.debug("JSON parse failed: %s", e)
        return None

    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "product_id" in node and "seller_info" in node:
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None

# ──────────────────────────────── Playwright I/O ─────────────────────────────
PDP_URL    = "https://www.tiktok.com/shop/pdp/{pid}"
PAGE_DATA  = "/api/shop/pdp_desktop/page_data/"

async def crawl_product(product_id: int, kafka: KafkaWriter, pool: ProxyPool):
    proxy = await pool.next()
    pw_kwargs = {"proxy": {"server": f"http://{proxy}"}} if proxy else {}

    async with async_playwright() as pw:
        browser  = await pw.chromium.launch(headless=True, **pw_kwargs)
        context  = await browser.new_context()
        page     = await context.new_page()

        # ── load cookies (optional)
        cookie_file = Path("/app/cookies.json")
        if cookie_file.exists():
            await context.add_cookies(
                chrome_to_playwright(json.loads(cookie_file.read_text()))
            )
            ##debugger
            #loaded = await context.cookies()
            #logger.debug("Playwright context now has %d cookies", len(loaded))

        try:
            ##debugger
            # await page.goto("https://www.tiktok.com/", wait_until="domcontentloaded")
            # logged_in = await page.locator("text=Log in").count() == 0
            # logger.debug("Logged‑in UI visible? %s", logged_in)
            ##
            await page.goto("https://www.tiktok.com/about",
                            wait_until="domcontentloaded")

            def is_pdp_resp(resp):
                return PAGE_DATA in resp.url and str(product_id) in resp.url

            # ───────────────────────── primary attempt ─────────────────────
            try:
                async with page.expect_response(is_pdp_resp,
                                                timeout=60_000) as wait:
                    await page.goto(PDP_URL.format(pid=product_id),
                                    wait_until="networkidle")
                data = await (await wait.value).json()
            except PwTimeout:
                data = None

            # ──────────────────────── fallback: HTML parse ─────────────────
            if not data or "product_info" not in data:
                html = await page.content()
                logger.debug("HTML head: %s…",
                             html[:1000].replace("\n", "\\n")[:300])
                detail = extract_pdp_json(html)
                if not detail:
                    logger.warning("product %s – JSON not found, rotating proxy",
                                   product_id)
                    await pool.ban(proxy)
                    return
                data = {
                    "product_info": detail,
                    "seller_info":  detail.get("seller_info", {})
                }

            # ─────────────────────────── validate ──────────────────────────
            if "seller_info" not in data or "product_info" not in data:
                logger.warning("product %s – missing keys, rotating proxy",
                               product_id)
                await pool.ban(proxy)
                return

            seller_id = int(data["seller_info"]["seller_id"])
            price     = data["product_info"]["price"]
            currency  = data["product_info"].get("currency", "USD")

            now = datetime.utcnow()

            await kafka.send({
                "product_id":  product_id,
                "seller_id":   seller_id,
                "price":       price,
                "currency":    currency,
                "snapshot_ts": now.isoformat(),
            })

            #database
            price_cents = int(float(price) * 100)
            with ENGINE.begin() as cx:
                cx.execute(sa.insert(ProductList).values(
                    product_id=product_id,
                    seller_id=seller_id,
                    price_cents=price_cents,
                    currency=currency,
                    updated_at=now,
                ).on_conflict_do_update(
                    index_elements=[ProductList.product_id],
                    set_={"price_cents": price_cents,
                          "currency": currency,
                          "updated_at": now},
                ))
                cx.execute(sa.insert(ProductDetail).values(
                    product_id=product_id,
                    seller_id=seller_id,
                    snap_date=date.today(),
                    price_cents=price_cents,
                    currency=currency,
                    stock=None,
                ).on_conflict_do_nothing())

            logger.info("product %s scraped for seller %s",
                        product_id, seller_id)

        finally:
            await browser.close()

# ──────. DB helpers & seeds
DB_RETRIES = 10
def wait_engine(max_wait: int = 30) -> sa.Engine:
    for _ in range(DB_RETRIES):
        try:
            with ENGINE.connect():
                return ENGINE
        except sa.exc.OperationalError:
            time.sleep(3)
    raise RuntimeError("Postgres never became ready")

async def fetch_product_seeds(limit: int = 20) -> List[int]:
    eng = wait_engine()
    with eng.begin() as cx:
        rows = cx.execute(
            sa.text("""SELECT product_id
                       FROM product_seed
                       ORDER BY added_at DESC
                       LIMIT :n"""), {"n": limit})
        return [r[0] for r in rows]

########### main ###########
async def main() -> None:
    kafka = KafkaWriter(os.getenv("KAFKA_TOPIC", "tiktok_raw"))
    await kafka.start()
    try:
        proxy_pool = pool_from_env(os.getenv("PROXY_POOL", "").split(","))
        products   = await fetch_product_seeds()
        if not products:
            logger.warning("No product_seed rows - nothing to crawl.")
            return
        await asyncio.gather(*(crawl_product(p, kafka, proxy_pool)
                               for p in products))
    finally:
        await kafka.stop()

if __name__ == "__main__":
    asyncio.run(main())
