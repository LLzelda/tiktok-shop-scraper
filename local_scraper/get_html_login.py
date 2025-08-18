
import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import re


df = pd.read_csv("pdp_links.csv")
raw_urls = df.iloc[:, 0].dropna().unique().tolist()

def normalize_url(url):
    match = re.search(r'/(\d{15,})', url)
    if match:
        pid = match.group(1)
        return f"https://www.tiktok.com/shop/pdp/{pid}"
    return url

urls = [normalize_url(url) for url in raw_urls]

output_dir = Path("pdp_html_playwright")
output_dir.mkdir(parents=True, exist_ok=True)


USER_DATA_DIR = "tiktok_user_data"

def extract_pid(url):
    return url.rstrip("/").split("/")[-1]

async def scrape_all(urls):
    async with async_playwright() as p:
        # Persistent context keeps login session
        context = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            slow_mo=50,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # First-time login notice
        print("\n🧠 If this is your first run, please log in manually in the opened browser.\n")
        print("⏳ Once you're logged in, press ENTER here to continue scraping...")
        input()

        for url in urls:
            pid = extract_pid(url)
            try:
                print(f"[INFO] Fetching {url}")
                await page.goto(url, timeout=45000)
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

        await context.close()

asyncio.run(scrape_all(urls))
