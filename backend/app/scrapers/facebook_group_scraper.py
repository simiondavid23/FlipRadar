import asyncio
import hashlib
import random
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import async_playwright

from app.utils.cookie_crypto import normalize_cookies

# FBG-2 (C2) — permalink-ul postarii din ancorele articolului. Formele intalnite:
#   /groups/<gid>/posts/<pid>/            (forma canonica)
#   /groups/<gid>/permalink/<pid>/        (forma veche, inca servita)
#   ?multi_permalinks=<pid>               (feed-ul de grup, link de bump)
#   permalink.php?story_fbid=<pid>&id=... (fallback istoric)
# <pid> e ID-ul NUMERIC global al postarii — singurul identificator stabil intre
# rulari. Ancorele cu comment_id sunt permalink-uri de COMENTARIU si se sar.
_PERMALINK_PATTERNS = (
    re.compile(r"/groups/[^/?#]+/(?:posts|permalink)/(\d+)"),
    re.compile(r"[?&]multi_permalinks=(\d+)"),
    re.compile(r"[?&]story_fbid=(\d+)"),
)


def _post_id_from_hrefs(hrefs: list) -> Optional[str]:
    """ID-ul numeric al postarii din lista de href-uri a unui articol; None daca
    niciun href nu contine un permalink de postare."""
    for href in hrefs or []:
        if not href or "comment_id" in href:
            continue
        for pat in _PERMALINK_PATTERNS:
            m = pat.search(href)
            if m:
                return m.group(1)
    return None


def _text_fingerprint(text: str) -> str:
    """FBG-2 (C2) — fallback cand articolul nu expune niciun permalink: hash pe
    primele ~300 caractere normalizate (NFKD->ascii, lower, spatii pliate).

    Inlocuieste vechiul `pos_{len(seen_ids)}` — un index POZITIONAL per rulare:
    la rularea urmatoare, postari COMPLET NOI primeau aceleasi pos_N si erau
    aruncate TACUT de dedup-ul din _process_config."""
    n = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    n = re.sub(r"\s+", " ", n).lower().strip()[:300]
    return "txt_" + hashlib.sha1(n.encode()).hexdigest()[:16]


def _permalink_url(group_url: str, post_id: Optional[str]) -> Optional[str]:
    """URL-ul direct al postarii (M4 — cardul din feed ducea doar la grup).
    Doar pentru ID-uri numerice reale; pentru fingerprint-uri de text nu exista
    URL de postare, deci None (feed-ul cade pe group_url)."""
    if not post_id or not str(post_id).isdigit():
        return None
    base = (group_url or "").split("?")[0].rstrip("/")
    if not base:
        return None
    return f"{base}/posts/{post_id}/"


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

        # Incarca cookies utilizatorului. FBG-2 (C1): normalizare si AICI, nu doar
        # la salvare — cookie-urile criptate INAINTE de fix au inca formatul brut
        # de extensie (sameSite lowercase etc.), pe care add_cookies il respinge.
        try:
            await context.add_cookies(normalize_cookies(cookies))
        except Exception as e:
            await browser.close()
            raise Exception(f"COOKIES_INVALIDE: {e}")

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
                    # Extrage textul postarii (selectoarele raman de validat live — C3)
                    text_selectors = [
                        '[data-ad-rendering-role="story_message"]',
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
                    text = text.strip()

                    # FBG-2 (C2) — identitatea postarii: permalink-ul NUMERIC din
                    # ancore (stabil intre rulari), cu fallback pe amprenta
                    # textului. Vechiul aria-label/data-ft nu exista pe DOM-ul
                    # comet actual (aria apare pe COMENTARII), iar pos_N era un
                    # index pozitional care omora dedup-ul intre rulari.
                    hrefs = await article.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.getAttribute('href'))")
                    pid = _post_id_from_hrefs(hrefs)
                    post_id = pid or _text_fingerprint(text)

                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)
                    new_found_in_batch += 1

                    # Extrage timestamp postare. FBG-2 (m2): epoch-ul e UTC —
                    # fromtimestamp() naiv-LOCAL se compara gresit (offset 3h) cu
                    # last_run_at naiv-UTC; pastram conventia naiv-UTC a aplicatiei.
                    posted_at = None
                    time_el = await article.query_selector("abbr[data-utime]")
                    if time_el:
                        utime = await time_el.get_attribute("data-utime")
                        if utime and utime.isdigit():
                            posted_at = datetime.fromtimestamp(
                                int(utime), tz=timezone.utc).replace(tzinfo=None)

                    # Daca am ajuns la postari mai vechi decat last_run_at, opreste
                    if last_run_at and posted_at and posted_at < last_run_at:
                        stop_scraping = True
                        break

                    results.append({
                        "post_id": post_id,
                        "post_url": _permalink_url(group_url, pid),
                        "text": text[:1500],
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
