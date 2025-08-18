import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import re

# Load links
df = pd.read_csv("pdp_links.csv")
raw_urls = df.iloc[:, 0].dropna().unique().tolist()

#normalize URLs to https://www.tiktok.com/shop/pdp/<product_id>
def normalize_url(url):
    match = re.search(r'/(\d{15,})', url)  # extract 15+ digit ID
    if match:
        pid = match.group(1)
        return f"https://www.tiktok.com/shop/pdp/{pid}"
    else:
        return url  # fallback to original if pattern doesn't match

urls = [normalize_url(url) for url in raw_urls]


output_dir = Path("pdp_html_playwright")
output_dir.mkdir(parents=True, exist_ok=True)


def extract_pid(url):
    return url.rstrip("/").split("/")[-1]

#async scraping function
async def scrape_all(urls):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        #browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context()

        for url in urls:
            pid = extract_pid(url)
            page = await context.new_page()
            try:
                print(f"[INFO] Fetching {url}")
                await page.goto(url, timeout=20000)
                
                #wait for price element to render
                await page.wait_for_selector("span.flex.flex-row.items-baseline", timeout=15000)

                # for debug
                try:
                    # Locate the correct price block (2nd .items-baseline)
                    price_container = page.locator("span.flex.flex-row.items-baseline").nth(1)
                    spans = price_container.locator("span")

                    # Try to extract each part safely
                    dollar_sign = await spans.nth(0).inner_text()
                    dollars = await spans.nth(1).inner_text()
                    
                    try:
                        cents = await spans.nth(2).inner_text()
                    except:
                        cents = ""

                    price_text = f"{dollar_sign.strip()}{dollars.strip()}{cents.strip()}"
                    print(f"[PRICE] {pid}: {price_text}")
                except Exception as e:
                    print(f"[WARNING] Could not extract price for {pid}: {e}")


                html = await page.content()
                
                with open(output_dir / f"{pid}.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception as e:
                print(f"[ERROR] Failed to fetch {url}: {e}")
            finally:
                await page.close()

        await browser.close()

asyncio.run(scrape_all(urls))
