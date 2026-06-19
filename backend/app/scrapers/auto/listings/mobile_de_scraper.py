"""Mobile.de — anunturi auto (Germania). platform="mobile_de".

Datele publice disponibile: titlu, an, km, pret (EUR), locatie, URL, thumbnail.
"""
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
)

_SEARCH_URL = "https://suchen.mobile.de/fahrzeuge/search.html"

# Top marci -> makeId mobile.de (valori uzuale; pot necesita verificare per platforma).
MOBILE_DE_MAKE_IDS = {
    "Audi": "1900",
    "BMW": "3500",
    "Mercedes": "17200",
    "Mercedes-Benz": "17200",
    "Volkswagen": "25200",
    "Ford": "9000",
    "Opel": "19000",
    "Porsche": "20000",
    "Renault": "20700",
    "Peugeot": "19800",
    "Toyota": "24100",
    "Skoda": "22900",
    "Volvo": "25100",
    "Mazda": "16800",
    "Nissan": "18700",
    "Hyundai": "11600",
    "Kia": "13200",
    "Fiat": "8800",
    "Citroen": "5300",
    "Seat": "22500",
    "Honda": "11000",
    "Dacia": "6600",
}


async def search_mobile_de(make_id: str = "", filters: dict = {}) -> list:
    filters = filters or {}
    # Permite trimiterea numelui marcii in loc de ID (ex: "BMW").
    if make_id and not make_id.isdigit():
        make_id = MOBILE_DE_MAKE_IDS.get(make_id, MOBILE_DE_MAKE_IDS.get(make_id.title(), ""))

    params = {"damageUnrepaired": "false", "isSearchRequest": "true"}
    if make_id:
        params["makeModelVariant1.makeId"] = make_id
    if filters.get("price_max") is not None:
        params["price.max"] = int(float(filters["price_max"]))
    if filters.get("price_min") is not None:
        params["price.min"] = int(float(filters["price_min"]))
    if filters.get("year_min") is not None:
        params["minFirstRegistrationDate"] = int(filters["year_min"])

    headers = build_headers({"Referer": "https://www.mobile.de/", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(_SEARCH_URL, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[mobile_de] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[mobile_de] error: {exc}")
        return []

    cards = (
        soup.select(".cBox-body--resultitem")
        or soup.select('[data-testid="result-list-item"]')
        or soup.select("article")
        or soup.select("[data-listing-id]")
    )
    for card in cards:
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = "https://suchen.mobile.de" + href

            title_el = card.find(["h2", "h3"]) or card.find(class_=re.compile(r"title|headline", re.I)) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            price_el = card.find(class_=re.compile(r"price", re.I)) or card.find(attrs={"data-testid": re.compile(r"price", re.I)})
            pret = parse_price(price_el.get_text(" ", strip=True)) if price_el else parse_price(card_text)

            loc_el = card.find(class_=re.compile(r"location|seller", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="mobile_de", external_id=card.get("data-listing-id"), titlu=titlu,
                year=extract_year(titlu) or extract_year(card_text), km=extract_km(card_text),
                pret=pret, moneda="EUR", locatie=locatie or "Germania",
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[mobile_de] card parse error: {exc}")
            continue

    print(f"[mobile_de] {len(results)} anunturi (make_id='{make_id}')")
    return results[:MAX_LISTINGS]
