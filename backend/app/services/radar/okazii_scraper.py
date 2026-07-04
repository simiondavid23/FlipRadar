"""Scraper Okazii.ro — marketplace produse noi + second hand.

Rescris complet de la zero (Faza 0 — diagnostic live, fara Playwright/cookie).
curl_cffi impersonate=chrome110. Structura confirmata prin fetch-uri reale:

- Cautare:   https://www.okazii.ro/cautare/{kw}.html   (spatii -> '+' literal)
             https://www.okazii.ro/cautare/{kw}/{categorie-slug}.html   (cu categorie)
- Stare:     modificator de path pe ultimul segment inainte de .html:
             '--nou' | '--second-hand'   (ex. /cautare/apple+iphone--nou.html)
- Pret:      ?pret_min={int}&pret_max={int}   (merg si ca GET, desi form-ul e POST)
- Paginare:  ?page={N}   (36 rezultate/pagina)
- Card:      #listing-Okazii .list-item
- external_id: '-a(\\d+)' la finalul URL-ului anuntului
"""
import random
import re
import time
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config


_IMPERSONATE = "chrome110"
_BASE = "https://www.okazii.ro"

# Plasa de siguranta la paginare (scanner-ul se opreste cand nu mai apar anunturi noi).
_OKAZII_MAX_PAGES = 20


def _okazii_keyword(keyword: str) -> str:
    """Uneste cuvintele cautarii cu '+' literal (cerinta Okazii); fiecare cuvant
    e url-encodat normal (diacritice), doar spatiile devin '+'."""
    words = [w for w in re.split(r"\s+", (keyword or "").strip()) if w]
    return "+".join(urllib.parse.quote(w, safe="") for w in words)


def _condition_modifier(condition: str) -> str:
    if condition == "new":
        return "--nou"
    if condition == "used":
        return "--second-hand"
    return ""


def _parse_price(raw: str) -> tuple[Optional[float], str]:
    """Format RO: '.' separator de mii, ',' zecimale — '1.200,00 Lei' -> 1200.0."""
    if not raw:
        return None, "RON"
    currency = "EUR" if ("EUR" in raw.upper() or "€" in raw) else "RON"
    cleaned = re.sub(r"[^\d.,]", "", raw).replace(".", "").replace(",", ".")
    try:
        return (float(cleaned) if cleaned else None), currency
    except ValueError:
        return None, currency


def _extract_external_id(url: str) -> Optional[str]:
    """ID Okazii = '-a<digits>' la finalul URL-ului anuntului (fara .html)."""
    if not url:
        return None
    m = re.search(r"-a(\d+)(?:\.html?)?(?:[?#].*)?$", url)
    if m:
        return f"okazii_{m.group(1)}"
    return None


def _upgrade_image(url: str) -> Optional[str]:
    """Okazii serveste imagini in variante '-{W}_{H}' (ex. -160_160). Le urcam la
    -1000_1000 pentru calitate maxima."""
    if not url:
        return None
    base = url.split("?")[0]
    if base.startswith("//"):
        base = "https:" + base
    return re.sub(r"-\d+_\d+(\.\w+)?$", r"-1000_1000\1", base)


def _build_url(keyword: str, category: Optional[str], condition: str,
               min_price: Optional[float], max_price: Optional[float], page: int) -> str:
    segments = [_okazii_keyword(keyword)]
    if category:
        segments.append(category.strip("/"))
    modifier = _condition_modifier(condition)
    if modifier:
        segments[-1] = segments[-1] + modifier
    path = "/".join(segments) + ".html"

    params = {}
    if min_price and min_price > 0:
        params["pret_min"] = int(min_price)
    if max_price and max_price > 0:
        params["pret_max"] = int(max_price)
    if page and page > 1:
        params["page"] = int(page)

    url = f"{_BASE}/cautare/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def _request(url: str, referer: str = _BASE + "/") -> Optional[str]:
    headers = build_headers({"Referer": referer})
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
    for attempt in range(3):
        try:
            resp = curl_requests.get(url, **req_kwargs)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt)
                log_manager.emit("radar", "WARN", f"Okazii: 429 rate-limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            if resp.status_code == 404:
                return None
            log_manager.emit("radar", "WARN", f"Okazii: HTTP {resp.status_code} pentru {url}")
            return None
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Okazii: eroare fetch ({attempt+1}/3): {str(exc)[:100]}")
            time.sleep(rate_limit_backoff(attempt))
    return None


def fetch_okazii_listing_details(url: str) -> dict:
    """Pagina individuala -> descriere completa + toate imaginile din galerie
    (calitate 1000x1000). {"images": [...], "description": str|None}."""
    if not url:
        return {"images": [], "description": None}
    html = _request(url, referer=_BASE + "/")
    if not html:
        return {"images": [], "description": None}

    soup = BeautifulSoup(html, "html.parser")

    description = None
    desc_el = (
        soup.select_one("#text_anunt")
        or soup.select_one(".ux-user-description")
        or soup.select_one("#description_tmce")
    )
    if desc_el:
        description = desc_el.get_text("\n", strip=True) or None

    imgs: list[str] = []
    seen = set()
    gallery = soup.select(".product-gallery .gallery-thumbs img, .product-gallery #gallery_show_big_img, #produs_gallery_thumbs img")
    for im in gallery:
        src = im.get("data-zoom-image") or im.get("src") or im.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        up = _upgrade_image(src)
        if not up or up in seen:
            continue
        seen.add(up)
        imgs.append(up)

    return {"images": imgs, "description": description}


def search_okazii(
    keyword: str,
    max_price: Optional[float] = None,
    condition: str = "all",
    exclude_words: Optional[list] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    page: int = 1,
) -> list[dict]:
    """Cauta pe Okazii dupa keyword; returneaza listinguri in format standard.

    `category` = slug de categorie din PLATFORM_CATEGORIES["okazii"] (path segment).
    `page` (>=1) adauga ?page=N. Enrichment secvential (descriere + galerie) ca la OLX.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if page > _OKAZII_MAX_PAGES:
        return []

    url = _build_url(keyword_clean, category, condition, min_price, max_price, page)
    log_manager.emit("radar", "SCAN", f'Okazii "{keyword_clean}" (pag {page})')

    html = _request(url)
    if not html:
        log_manager.emit("radar", "WARN", f'Okazii: fara raspuns pentru "{keyword_clean}" (pag {page})')
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("#listing-Okazii .list-item")

    # Daca am filtrat pe stare via path, reflectam conditia in listing.
    listing_condition = None
    if condition == "new":
        listing_condition = "nou"
    elif condition == "used":
        listing_condition = "second hand"

    results: list[dict] = []
    for card in cards:
        try:
            link_tag = card.select_one("figure.item-image a[href]") or card.select_one(".item-title h2 a[href]")
            if not link_tag:
                link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            if href.startswith("/"):
                href = _BASE + href

            ext_id = _extract_external_id(href)
            if not ext_id:
                continue

            title_tag = card.select_one(".item-title h2 a") or card.select_one(".item-title")
            title = ""
            if title_tag:
                title = (title_tag.get("title") or title_tag.get_text(" ", strip=True) or "").strip()
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_el = (
                card.select_one(".item-price .main-cost .prSup")
                or card.select_one(".item-price .prSup")
                or card.select_one(".item-price")
            )
            price, currency = (None, "RON")
            if price_el:
                price, currency = _parse_price(price_el.get_text(" ", strip=True))
            if price is None:
                continue
            if max_price and max_price > 0 and price > max_price:
                continue
            if min_price and min_price > 0 and price < min_price:
                continue

            img_tag = card.select_one("figure.item-image img") or card.find("img")
            image_url = None
            if img_tag:
                raw_img = img_tag.get("src") or img_tag.get("data-src") or ""
                if raw_img and not raw_img.startswith("data:"):
                    image_url = _upgrade_image(raw_img)
            images = [image_url] if image_url else []

            results.append({
                "external_id": ext_id,
                "platform": "okazii",
                "title": title,
                "price": price,
                "currency": currency,
                "condition": listing_condition,
                "location": None,  # Okazii nu afiseaza locatie pe card (oferte magazin)
                "url": href,
                "images": images,
                "description": None,
                "seller_name": None,
                "seller_id": None,
                "listed_at": None,
            })
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Okazii: card invalid ignorat: {str(exc)[:80]}")
            continue

    # Enrichment secvential — descriere completa + toate imaginile din galerie.
    for idx, item in enumerate(results):
        if idx > 0:
            time.sleep(random.uniform(0.5, 1.0))
        try:
            details = fetch_okazii_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Okazii: enrichment {item['external_id']}: {str(exc)[:80]}")
            continue

    log_manager.emit("radar", "OK", f'Okazii: {len(results)} rezultate pentru "{keyword_clean}" (pag {page})')
    return results
