
import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import re
import os

# Load and normalize TikTok product URLs
df = pd.read_csv("pdp_links.csv")
raw_urls = df.iloc[:, 0].dropna().unique().tolist()

def normalize_url(url):
    match = re.search(r'/pdp/(?:[\w-]+/)?(\d+)', url)
    if match:
        return f"https://www.tiktok.com/shop/pdp/{match.group(1)}"
    return url

urls = [normalize_url(url) for url in raw_urls]

# Output directory
output_dir = Path("pdp_html_playwright")
output_dir.mkdir(parents=True, exist_ok=True)

# 

CHROME_PROFILE_PATH = os.path.expanduser("'/Users/mingl/Library/Application Support/Google/Chrome/Default'")


def extract_pid(url):
    return url.rstrip("/").split("/")[-1]

async def scrape_all(urls):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            CHROME_PROFILE_PATH,
            channel="chrome",
            headless=False,
            slow_mo=50,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("\n⚠️  Make sure you're logged into TikTok on this Chrome profile.\n")

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
