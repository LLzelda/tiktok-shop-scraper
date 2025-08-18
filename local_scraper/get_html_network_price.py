
import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import re
import json

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

# Output directories
output_dir = Path("pdp_html_playwright")
output_dir.mkdir(parents=True, exist_ok=True)
json_log = Path("price_log.csv")

# Extract product ID from URL
def extract_pid(url):
    return url.rstrip("/").split("/")[-1]

# Async scraping function
async def scrape_all(urls):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        results = []

        for url in urls:
            pid = extract_pid(url)
            page = await context.new_page()
            price_info = {"product_id": pid, "price": "N/A"}

            async def handle_response(response):
                try:
                    if "product/details" in response.url and response.status == 200:
                        json_data = await response.json()
                        # Try different possible price paths
                        price_data = json_data.get("data", {}).get("price", {})
                        real_price = price_data.get("real_price") or "?"
                        currency = price_data.get("currency_symbol", "$")
                        price_info["price"] = f"{currency}{real_price / 100:.2f}" if isinstance(real_price, int) else real_price
                except Exception:
                    pass  # Ignore JSON errors

            page.on("response", handle_response)

            try:
                print(f"[INFO] Fetching {url}")
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle")

                html = await page.content()
                with open(output_dir / f"{pid}.html", "w", encoding="utf-8") as f:
                    f.write(html)

                print(f"[PRICE] {pid}: {price_info['price']}")
                results.append(price_info)

            except Exception as e:
                print(f"[ERROR] {url} – {e}")
            finally:
                await page.close()

        await browser.close()

        # Save price log
        pd.DataFrame(results).to_csv(json_log, index=False)

# Run it
asyncio.run(scrape_all(urls))
