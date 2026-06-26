"""Facebook Auto — Marketplace Vehicles category.

Reutilizeaza aceeasi sesiune autentificata ca scraperul Facebook Marketplace din
Radar Piata (app/services/radar/facebook_scraper.py). Sesiunea e un storage_state
Playwright salvat in data/facebook_session_{user_id}.json (cookies + localStorage).

NOTA: functie SINCRONA (la fel ca radar search_facebook). Dispecerul din
auto_listings_scanner o apeleaza DIRECT, nu prin asyncio.run — sync_playwright nu
poate rula intr-un event loop asyncio.
"""
import glob
import json
import os
import re
import time
import urllib.parse
from typing import Optional

_SESSION_GLOB = "data/facebook_session_*.json"
_BASE_URL = "https://www.facebook.com/marketplace/category/vehicles/"


def _find_session_file() -> Optional[str]:
    """Cel mai recent fisier de sesiune Facebook."""
    files = glob.glob(_SESSION_GLOB)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _is_session_valid(session_path: str) -> bool:
    """Sesiune valida = fisier existent, cu cookie c_user, sub 30 zile vechime.

    Deleaga la validatorul real folosit de Radar Piata; fallback pe varsta
    fisierului (14 zile) daca modulul nu e disponibil.
    """
    if not session_path or not os.path.exists(session_path):
        return False
    try:
        from app.services.radar.facebook_scraper import is_facebook_session_valid
        return is_facebook_session_valid(session_path)
    except Exception:
        age_seconds = time.time() - os.path.getmtime(session_path)
        return age_seconds < (14 * 86400)


def _parse_price(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.,]", "", raw or "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def search_facebook_auto(query: str = "", filters: dict = {}, page: int = 1, max_scrolls: int = 10) -> list:
    # `page` e ignorat (Facebook foloseste infinite scroll); `max_scrolls` limiteaza
    # derularea. Returneaza toate cardurile adunate prin scroll.
    from app.services.log_manager import log_manager
    filters = filters or {}

    session_path = _find_session_file()
    if not session_path or not _is_session_valid(session_path):
        log_manager.emit("auto_listings", "WARN",
            "Facebook Auto: sesiune expirata sau inexistenta. "
            "Reautentifica-te din Setari Radar → Facebook.")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("auto_listings", "ERR", "Facebook Auto: Playwright nu e instalat.")
        return []

    # URL categoria vehicule + filtre de pret.
    params = {}
    if query:
        params["query"] = query
    if filters.get("price_min"):
        params["minPrice"] = int(float(filters["price_min"]))
    if filters.get("price_max"):
        params["maxPrice"] = int(float(filters["price_max"]))
    url = _BASE_URL + ("?" + urllib.parse.urlencode(params) if params else "")

    log_manager.emit("auto_listings", "SCAN", f"Facebook Auto Playwright: {query!r}")

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Restaureaza sesiunea direct din storage_state (la fel ca radar).
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    storage = json.load(f)
                context = browser.new_context(storage_state=storage)
            except Exception:
                context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(4000)
                # Login wall = sesiune respinsa.
                if "login" in page.url.lower():
                    log_manager.emit("auto_listings", "WARN",
                        "Facebook Auto: sesiune respinsa (login wall) — reconecteaza-te.")
                    return []
                # Infinite scroll (Facebook nu pagineaza prin URL): derulam pana
                # cand o pasare nu mai aduce carduri noi (sau atingem max_scrolls).
                seen = set()
                prev_count = 0
                scroll_count = 0
                while scroll_count < max_scrolls:
                    items = page.query_selector_all('a[href*="/marketplace/item/"]')
                    for it in items:
                        try:
                            href = it.get_attribute("href") or ""
                            full = href if href.startswith("http") else f"https://www.facebook.com{href}"
                            full = full.split("?")[0]
                            if "/marketplace/item/" not in full or full in seen:
                                continue
                            seen.add(full)
                            m = re.search(r"/marketplace/item/(\d+)", full)
                            if not m:
                                continue
                            ext_id = m.group(1)

                            text = (it.inner_text() or "").strip()
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            price = None
                            title = ""
                            for line in lines:
                                if price is None and ("RON" in line.upper() or "lei" in line.lower() or re.match(r"^\d", line)):
                                    pv = _parse_price(line)
                                    if pv is not None:
                                        price = pv
                                        continue
                                if not title and not re.match(r"^[\d.,]+$", line):
                                    title = line
                            if not title:
                                continue
                            if filters.get("price_max") and price and price > float(filters["price_max"]):
                                continue

                            img_el = it.query_selector("img")
                            thumb = (img_el.get_attribute("src") or img_el.get_attribute("data-src")) if img_el else ""

                            results.append({
                                "external_id":   ext_id,
                                "title":         title,
                                "price":         price,
                                "currency":      "RON",
                                "url":           full,
                                "source_url":    full,
                                "thumbnail_url": thumb or "",
                                "platform":      "facebook_auto",
                            })
                        except Exception:
                            continue

                    log_manager.emit("auto_listings", "INFO",
                        f"Facebook Auto scroll {scroll_count+1}: {len(results)} total")
                    # Stop cand un scroll nu mai aduce carduri noi.
                    if len(results) == prev_count and scroll_count > 0:
                        break
                    prev_count = len(results)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2500)
                    scroll_count += 1
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        log_manager.emit("auto_listings", "ERR",
            f"Facebook Auto Playwright eroare: {str(exc)[:100]}")

    log_manager.emit("auto_listings", "OK",
        f"Facebook Auto: {len(results)} rezultate pentru {query!r}")
    return results
