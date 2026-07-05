"""Facebook Auto — anunturi de vehicule din Facebook Marketplace.

RESCRIS (2026-07-05): inlocuim Playwright + citirea vizuala (inner_text pe linii,
fragila si nefiltrata pe keyword — intorcea Opel Mokka / camioane MAN / jante) cu
pattern-ul DOVEDIT din Radar Piata (services/radar/facebook_scraper.py): curl_cffi +
cookie-urile din sesiunea salvata + citire STRUCTURATA din JSON-ul server-rendered
(<script type="application/json">). Playwright NU se mai foloseste nicaieri aici.

Reutilizam DIRECT piesele dovedite din Radar (import cross-modul; radar/facebook_scraper
NU importa nimic din scrapers/auto -> fara dependinta circulara): is_facebook_session_valid,
_load_cookies, _build_search_url, _fetch, _iter_listing_objects, _parse_price,
_parse_location, _is_active, _deep_first, _BASE.

Task 1 — diagnostic live (2026-07-05): obiectele de listare din feed-ul de cautare NU au
chei structurate de vehicul (cautare recursiva dupa vehicle_year/vehicle_mileage/
vehicle_fuel_type/... = NICIUNA). Cheile reale: marketplace_listing_title, listing_price
(amount corect, ex "11500.00"), location, primary_listing_photo, marketplace_listing_
category_id, seller, creation_time. Deci an/km se extrag din TITLU cu regex
(extract_year/extract_km din _common), ca la Kleinanzeigen/AutoScout24.

Categoria vehicule = marketplace_listing_category_id "807311116002614" ("Auto, Moto si
Ambarcatiuni") — confirmat live (== id-ul din PLATFORM_CATEGORIES['facebook'] SI ==
category_id de pe anunturile reale de masini). Filtram client-side pe ea ca sa scapam de
jante/piese/necorelate pe care le intoarce cautarea fuzzy FB.
"""
import glob
import os
from datetime import datetime
from typing import Optional

from app.scrapers.auto.listings._common import extract_year, extract_km
from app.services.log_manager import log_manager
# Piese DOVEDITE din Radar Piata (curl_cffi, fara Playwright). Import sigur — radar/
# facebook_scraper nu importa nimic din scrapers/auto.
from app.services.radar.facebook_scraper import (
    is_facebook_session_valid, _load_cookies, _build_search_url, _fetch,
    _iter_listing_objects, _parse_price, _parse_location, _is_active, _deep_first, _BASE,
)

_SESSION_GLOB = "data/facebook_session_*.json"


def _find_session_file() -> Optional[str]:
    """Cel mai recent fisier de sesiune Facebook (storage_state salvat la login)."""
    files = glob.glob(_SESSION_GLOB)
    return max(files, key=os.path.getmtime) if files else None


def _is_session_valid(session_path: str) -> bool:
    """Delegat la validatorul Radar (fisier existent + cookie c_user + varsta < 30 zile).
    Pastrat ca API public — /api/auto-listings/stats il importa pentru statusul sesiunii."""
    return is_facebook_session_valid(session_path)


def _vehicles_category_id() -> str:
    """Id-ul categoriei 'Auto, Moto si Ambarcatiuni' din PLATFORM_CATEGORIES['facebook'].
    Confirmat live: 807311116002614 (== marketplace_listing_category_id de pe masini)."""
    try:
        from app.services.radar.categories import PLATFORM_CATEGORIES
        for c in PLATFORM_CATEGORIES.get("facebook", []):
            lbl = (c.get("label") or "").lower()
            if c.get("value") and "auto" in lbl and "moto" in lbl:
                return str(c["value"])
    except Exception:
        pass
    return "807311116002614"


def search_facebook_auto(query: str = "", filters: dict = {}, page: int = 1,
                         max_scrolls: int = 10) -> list:
    """Cauta vehicule pe Facebook Marketplace prin curl_cffi + JSON structurat.

    Semnatura pastrata compatibila cu apelul din auto_listings_scanner
    (query/filters/page). `page`/`max_scrolls` sunt NO-OP (un singur fetch aduce tot
    feed-ul server-rendered); page>1 -> [] (semnal „gata", ca la Radar).
    """
    filters = filters or {}
    query = (query or "").strip()
    if not query:
        return []
    if page and page > 1:
        return []

    session_path = _find_session_file()
    if not session_path or not is_facebook_session_valid(session_path):
        log_manager.emit("auto_listings", "WARN",
            "Facebook Auto: sesiune expirata/inexistenta. Reautentifica din Setari Radar -> Facebook.")
        return []

    cookies = _load_cookies(session_path)
    min_price = filters.get("price_min")
    max_price = filters.get("price_max")
    try:
        max_price_f = float(max_price) if max_price not in (None, "") else None
    except (ValueError, TypeError):
        max_price_f = None

    url = _build_search_url(query, min_price, max_price)
    log_manager.emit("auto_listings", "SCAN", f'Facebook Auto "{query}"')

    html, final_url = _fetch(url, cookies)
    if html is None:
        return []
    low = (final_url or "").lower()
    if "login" in low or "checkpoint" in low:
        log_manager.emit("auto_listings", "WARN",
            "Facebook Auto: redirect login/checkpoint — sesiune posibil expirata.")
        return []

    veh_cat = _vehicles_category_id()
    by_id: dict[str, dict] = {}
    for o in _iter_listing_objects(html):
        oid = str(o.get("id"))
        if oid and oid not in by_id:
            by_id[oid] = o

    results = []
    skipped_cat = 0
    for oid, o in by_id.items():
        if not _is_active(o):
            continue
        title = (o.get("marketplace_listing_title") or "").strip()
        if not title:
            continue
        # Filtru categorie: doar vehicule (scapa de jante/piese/necorelate din cautarea fuzzy).
        cat_id = o.get("marketplace_listing_category_id")
        if cat_id is not None and str(cat_id) != veh_cat:
            skipped_cat += 1
            continue

        price, currency = _parse_price(o)
        if max_price_f and price is not None and price > max_price_f:
            continue

        # An/km din TITLU — FB search NU expune chei structurate de vehicul (vezi Task 1).
        year = extract_year(title)
        km = extract_km(title)

        image_url = ((o.get("primary_listing_photo") or {}).get("image") or {}).get("uri")
        seller = o.get("marketplace_listing_seller") or {}
        ct = _deep_first(o, "creation_time")
        listed_at = None
        if isinstance(ct, (int, float)) and ct > 1_000_000_000:
            try:
                listed_at = datetime.fromtimestamp(ct)
            except (OverflowError, OSError, ValueError):
                listed_at = None

        results.append({
            "external_id":   f"fb_{oid}",
            "platform":      "facebook_auto",
            "title":         title,
            "price":         price,
            "currency":      currency,
            "year":          year,
            "km":            km,
            "location":      _parse_location(o),
            "url":           f"{_BASE}/marketplace/item/{oid}/",
            "source_url":    f"{_BASE}/marketplace/item/{oid}/",
            "thumbnail_url": image_url or "",
            "image_url":     image_url or "",
            "seller_name":   (seller.get("name") if isinstance(seller, dict) else None),
            "listed_at":     listed_at,
            "description":   None,
        })

    if skipped_cat:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_cat} anunturi excluse (nu sunt categoria vehicule)")
    log_manager.emit("auto_listings", "OK",
        f'Facebook Auto: {len(results)} rezultate pentru "{query}"')
    return results
