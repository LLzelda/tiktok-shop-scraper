"""
Open each third-level category URL → collect PDP links
Writes pdp_links.csv
"""
import argparse, asyncio, csv, random
from pathlib import Path
from playwright.async_api import async_playwright, Page

PDP_SEL = "a[href*='/pdp/']"

def load_cookies():
    p = Path("cookies.txt")
    if not p.exists(): return []
    pairs = [c.strip().split("=",1) for c in p.read_text().split(";") if "=" in c]
    return [{"name":n,"value":v,"domain":".tiktok.com","path":"/"} for n,v in pairs]

async def scroll_and_collect(page: Page, n_scroll: int) -> list[str]:
    links = set()
    for i in range(n_scroll+1):
        anchors = await page.eval_on_selector_all(
            PDP_SEL, "els => els.map(e => e.getAttribute('href'))")
        for h in anchors:
            if h:
                if h.startswith("/"): h = "https://www.tiktok.com" + h
                links.add(h.split("?")[0])
        ##break early
        if links and i >= 1:
            break
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(random.randint(600, 900))
    return list(links)

async def worker(queue: asyncio.Queue, out: Path, scrolls: int, ctx):
    while not queue.empty():
        url = await queue.get()
        page = await ctx.new_page()
        try:
            #await page.goto(url, timeout=60000)
            await page.goto(url, timeout=8_000, wait_until="domcontentloaded")
            if await page.query_selector("#secsdk-captcha"):
                print(f"⚠️  captcha - skipped  {url}")
                continue
            pdps = await scroll_and_collect(page, scrolls)
            if pdps:
                with out.open("a", newline="") as fh:
                    csv.writer(fh).writerows([[p] for p in pdps])
                print(f"✓  {len(pdps):3} PDPs  ← {url}")
        except Exception as e:
            print(f"⚠️  {url} … {e}")
        finally:
            await page.close()
            queue.task_done()

async def main(third_csv: Path, output: Path, scrolls: int, concurrency: int):
    #urls = [r.strip() for r in third_csv.read_text().splitlines()[1:]]  # skip header
    # urls = []
    # with third_csv.open(newline='', encoding='utf-8') as fh:
    #     reader = csv.DictReader(fh)          # 'id','slug','url'
    #     for row in reader:
    #         urls.append(row["url"])
    with third_csv.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)          # header line is present
        urls = [row["url"].strip() for row in reader if row["url"].startswith("http")]

    print(f"Loaded {len(urls):,} third-level URLs")
    queue = asyncio.Queue()
    for u in urls: queue.put_nowait(u)

    cookies = load_cookies()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        #ctx = await browser.new_context()
        ctx = await browser.new_context(java_script_enabled=False)
        if cookies: await ctx.add_cookies(cookies)
        
        async def _block(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                await route.abort()
            else:
                await route.continue_()
        await ctx.route("**/*", _block)

        workers = [worker(queue, output, scrolls, ctx) for _ in range(concurrency)]
        await asyncio.gather(*workers)

        await ctx.close(); await browser.close()
    print(f"✓  All done - {output.stat().st_size/1024:.1f} KB of links")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--third-csv", type=Path, default=Path("third_categories.csv"))
    ap.add_argument("--output",    type=Path, default=Path("pdp_links.csv"))
    ap.add_argument("--scroll",    type=int,  default=2)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    args.output.unlink(missing_ok=True)
    asyncio.run(main(args.third_csv, args.output, args.scroll, args.concurrency))





