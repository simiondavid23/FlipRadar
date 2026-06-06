"""Scraper pentru Facebook Marketplace prin Playwright.

Facebook nu accepta scraping anonim — utilizatorul trebuie sa se logheze
manual o data prin facebook_auth.start_facebook_login_session, iar cookies-urile
de sesiune se salveaza pe disk. La fiecare scan reincarcam cookies-urile in
contextul Playwright si verificam ca sesiunea inca e valida.
"""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from app.services.radar.base_scraper import is_excluded, get_proxy_config
from app.services.radar.categories import FACEBOOK_CATEGORY_IDS


def _session_max_age_days() -> int:
    return 30


def is_facebook_session_valid(session_path: Optional[str]) -> bool:
    """True daca fisierul exista, contine cookies si nu e mai vechi de 30 zile."""
    if not session_path:
        return False
    if not os.path.isfile(session_path):
        return False
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not cookies:
            return False
        has_cuser = any(c.get("name") == "c_user" for c in cookies)
        if not has_cuser:
            return False
        # Check timestamp
        mtime = os.path.getmtime(session_path)
        age_days = (time.time() - mtime) / 86400
        return age_days < _session_max_age_days()
    except Exception as exc:
        print(f"[FacebookScraper] Eroare la validarea sesiunii: {exc}")
        return False


def _parse_price_text(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.,]", "", raw).replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_external_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/marketplace/item/(\d+)", url)
    if m:
        return f"fb_{m.group(1)}"
    return None


def search_facebook(
    keyword: str,
    max_price: float,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    exclude_words: Optional[list[str]] = None,
    session_path: Optional[str] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Cauta pe Facebook Marketplace cu o sesiune Playwright pre-logata."""
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if not is_facebook_session_valid(session_path):
        print("[FacebookScraper] Sesiune expirata — necesita reconectare")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FacebookScraper] Playwright nu e instalat — skip.")
        return []

    q = urllib.parse.quote(keyword_clean)
    min_p = int(min_price) if (min_price and min_price > 0) else 0
    url = f"https://www.facebook.com/marketplace/search/?query={q}&minPrice={min_p}"
    if max_price and max_price > 0:
        url += f"&maxPrice={int(max_price)}"
    if category:
        cat_id = FACEBOOK_CATEGORY_IDS.get(category)
        if cat_id:
            url += f"&category={cat_id}"

    results = []
    proxy_cfg = get_proxy_config()
    launch_kwargs = {"headless": True}
    if proxy_cfg:
        proxy_arg = {"server": proxy_cfg["https"]}
        if proxy_cfg.get("username"):
            proxy_arg["username"] = proxy_cfg["username"]
            proxy_arg["password"] = proxy_cfg["password"]
        launch_kwargs["proxy"] = proxy_arg
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    storage = json.load(f)
                context = browser.new_context(storage_state=storage)
            except Exception:
                context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                # Daca apare login wall, abandonam
                if "login" in page.url.lower():
                    print("[FacebookScraper] Sesiune expirata — necesita reconectare")
                    return []
                # Scroll pentru lazy load
                for _ in range(2):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(800)

                # Selectoare candidat — Facebook isi schimba clasele frecvent,
                # asa ca incercam mai multe pattern-uri si folosim primul care
                # returneaza ceva
                items = page.query_selector_all('a[href*="/marketplace/item/"]')
                seen_urls = set()
                for it in items:
                    try:
                        href = it.get_attribute("href")
                        if not href:
                            continue
                        full_url = href if href.startswith("http") else f"https://www.facebook.com{href}"
                        # Curata query string-ul
                        full_url = full_url.split("?")[0]
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)

                        text = (it.inner_text() or "").strip()
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        if len(lines) < 2:
                            continue
                        price = None
                        title = ""
                        location = None
                        for line in lines:
                            if price is None and ("RON" in line.upper() or "lei" in line.lower() or re.match(r"^\d", line)):
                                p_val = _parse_price_text(line)
                                if p_val is not None:
                                    price = p_val
                                    continue
                            if not title and line and not re.match(r"^[\d.,]+$", line):
                                title = line
                                continue
                            if not location and line and not re.match(r"^[\d.,]+", line):
                                location = line

                        if not title or price is None:
                            continue
                        if max_price and price > max_price:
                            continue
                        if min_price and price < min_price:
                            continue
                        if is_excluded(title, exclude_words):
                            continue

                        ext_id = _extract_external_id(full_url)
                        if not ext_id:
                            continue

                        img_el = it.query_selector("img")
                        image_url = img_el.get_attribute("src") if img_el else None
                        images = [image_url] if image_url else []

                        # Facebook nu expune data postarii in cardul de pe pagina de cautare —
                        # paginile au "X zile in urma" doar pe pagina detalii. Cadem pe now()
                        # ca sa avem totusi o valoare sortabila.
                        results.append({
                            "external_id": ext_id,
                            "platform": "facebook",
                            "title": title,
                            "price": price,
                            "currency": "RON",
                            "condition": None,
                            "location": location,
                            "url": full_url,
                            "images": images,
                            "description": None,
                            "seller_name": None,
                            "seller_id": None,
                            "listed_at": datetime.now(),
                        })
                    except Exception as exc:
                        print(f"[FacebookScraper] Eroare la parsare card: {exc}")
                        continue
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        print(f"[FacebookScraper] Eroare la scraping: {exc}")
        return []

    print(f"[FacebookScraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
