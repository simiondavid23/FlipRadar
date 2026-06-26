"""IAAI — date PUBLICE fara cont.

Extrage din pagina publica de search ce e disponibil (titlu, locatie, data
licitatie, km, damage vizibil, thumbnail). Campurile care necesita cont raman None.
"""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.lots._common import (
    IMPERSONATE, MAX_LOTS, REQUIRES_ACCOUNT,
    build_headers, parse_int, make_lot,
)
from app.services.log_manager import log_manager

_BASE = "https://www.iaai.com"


async def search_iaai_lots(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    filters = filters or {}
    url = f"{_BASE}/Search?Keyword={urllib.parse.quote(query)}"
    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("auto_lots", "SCAN", f"IAAI: cautare loturi '{query or '-'}'")
    results = []

    try:
        async with AsyncSession() as session:
            resp = await session.get(url, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[iaai] HTTP {resp.status_code}")
                log_manager.emit("auto_lots", "ERR", f"IAAI: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[iaai] error: {exc}")
        log_manager.emit("auto_lots", "ERR", f"IAAI eroare: {str(exc)[:80]}")
        return []

    cards = (
        soup.select(".table-row")
        or soup.select("[data-vehicle]")
        or soup.select(".vehicle-card")
        or soup.select("article")
    )
    for card in cards:
        try:
            link = card.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            title_el = card.find(["h4", "h3"]) or card.find(class_=re.compile(r"title|heading", re.I)) or link
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue

            loc_el = card.find(class_=re.compile(r"location|branch|yard", re.I))
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
                platform="iaai", title=title, year=year,
                damage_primary=damage, location_city=location_city,
                odometer=odometer, thumbnail_url=thumb, source_url=href,
                requires_account=REQUIRES_ACCOUNT,
            ))
            if len(results) >= MAX_LOTS:
                break
        except Exception as exc:
            print(f"[iaai] card parse error: {exc}")
            continue

    print(f"[iaai] {len(results)} loturi pentru '{query}'")
    log_manager.emit("auto_lots", "OK", f"IAAI: {len(results)} loturi gasite")
    return results[:MAX_LOTS]
