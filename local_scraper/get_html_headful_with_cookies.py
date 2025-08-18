
import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import re
from http.cookiejar import MozillaCookieJar

# Load and normalize URLs
df = pd.read_csv("pdp_links.csv")
raw_urls = df.iloc[:, 0].dropna().unique().tolist()

def normalize_url(url):
    match = re.search(r'/(\d{15,})', url)
    if match:
        pid = match.group(1)
        return f"https://www.tiktok.com/shop/pdp/{pid}"
    else:
        return url

urls = [normalize_url(url) for url in raw_urls]

# Output directory
output_dir = Path("pdp_html_playwright")
output_dir.mkdir(parents=True, exist_ok=True)

COOKIES_TXT = "cookies.txt"

def extract_pid(url):
    return url.rstrip("/").split("/")[-1]

def parse_cookies_txt(path):
    jar = MozillaCookieJar()
    jar.load(path, ignore_discard=True, ignore_expires=True)
    return [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "expires": c.expires,
            "httpOnly": c._rest.get("HttpOnly") or False,
            "secure": c.secure,
            "sameSite": "Lax"
        }
        for c in jar
    ]

async def scrape_all(urls):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()

        # Load cookies from cookies.txt
        try:
            cookies = parse_cookies_txt(COOKIES_TXT)
            await context.add_cookies(cookies)
            print(f"[INFO] Loaded cookies from {COOKIES_TXT}")
        except Exception as e:
            print(f"[WARNING] Failed to load cookies: {e}")

        page = await context.new_page()

        for i, url in enumerate(urls):
            pid = extract_pid(url)
            try:
                print(f"[INFO] Fetching {url}")
                await page.goto(url, timeout=45000)
                #await context.add_cookies(cookies)
                await page.wait_for_load_state("networkidle", timeout=20000)

                price_text = await page.evaluate("""
                    () => {
                        const container = document.querySelectorAll("span.flex.flex-row.items-baseline")[1];
                        if (!container) return null;
                        const spans = container.querySelectorAll("span");
                        return Array.from(spans).map(el => el.innerText.trim()).join("");
                    }
                """)
                print(f"[PRICE] {pid}: {price_text}")

                html = await page.content()
                with open(output_dir / f"{pid}.html", "w", encoding="utf-8") as f:
                    f.write(html)

            except Exception as e:
                print(f"[ERROR] {url} – {e}")
        await browser.close()

asyncio.run(scrape_all(urls))