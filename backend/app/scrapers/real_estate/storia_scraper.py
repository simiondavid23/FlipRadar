"""Storia.ro — anunturi imobiliare. platform="storia".

Storia e Next.js: datele listingurilor se afla in scriptul __NEXT_DATA__.
Incercam intai un endpoint JSON, apoi parsam __NEXT_DATA__, apoi HTML simplu.
"""
import json
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price,
    extract_rooms, extract_surface, make_re_listing,
)

_BASE = "https://www.storia.ro"


def _category_path(tip_anunt: str, tip_proprietate: str) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    tr = "inchiriere" if rent else "vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        prop = "casa"
    elif tp.startswith("teren"):
        prop = "teren"
    else:
        prop = "apartament"
    return f"/ro/rezultate/{tr}/{prop}"


def _find_items(obj, out, depth=0):
    """Cauta recursiv lista de anunturi din __NEXT_DATA__."""
    if depth > 8 or len(out) >= MAX_RESULTS:
        return
    if isinstance(obj, dict):
        # Heuristica: un ad are titlu + pret/suprafata/camere.
        keys = set(obj.keys())
        if "title" in keys and ("totalPrice" in keys or "price" in keys or "areaInSquareMeters" in keys):
            out.append(obj)
            return
        for v in obj.values():
            _find_items(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _find_items(v, out, depth + 1)


def _parse_item(it: dict, tip_anunt: str, tip_proprietate: str) -> dict:
    title = it.get("title") or ""
    # Pret
    pret = None
    moneda = "EUR"
    tp = it.get("totalPrice") or it.get("price")
    if isinstance(tp, dict):
        pret = parse_price(tp.get("value"))
        moneda = tp.get("currency") or "EUR"
    elif tp is not None:
        pret = parse_price(tp)
    # Locatie
    loc = it.get("location") or {}
    addr = loc.get("address") if isinstance(loc, dict) else None
    oras = None
    judet = None
    if isinstance(addr, dict):
        city = addr.get("city") or {}
        province = addr.get("province") or {}
        oras = city.get("name") if isinstance(city, dict) else None
        judet = province.get("name") if isinstance(province, dict) else None
    # Imagine
    images = it.get("images") or []
    thumb = None
    if images and isinstance(images, list):
        first = images[0]
        thumb = first.get("large") or first.get("medium") or first.get("small") if isinstance(first, dict) else None
    slug = it.get("slug")
    src = f"{_BASE}/ro/oferta/{slug}" if slug else None

    return make_re_listing(
        platform="storia", external_id=str(it.get("id")) if it.get("id") is not None else None,
        tip_anunt=tip_anunt, tip_proprietate=tip_proprietate,
        camere=it.get("roomsNumber") or extract_rooms(title),
        suprafata_mp=parse_price(it.get("areaInSquareMeters")) or extract_surface(title),
        etaj=str(it.get("floorNumber")) if it.get("floorNumber") is not None else None,
        pret=pret, moneda=moneda, locatie_oras=oras, locatie_judet=judet,
        titlu=title, source_url=src, thumbnail_url=thumb,
    )


async def search_storia(filters: dict = {}) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url = _BASE + _category_path(tip_anunt, tip_proprietate)

    params = {}
    if filters.get("pret_min") is not None:
        params["priceMin"] = int(float(filters["pret_min"]))
    if filters.get("pret_max") is not None:
        params["priceMax"] = int(float(filters["pret_max"]))
    if filters.get("camere_min") is not None:
        params["roomsNumber"] = "[ONE,TWO,THREE,FOUR]"

    headers = build_headers({"Referer": _BASE + "/"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params or None, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[storia] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[storia] error: {exc}")
        return []

    # __NEXT_DATA__ JSON embed
    try:
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            data = json.loads(script.string)
            found = []
            _find_items(data, found)
            for it in found:
                try:
                    results.append(_parse_item(it, tip_anunt, tip_proprietate))
                except Exception:
                    continue
                if len(results) >= MAX_RESULTS:
                    break
    except Exception as exc:
        print(f"[storia] __NEXT_DATA__ error: {exc}")

    # Fallback HTML simplu
    if not results:
        for card in (soup.select("article") or soup.select('[data-cy="listing-item"]')):
            try:
                link = card.find("a", href=True)
                href = link["href"] if link else None
                if href and href.startswith("/"):
                    href = _BASE + href
                title_el = card.find(["h3", "h6", "p"]) or link
                titlu = title_el.get_text(strip=True) if title_el else ""
                if not titlu:
                    continue
                price_el = card.find(string=re.compile(r"€|EUR|lei", re.I))
                pret = parse_price(price_el) if price_el else None
                img = card.find("img")
                thumb = (img.get("src") or img.get("data-src")) if img else None
                results.append(make_re_listing(
                    platform="storia", tip_anunt=tip_anunt, tip_proprietate=tip_proprietate,
                    camere=extract_rooms(titlu), suprafata_mp=extract_surface(titlu),
                    pret=pret, moneda="EUR", titlu=titlu, source_url=href, thumbnail_url=thumb,
                ))
                if len(results) >= MAX_RESULTS:
                    break
            except Exception:
                continue

    print(f"[storia] {len(results)} anunturi ({tip_proprietate} {tip_anunt})")
    return results[:MAX_RESULTS]
