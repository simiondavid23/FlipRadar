"""SCA Auctions — mai deschis decat Copart/IAAI, deci extragem si datele care la
ceilalti necesita cont (pret/licitatie vizibila public, daca exista in pagina).
"""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.lots._common import (
    IMPERSONATE, MAX_LOTS, build_headers, parse_int, parse_money, make_lot,
)

_BASE = "https://www.scaauctions.com"


async def search_sca_lots(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    filters = filters or {}
    url = f"{_BASE}/inventory"
    params = {"search": query} if query else None
    headers = build_headers({"Referer": _BASE + "/"})
    results = []

    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[sca] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[sca] error: {exc}")
        return []

    cards = (
        soup.select(".vehicle-card")
        or soup.select(".inventory-item")
        or soup.select("[data-lot]")
        or soup.select("article")
    )
    for card in cards:
        try:
            link = card.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            title_el = card.find(["h3", "h4"]) or card.find(class_=re.compile(r"title", re.I)) or link
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue

            price_el = card.find(class_=re.compile(r"price|bid", re.I))
            current_bid = parse_money(price_el.get_text(" ", strip=True)) if price_el else None

            loc_el = card.find(class_=re.compile(r"location|branch", re.I))
            location_city = loc_el.get_text(" ", strip=True) if loc_el else None

            dmg_el = card.find(class_=re.compile(r"damage", re.I))
            damage = dmg_el.get_text(" ", strip=True) if dmg_el else None

            odo_el = card.find(class_=re.compile(r"odometer|miles|mileage", re.I))
            odometer = parse_int(odo_el.get_text(" ", strip=True)) if odo_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            year_m = re.search(r"\b(19|20)\d{2}\b", title)
            year = int(year_m.group(0)) if year_m else None

            results.append(make_lot(
                platform="sca", lot_number=card.get("data-lot"), title=title, year=year,
                damage_primary=damage, location_city=location_city, odometer=odometer,
                thumbnail_url=thumb, source_url=href, current_bid=current_bid,
                requires_account=[],
            ))
            if len(results) >= MAX_LOTS:
                break
        except Exception as exc:
            print(f"[sca] card parse error: {exc}")
            continue

    print(f"[sca] {len(results)} loturi pentru '{query}'")
    return results[:MAX_LOTS]
