"""Autovit.ro — anunturi auto. platform="autovit"."""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price,
    extract_year, extract_km, normalize_fuel, normalize_gearbox, make_listing,
)

_BASE = "https://www.autovit.ro"


def _slug(text: str) -> str:
    return urllib.parse.quote((text or "").strip().lower().replace(" ", "-"))


async def search_autovit(make: str = "", model: str = "", filters: dict = {}) -> list:
    filters = filters or {}
    path = "/autoturisme/"
    if make:
        path += f"{_slug(make)}/"
        if model:
            path += f"{_slug(model)}/"
    url = _BASE + path

    params = {}
    if make:
        params["search[filter_enum_make][0]"] = make
    if filters.get("price_min") is not None:
        params["search[filter_float_price:from]"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["search[filter_float_price:to]"] = int(float(filters["price_max"]))
    if filters.get("year_min") is not None:
        params["search[filter_float_year:from]"] = int(filters["year_min"])

    headers = build_headers({"Referer": _BASE + "/"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[autovit] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[autovit] error: {exc}")
        return []

    cards = (
        soup.select("article[data-id]")
        or soup.select('[data-testid="listing-ad"]')
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

            title_el = card.find(["h1", "h2"]) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            price_el = card.find(class_=re.compile(r"price", re.I)) or card.find(attrs={"data-testid": re.compile(r"price", re.I)})
            price_raw = price_el.get_text(" ", strip=True) if price_el else card_text
            pret = parse_price(price_raw)
            moneda = "EUR" if ("€" in price_raw or "eur" in price_raw.lower()) else "RON"

            loc_el = card.find(class_=re.compile(r"location", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="autovit", external_id=card.get("data-id"), titlu=titlu,
                make=make or None, model=model or None,
                year=extract_year(titlu) or extract_year(card_text),
                km=extract_km(card_text),
                engine_type=normalize_fuel(card_text),
                gearbox=normalize_gearbox(card_text),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[autovit] card parse error: {exc}")
            continue

    print(f"[autovit] {len(results)} anunturi (make='{make}')")
    return results[:MAX_LISTINGS]
