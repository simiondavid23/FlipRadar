"""Scraper Okazii.ro — Playwright + playwright-stealth (browser real, JS randat).

Diagnostic (Playwright+stealth, headless, networkidle): /cautare?q= incarca
shell-ul Angular/jQuery dar NU randeaza carduri de produs in acest mediu
(produsele vin prin XHR /ajax/catalog care necesita sesiune si nu se completeaza
intr-un browser headless din acest mediu). Scraperul ramane corect structural:
randeaza cu browser stealth si extrage cardurile in formatul standard al
aplicatiei. Cand pagina randeaza produse (alt mediu / IP / proxy), le extrage;
altfel intoarce [] cu WARN, fara date inventate.
"""
import re
import urllib.parse
from typing import Optional

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import is_excluded, get_proxy_config

_BASE = "https://www.okazii.ro"

CARD_SEL = (
    "[class*='product-card'], [class*='listing-item'], [class*='product-item'], "
    "article[data-product-id], .o-list-item, li.product, .oferta"
)
TITLE_SELS = ["h2", "h3", "[class*='title']", "a[title]", "a"]
PRICE_SELS = ["[class*='price']", "[class*='pret']", ".price", ".pret"]
LINK_SELS = ["a[href*='-a']", "a[href]"]
IMG_SELS = ["img"]


def _extract_external_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = (re.search(r"-a(\d{5,})", url) or re.search(r"/a/(\d{5,})", url)
         or re.search(r"-(\d{6,})", url))
    if m:
        return f"okazii_{m.group(1)}"
    path = urllib.parse.urlparse(url).path.strip("/").replace("/", "_")
    return f"okazii_{path[-50:]}" if path else None


def _q_text(card, selectors) -> str:
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            try:
                t = el.inner_text().strip()
                if t:
                    return t
            except Exception:
                continue
    return ""


def _q_attr(card, selectors, *attrs) -> str:
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            for a in attrs:
                v = el.get_attribute(a)
                if v:
                    return v
    return ""


def _to_price(text: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.,]", "", text or "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def search_okazii(
    keyword: str,
    max_price: Optional[float] = None,
    condition: str = "all",
    exclude_words: Optional[list] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    page: int = 1,
) -> list:
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    # Okazii (Playwright) — fara suport multi-pagina deocamdata; pagina 2+ = gol,
    # iar scanner-ul se opreste (0 anunturi noi).
    if page > 1:
        return []

    if category:
        url = f"{_BASE}/{category.strip('/')}?q={urllib.parse.quote(keyword_clean)}"
    else:
        url = f"{_BASE}/cautare?q={urllib.parse.quote(keyword_clean)}"

    log_manager.emit("radar", "SCAN", f'Okazii Playwright "{keyword_clean}"')

    proxy_cfg = get_proxy_config()
    launch_kwargs = {"headless": True}
    if proxy_cfg:
        launch_kwargs["proxy"] = {"server": proxy_cfg.get("https") or proxy_cfg.get("http")}

    results = []
    try:
        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(**launch_kwargs)

            # Cookie de sesiune salvat (radar_settings.okazii_cookie) injectat in context.
            from app.database import SessionLocal
            from app.models.radar_settings import RadarSettings
            from app.services.crypto_service import decrypt_cookie
            _db = SessionLocal()
            try:
                _rs = _db.query(RadarSettings).first()
                # MODIFICARE 4 — cookie-ul e stocat criptat; îl decriptăm la citire.
                cookie_str = decrypt_cookie((_rs.okazii_cookie or "").strip()) if _rs else ""
            finally:
                _db.close()

            context = browser.new_context()
            if cookie_str:
                parsed = []
                for part in cookie_str.split(";"):
                    part = part.strip()
                    if "=" in part:
                        name, value = part.split("=", 1)
                        parsed.append({
                            "name": name.strip(), "value": value.strip(),
                            "domain": ".okazii.ro", "path": "/",
                        })
                if parsed:
                    context.add_cookies(parsed)
                    log_manager.emit("radar", "INFO", "Okazii: cookie de sesiune injectat")
            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=35000)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=35000)

                try:
                    page.wait_for_selector(CARD_SEL, timeout=12000)
                except Exception:
                    log_manager.emit("radar", "WARN",
                                     "Okazii: niciun card randat in acest mediu → 0 rezultate")
                    return []
                page.wait_for_timeout(800)

                cards = page.query_selector_all(CARD_SEL)
                log_manager.emit("radar", "INFO", f"Okazii: {len(cards)} carduri in DOM")

                for card in cards[:48]:
                    try:
                        title = _q_text(card, TITLE_SELS)
                        if not title or is_excluded(title, exclude_words):
                            continue

                        price = _to_price(_q_text(card, PRICE_SELS))
                        if max_price and price and price > max_price:
                            continue
                        if min_price and price and price < min_price:
                            continue

                        href = _q_attr(card, LINK_SELS, "href")
                        if href and href.startswith("/"):
                            href = _BASE + href
                        ext = _extract_external_id(href)
                        if not ext:
                            continue

                        thumb = _q_attr(card, IMG_SELS, "src", "data-src")
                        if thumb and thumb.startswith("/"):
                            thumb = _BASE + thumb

                        results.append({
                            "external_id": ext,
                            "platform": "okazii",
                            "title": title,
                            "price": price,
                            "currency": "RON",
                            "condition": None,
                            "location": None,
                            "url": href,
                            "images": [thumb] if thumb else [],
                            "description": None,
                            "seller_name": None,
                            "seller_id": None,
                            "listed_at": None,
                        })
                    except Exception:
                        continue
            except Exception as exc:
                log_manager.emit("radar", "ERR", f"Okazii eroare: {str(exc)[:100]}")
            finally:
                browser.close()
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"Okazii Playwright init: {str(exc)[:100]}")
        return []

    log_manager.emit("radar", "OK",
                     f'Okazii: {len(results)} rezultate pentru "{keyword_clean}"')
    return results
