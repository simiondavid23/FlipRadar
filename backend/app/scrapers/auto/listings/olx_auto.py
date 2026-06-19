"""OLX.ro — anunturi auto (categoria autoturisme). platform="olx_auto"."""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
)

_BASE = "https://www.olx.ro"
_PATH = "/auto-masini-moto-ambarcatiuni/autoturisme/"


def _olx_id(href: str):
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", href or "")
    return m.group(1) if m else None


async def search_olx_auto(query: str = "", filters: dict = {}) -> list:
    filters = filters or {}
    base_url = _BASE + _PATH
    if (query or "").strip():
        base_url += f"q-{urllib.parse.quote(query.strip())}/"

    params = {"search[order]": "created_at:desc"}
    if filters.get("price_min") is not None:
        params["search[filter_float_price:from]"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["search[filter_float_price:to]"] = int(float(filters["price_max"]))
    if filters.get("make"):
        params["search[filter_enum_make][0]"] = filters["make"]
    if filters.get("year_min") is not None:
        params["search[filter_float_year:from]"] = int(filters["year_min"])
    if filters.get("km_max") is not None:
        params["search[filter_float_enginesize_km:to]"] = int(filters["km_max"])

    headers = build_headers({"Referer": _BASE + "/"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(base_url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[olx_auto] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[olx_auto] error: {exc}")
        return []

    cards = soup.select('div[data-cy="l-card"]') or soup.select('[data-testid="l-card"]')
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

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="olx_auto", external_id=_olx_id(href), titlu=titlu,
                year=extract_year(titlu), km=extract_km(titlu),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[olx_auto] card parse error: {exc}")
            continue

    print(f"[olx_auto] {len(results)} anunturi pentru '{query}'")
    return results[:MAX_LISTINGS]
