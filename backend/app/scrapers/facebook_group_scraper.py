import asyncio
import random
from datetime import datetime
from playwright.async_api import async_playwright


async def scrape_facebook_group(
    group_url: str,
    cookies: list,
    last_run_at: datetime = None,
    max_posts: int = 40,
) -> list:
    """
    Scrapează postări noi dintr-un grup Facebook folosind cookies salvate.
    Returnează o listă de dicționare {post_id, text, posted_at}.
    Nu folosește AI — returnează textul brut pentru procesare ulterioară.
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="ro-RO",
        )

        # Ascunde indicatorii de automatizare
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            window.chrome = {runtime: {}};
        """)

        # Incarca cookies utilizatorului
        await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            await browser.close()
            raise Exception(f"Nu am putut accesa grupul: {e}")

        # Verifica daca suntem logati (redirect la login = cookies expirate)
        current_url = page.url
        if "login" in current_url or "checkpoint" in current_url:
            await browser.close()
            raise Exception("COOKIES_EXPIRATE")

        # Pauza naturala dupa incarcare
        await asyncio.sleep(random.uniform(2.0, 3.5))

        seen_ids = set()
        stop_scraping = False
        scroll_attempts = 0
        max_scroll_attempts = 15

        while (
            not stop_scraping
            and len(results) < max_posts
            and scroll_attempts < max_scroll_attempts
        ):
            # Extrage articolele vizibile
            articles = await page.query_selector_all('[role="article"]')

            new_found_in_batch = 0

            for article in articles:
                try:
                    # ID unic pentru deduplicare
                    aria = await article.get_attribute("aria-label") or ""
                    data_id = await article.get_attribute("data-ft") or ""
                    post_id = aria or data_id or f"pos_{len(seen_ids)}"

                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)
                    new_found_in_batch += 1

                    # Extrage textul postarii
                    text_selectors = [
                        '[data-ad-comet-preview="message"]',
                        '[data-testid="post_message"]',
                        '.xdj266r',
                    ]
                    text = ""
                    for selector in text_selectors:
                        el = await article.query_selector(selector)
                        if el:
                            text = await el.inner_text()
                            break

                    if not text or len(text.strip()) < 20:
                        continue

                    # Extrage timestamp postare
                    posted_at = None
                    time_el = await article.query_selector("abbr[data-utime]")
                    if time_el:
                        utime = await time_el.get_attribute("data-utime")
                        if utime and utime.isdigit():
                            posted_at = datetime.fromtimestamp(int(utime))

                    # Daca am ajuns la postari mai vechi decat last_run_at, opreste
                    if last_run_at and posted_at and posted_at < last_run_at:
                        stop_scraping = True
                        break

                    results.append({
                        "post_id": post_id,
                        "text": text.strip()[:1500],
                        "posted_at": posted_at,
                    })

                except Exception:
                    continue

            # Daca nu am gasit nimic nou in acest batch, probabil am ajuns la final
            if new_found_in_batch == 0:
                scroll_attempts += 1
            else:
                scroll_attempts = 0

            if not stop_scraping and len(results) < max_posts:
                # Scroll cu viteza si distanta variabila
                scroll_px = random.randint(500, 900)
                await page.evaluate(f"window.scrollBy(0, {scroll_px})")
                await asyncio.sleep(random.uniform(1.0, 2.2))

        await browser.close()

    return results
