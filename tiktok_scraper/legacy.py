import os, asyncio, json, logging, random, time
from datetime import datetime, date
from typing import List
from pathlib import Path 
import sqlalchemy as sa
from playwright.async_api import async_playwright, Response, Error as PwError, TimeoutError as PwTimeout

from .proxy import pool_from_env, ProxyPool
from .producer import KafkaWriter
from etl.models import ENGINE, ProductList, ProductDetail
#from .signer import sign_url

#a trick to not be like a BOTTTTT
from bs4 import BeautifulSoup
import re, html as html_lib

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
# JSON_PAT = re.compile(r'"product_detail"\s*:\s*({.*?})\s*,\s*"seller_info"', re.S)
# async def html_fallback(page) -> dict | None:
#     """
#     Parse PDP HTML for embedded product_detail JSON.

#     Works with both:
#       • <script id="__NEXT_DATA__">… "product_detail":{…}</script>
#       • <script id="sigi-pb-data"> window._SSR_DATA_ = { product_detail: … }</script>
#     """
#     html = await page.content()
#     #debugger, mark when un-use
#     logger.debug("HTML head: %s…", html[:1000].replace("\n", "\\n")[:300])

#     # 1. quick regex – fastest
#     m = JSON_PAT.search(html)
#     if m:
#         try:
#             return json.loads(m.group(1))
#         except Exception:
#             pass

#     # 2. slower BeautifulSoup walk
#     soup  = BeautifulSoup(html, "lxml")
#     for node in soup.find_all("script"):
#         if not node.string:
#             continue
#         if "product_detail" in node.string:
#             try:
#                 m2 = JSON_PAT.search(node.string)
#                 if m2:
#                     return json.loads(m2.group(1))
#             except Exception:
#                 continue
#     return None



def extract_pdp_json(page_html: str) -> dict | None:
    """
    Find the first <script …application/json> block, parse JSON,
    then walk it depth-first until we hit an object that has
    both 'product_id' and 'seller_info'.
    Return that dict or None.
    """
    #grab the raw JSON text
    m = re.search(
        r'<script[^>]+type=["\']application/json["\'][^>]*>(\{.*?})</script>',
        page_html,
        re.S,
    )
    if not m:
        return None

    try:
        #some HTML entities (&quot;) appear in older builds
        raw = html_lib.unescape(m.group(1))
        data = json.loads(raw)
    except Exception as e:
        logger.debug("JSON parse failed: %s", e)
        return None

    #DFS walk
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
        if c.get("session") is True and "expiry" not in c:
            # session cookie: let Playwright handle expiry
            pass
        elif "expiry" in c:
            c["expires"] = int(c["expiry"])          # rename
        # map sameSite if present
        ss = c.get("sameSite")
        if ss:
            mapped = SAMESITE_MAP.get(ss.lower())
            if mapped:
                c["sameSite"] = mapped
            else:
                c.pop("sameSite", None)              # drop unknown value
        # drop Chrome‑only keys Playwright dislikes
        for k in ("hostOnly", "creation", "lastAccessed",
                  "priority", "sameParty", "sourceScheme",
                  "sourcePort", "expiry", "session"):
            c.pop(k, None)
        fixed.append(c)
    return fixed


PDP_URL = "https://www.tiktok.com/shop/pdp/{pid}"
PAGE_DATA = "/api/shop/pdp_desktop/page_data/"

async def crawl_product(product_id: int, kafka: KafkaWriter, pool: ProxyPool):
    proxy = await pool.next()
    pw_kwargs = {"proxy": {"server": f"http://{proxy}"}} if proxy else {}

    playwright = await async_playwright().start()
    browser    = await playwright.chromium.launch(headless=True, **pw_kwargs)
    context    = await browser.new_context()
    page       = await context.new_page()
    cookie_file = Path("/app/cookies.json")
    if cookie_file.exists():
        raw = json.loads(cookie_file.read_text())
        await context.add_cookies(chrome_to_playwright(raw))
    try:
        # warm cookies
        await page.goto("https://www.tiktok.com/about", wait_until="domcontentloaded")

        def is_pdp_resp(resp):
            return PAGE_DATA in resp.url and str(product_id) in resp.url

        try:
            async with page.expect_response(is_pdp_resp, timeout=60_000) as wait:
                await page.goto(PDP_URL.format(pid=product_id), wait_until="networkidle")
            data = await (await wait.value).json()
            print(data)
        except PwTimeout:
            # fallback: call page_data ourselves inside the DOM

            #a helper
            async def fetch_pdp_json(page, url: str) -> dict | None:
                return await page.evaluate(
                    """async u => {
                        const r = await fetch(u, {credentials:'include'});
                        const txt = await r.text();
                        if (!txt.trim().startsWith('{')) return {__html: txt.slice(0,200)};
                        return JSON.parse(txt);
                    }""",
                    url
                )
            url = f"{PAGE_DATA}?product_id={product_id}"
            #try:
                # data = await page.evaluate(
                #     """async u => (await fetch(u,{credentials:'include'})).json()""",
                #     url
                # )
            data = await fetch_pdp_json(page, url)

            #     if data is None or "__html" in data:
            #         logger.warning("product %s - blocked (HTML body starts: %s…) rotating proxy",
            #                     product_id, (data or {}).get("__html", ""))
            #         await pool.ban(proxy)
            #         return
            if data is None or "__html" in data:
                #trick: second fallback: parse embedded HTML JSON
                data = await page.content()
                detail = extract_pdp_json(data)
            if not detail:
                logger.warning("product %s - JSON not found, rotating proxy", product_id)
                await pool.ban(proxy)
                return
            # except Exception as e:
            #     logger.warning("product %s - fallback fetch failed %s, rotating proxy",
            #                    product_id, e)
            #     await pool.ban(proxy)
            #     return
        # validation
        if "seller_info" not in data or "product_info" not in data:
            logger.warning("product %s - missing keys, rotating proxy", product_id)
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
            "snapshot_ts": now.isoformat()
        })

        price_cents = int(float(price) * 100)
        with ENGINE.begin() as cx:
            cx.execute(sa.insert(ProductList).values(
                product_id  = product_id,
                seller_id   = seller_id,
                price_cents = price_cents,
                currency    = currency,
                updated_at  = now
            ).on_conflict_do_update(
                index_elements=[ProductList.product_id],
                set_={"price_cents": price_cents,
                      "currency":    currency,
                      "updated_at":  now}
            ))

            cx.execute(sa.insert(ProductDetail).values(
                product_id  = product_id,
                seller_id   = seller_id,
                snap_date   = date.today(),
                price_cents = price_cents,
                currency    = currency,
                stock       = None
            ).on_conflict_do_nothing())

        logger.info("product %s scraped for seller %s", product_id, seller_id)

    finally:
        await browser.close()
        await playwright.stop()



# ──────────────────────────────────────────────────────────────────────────────
#feed fetch
# ──────────────────────────────────────────────────────────────────────────────
async def fetch_product_seeds(limit: int = 20) -> List[int]:
    eng = wait_engine()
    with eng.begin() as cx:
        rows = cx.execute(
            sa.text("SELECT product_id FROM product_seed ORDER BY added_at DESC LIMIT :n"),
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
        products   = await fetch_product_seeds()
        if not products:
            logger.warning("No product_seed rows – nothing to crawl.")
            return

        await asyncio.gather(*(crawl_product(p, kafka, proxy_pool) for p in products))
    finally:
        await kafka.stop()


if __name__ == "__main__":
    asyncio.run(main())
