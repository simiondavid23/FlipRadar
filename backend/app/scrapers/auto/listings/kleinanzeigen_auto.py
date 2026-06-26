"""Kleinanzeigen.de — anunturi auto (categoria 216). platform="kleinanzeigen_auto"."""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
)

_BASE = "https://www.kleinanzeigen.de"


async def search_kleinanzeigen_auto(query: str = "", make: str = "", filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    # Categoria auto = c216. Keyword-ul (query/make) se prefixeaza in slug.
    keyword = " ".join(x for x in [(make or "").strip(), (query or "").strip()] if x).strip()
    if keyword:
        url = f"{_BASE}/s-autos/{urllib.parse.quote(keyword)}/c216"
    else:
        url = f"{_BASE}/s-autos/c216"
    if page > 1:
        # Kleinanzeigen pagineaza in path: /s-autos/seite:N/.../c216
        url = url.replace("/s-autos/", f"/s-autos/seite:{page}/", 1)

    params = {}
    if filters.get("price_min") is not None or filters.get("price_max") is not None:
        lo = int(float(filters["price_min"])) if filters.get("price_min") is not None else ""
        hi = int(float(filters["price_max"])) if filters.get("price_max") is not None else ""
        params["priceType"] = "FIXED"
        params["minPrice"] = lo
        params["maxPrice"] = hi
    if filters.get("plz"):
        params["locationCity"] = filters["plz"]
    if filters.get("radius_km"):
        params["locationRadius"] = filters["radius_km"]

    headers = build_headers({"Referer": _BASE + "/", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params or None, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[kleinanzeigen_auto] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[kleinanzeigen_auto] error: {exc}")
        return []

    cards = soup.select("article.aditem") or soup.select(".aditem")
    for card in cards:
        try:
            title_el = card.select_one(".aditem-main--middle--title") or card.select_one("h2 a") or card.find("a", href=True)
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            link = card.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            price_el = card.select_one(".aditem-main--middle--price-shipping--price") or card.select_one(".aditem-main--middle--price")
            pret = parse_price(price_el.get_text(" ", strip=True)) if price_el else None

            loc_el = card.select_one(".aditem-main--top--left")
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-imgsrc") or img.get("data-src")) if img else None

            card_text = card.get_text(" ", strip=True)
            results.append(make_listing(
                platform="kleinanzeigen_auto", external_id=card.get("data-adid"), titlu=titlu,
                make=make or None, year=extract_year(titlu) or extract_year(card_text),
                km=extract_km(card_text), pret=pret, moneda="EUR",
                locatie=locatie or "Germania", source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[kleinanzeigen_auto] card parse error: {exc}")
            continue

    print(f"[kleinanzeigen_auto] {len(results)} anunturi (make='{make}', q='{query}')")
    return results[:MAX_LISTINGS]
