"""Facebook Marketplace — categoria Property Rentals (chirii imobiliare).

Reutilizeaza aceeasi sesiune autentificata ca facebook_auto_scraper (storage_state
Playwright salvat in data/facebook_session_{user_id}.json). Functie SINCRONA — la
fel ca facebook_auto, dispecerul din real_estate_scanner o apeleaza DIRECT, nu prin
asyncio.run (sync_playwright nu poate rula intr-un event loop asyncio).
"""
import json
import re
import urllib.parse
from typing import Optional

_BASE_URL = "https://www.facebook.com/marketplace/category/propertyrentals/"


def _parse_price(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.,]", "", raw or "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def search_facebook_real_estate(query: str = "", filters: dict = {}) -> list:
    from app.services.log_manager import log_manager
    from app.scrapers.auto.listings.facebook_auto_scraper import (
        _find_session_file, _is_session_valid)
    filters = filters or {}

    session_path = _find_session_file()
    if not session_path or not _is_session_valid(session_path):
        log_manager.emit("real_estate", "WARN",
            "Facebook RE: sesiune expirata sau inexistenta. "
            "Reautentifica-te din Setari Radar → Facebook.")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("real_estate", "ERR", "Facebook RE: Playwright nu e instalat.")
        return []

    params = {}
    if query:
        params["query"] = query
    if filters.get("price_min"):
        params["minPrice"] = int(float(filters["price_min"]))
    if filters.get("price_max"):
        params["maxPrice"] = int(float(filters["price_max"]))
    url = _BASE_URL + ("?" + urllib.parse.urlencode(params) if params else "")

    log_manager.emit("real_estate", "SCAN", f"Facebook RE Playwright: {query!r}")

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
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
                if "login" in page.url.lower():
                    log_manager.emit("real_estate", "WARN",
                        "Facebook RE: login wall — reconecteaza-te.")
                    return []
                for _ in range(2):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(800)

                items = page.query_selector_all('a[href*="/marketplace/item/"]')
                log_manager.emit("real_estate", "INFO",
                    f"Facebook RE: {len(items)} carduri gasite")

                seen = set()
                for it in items[:40]:
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
                        location = None
                        for line in lines:
                            if price is None and ("RON" in line.upper() or "lei" in line.lower() or "€" in line or re.match(r"^\d", line)):
                                pv = _parse_price(line)
                                if pv is not None:
                                    price = pv
                                    continue
                            if not title and not re.match(r"^[\d.,]+$", line):
                                title = line
                                continue
                            if not location:
                                location = line
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
                            "currency":      "EUR" if "€" in text else "RON",
                            "location":      location,
                            "url":           full,
                            "source_url":    full,
                            "thumbnail_url": thumb or "",
                            "platform":      "facebook_marketplace",
                        })
                        if len(results) >= 30:
                            break
                    except Exception:
                        continue
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"Facebook RE Playwright eroare: {str(exc)[:100]}")

    log_manager.emit("real_estate", "OK",
        f"Facebook RE: {len(results)} rezultate pentru {query!r}")
    return results
