"""OLX.ro — anunturi auto (categoria autoturisme). platform="olx_auto"."""
import json
import re
import urllib.parse

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
    safe_soup, thumb_from_img,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters, AUTO_PLATFORM_CATEGORIES
from app.services.log_manager import log_manager
from app.utils.listing_dates import iso_to_naive_local
from app.utils.olx_state import extract_olx_ad_meta

_BASE = "https://www.olx.ro"
_CAT_BASE = "/auto-masini-moto-ambarcatiuni/"  # baza fixa; segmentul final = categoria selectata
# Categorii confirmate (auto_categories.py). Orice altceva -> fallback "autoturisme".
_OLX_CATEGORIES = {c["value"] for c in AUTO_PLATFORM_CATEGORIES["olx_auto"] if c.get("value")}


def _olx_id(href: str):
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", href or "")
    return m.group(1) if m else None


def _olx_upgrade_thumb(url: str) -> str:
    """Normalizeaza sufixul OLX `;s=WxH` la o dimensiune de thumbnail stabila (1000x1000).

    Reprodus dupa app/services/radar/olx_scraper.py::_upgrade_image_url (acelasi CDN
    frankfurt.apollo.olxcdn.com) — local, fara import din app.services.radar.*. Un URL
    fara `;s=` ramane neatins.
    """
    if not url:
        return ""
    return re.sub(r";s=\d+x\d+", ";s=1000x1000", url)


# OLX-STATE-1: `_photos_map_from_state` a disparut de aici — pozele vin din
# `extract_olx_ad_meta` (app/utils/olx_state.py), din ACEEASI parsare de state ca
# datele si categoria. Era a doua parsare a aceluiasi HTML (~470 ms per pagina).
# Ridicarea la ;s=1000x1000 a ramas locala (_olx_upgrade_thumb): e afisare, nu state.


async def search_olx_auto(query: str = "", filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    cat = (filters.get("category") or "").strip()
    category = cat if cat in _OLX_CATEGORIES else "autoturisme"
    base_url = _BASE + _CAT_BASE + category + "/"
    if (query or "").strip():
        base_url += f"q-{urllib.parse.quote(query.strip())}/"

    params = {"search[order]": "created_at:desc"}
    if page > 1:
        params["page"] = page
    if filters.get("price_min") is not None:
        params["search[filter_float_price:from]"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["search[filter_float_price:to]"] = int(float(filters["price_max"]))
    if filters.get("make"):
        params["search[filter_enum_make][0]"] = filters["make"]
    if filters.get("year_min") is not None:
        params["search[filter_float_year:from]"] = int(filters["year_min"])
    # NOTA: parametrul vechi search[filter_float_enginesize_km:to] pentru km_max a fost
    # ELIMINAT — test live (azi) a aratat ca intoarce 0 rezultate (param neconfirmat de OLX,
    # rupe cautarea). Candidatii milage/mileage au dat tot 0. Fara un param de km confirmat
    # live nu punem un inlocuitor ghicit (regula: nu inventa).
    # Campuri tehnice confirmate: fuel_type, engine_capacity_min/max, body_type, condition,
    # seller_type. Scanner-ul trimite "fuel"/"body" pentru fuel_type/body_type.
    apply_confirmed_filters("olx_auto", filters, params,
                            aliases={"fuel_type": "fuel", "body_type": "body"})

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("auto_listings", "SCAN", f"OLX Auto: cautare '{query or 'auto'}'")
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(base_url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[olx_auto] HTTP {resp.status_code}")
                log_manager.emit("auto_listings", "ERR", f"OLX Auto: HTTP {resp.status_code}")
                return []
            soup = safe_soup(resp.text)
    except Exception as exc:
        print(f"[olx_auto] error: {exc}")
        log_manager.emit("auto_listings", "ERR", f"OLX Auto eroare: {str(exc)[:80]}")
        return []

    # AA-1 — pozele reale ale TUTUROR cardurilor stau in __PRERENDERED_STATE__ (ads[]),
    # inclusiv cele de sub fold pe care OLX le lazy-load-eaza (src/data-src raman
    # placeholder in HTML-ul server-rendered). Construim map-ul {token -> URL} o data/pagina.
    # DATE-2 + OLX-STATE-1 — o SINGURA parsare de state per pagina: acelasi dict da
    # pozele (AA-1), cele doua date ale anuntului (`createdTime` / `lastRefreshTime`)
    # si restul meta-ului. `_photos_map_from_state` era a doua parsare a aceluiasi HTML.
    date_map = extract_olx_ad_meta(resp.text)

    cards = soup.select('div[data-cy="l-card"]') or soup.select('[data-testid="l-card"]')
    cu_poza = 0
    din_state = 0
    for card in cards:
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = _BASE + href

            title_el = card.find("h4") or card.find("h6") or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            price_el = card.find(attrs={"data-testid": "ad-price"}) or card.find("p")
            price_raw = price_el.get_text(" ", strip=True) if price_el else ""
            pret = parse_price(price_raw)
            moneda = "EUR" if ("€" in price_raw or "eur" in price_raw.lower()) else "RON"

            loc_el = card.find(attrs={"data-testid": "location-date"})
            locatie = None
            if loc_el:
                raw = loc_el.get_text(" ", strip=True)
                locatie = raw.split("-")[0].strip() if "-" in raw else raw.strip()

            # DATE-2 — conventia Auto e datetime NAIV LOCAL (vezi iso_to_naive_local).
            # `_olx_id` da exact cheia din meta (token-ul -ID<...>.html).
            _meta = date_map.get(_olx_id(href) or "") or {}

            img = card.find("img")
            # OLX lazy-load: pentru cardurile de sub fold `src`/`data-src` raman placeholder
            # in HTML-ul server-rendered (poza reala e populata din JS). thumb_from_img
            # acopera candidatii din tag; daca niciunul nu e URL real, cadem pe poza din
            # __PRERENDERED_STATE__ (ads[]) dupa token-ul din URL (-ID<token>.html). Daca nici
            # acolo -> "" (feed-ul arata fallback-ul ImageOff, nu o imagine rupta).
            # OLX-STATE-1: pozele vin din meta (BRUTE, toate); ridicarea la ;s=1000x1000
            # ramane aici, e o decizie de afisare a modulului, nu o proprietate a state-ului.
            _poze = _meta.get("photos") or []
            img_thumb = thumb_from_img(img)
            thumb = img_thumb or (_olx_upgrade_thumb(_poze[0]) if _poze else "")
            if thumb:
                cu_poza += 1
                if not img_thumb:
                    din_state += 1

            results.append(make_listing(
                platform="olx_auto", external_id=_olx_id(href), titlu=titlu,
                year=extract_year(titlu), km=extract_km(titlu),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
                listed_at=iso_to_naive_local(_meta.get("created")),
                refreshed_at=iso_to_naive_local(_meta.get("refreshed")),
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[olx_auto] card parse error: {exc}")
            continue

    print(f"[olx_auto] {len(results)} anunturi pentru '{query}' "
          f"({cu_poza} cu poza, {din_state} completate din state)")
    log_manager.emit("auto_listings", "OK",
                     f"OLX Auto: {len(results)} anunturi ({cu_poza} cu poza, {din_state} completate din state)")
    return results[:MAX_LISTINGS]
