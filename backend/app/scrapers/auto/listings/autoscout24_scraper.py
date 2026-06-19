"""AutoScout24.ro — anunturi auto. platform="autoscout24"."""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price,
    extract_year, extract_km, normalize_fuel, normalize_gearbox, make_listing,
)

_BASE = "https://www.autoscout24.ro"


async def search_autoscout24(make: str = "", filters: dict = {}) -> list:
    filters = filters or {}
    path = f"/lst/{urllib.parse.quote((make or '').strip().lower())}" if make else "/lst/"
    url = _BASE + path

    params = {"sort": "standard", "desc": "0", "ustate": "N,U", "atype": "C"}
    if filters.get("price_min") is not None:
        params["pricefrom"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["priceto"] = int(float(filters["price_max"]))
    if filters.get("year_min") is not None:
        params["fregfrom"] = int(filters["year_min"])

    headers = build_headers({"Referer": _BASE + "/"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[autoscout24] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[autoscout24] error: {exc}")
        return []

    cards = (
        soup.select("article.cldt-summary-full-item")
        or soup.select('[data-testid="list-item"]')
        or soup.select("article")
    )
    for card in cards:
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = _BASE + href

            title_el = card.find(["h2", "h3"]) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            price_el = card.find(class_=re.compile(r"price", re.I)) or card.find(attrs={"data-testid": re.compile(r"price", re.I)})
            pret = parse_price(price_el.get_text(" ", strip=True)) if price_el else parse_price(card_text)
            moneda = "RON" if ("lei" in (price_el.get_text(" ", strip=True).lower() if price_el else card_text.lower())) else "EUR"

            loc_el = card.find(class_=re.compile(r"location|seller", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="autoscout24", external_id=card.get("data-guid") or card.get("id"),
                titlu=titlu, make=make or None,
                year=extract_year(titlu) or extract_year(card_text), km=extract_km(card_text),
                engine_type=normalize_fuel(card_text), gearbox=normalize_gearbox(card_text),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[autoscout24] card parse error: {exc}")
            continue

    print(f"[autoscout24] {len(results)} anunturi (make='{make}')")
    return results[:MAX_LISTINGS]
