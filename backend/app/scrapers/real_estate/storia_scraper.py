"""Storia.ro — anunturi imobiliare. platform="storia".

Storia e Next.js: datele listingurilor se afla in scriptul __NEXT_DATA__.
Incercam intai un endpoint JSON, apoi parsam __NEXT_DATA__, apoi HTML simplu.
"""
import json
import re
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price,
    extract_rooms, extract_surface, make_re_listing, norm_city_slug,
)
from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES
from app.services.log_manager import log_manager

_BASE = "https://www.storia.ro"

_ROOMS_ENUM = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR"}


def _rooms_from_min(camere_min) -> Optional[str]:
    """camere_min -> valoarea reala pt param roomsNumber, ex "[THREE,FOUR]".

    Confirmat live 2026-07-05: storia filtreaza pe SET EXACT via forma cu paranteze
    roomsNumber=[X,Y]; forma simpla "roomsNumber=THREE" e IGNORATA (aceeasi distributie
    ca fara filtru). Pentru "minim N camere" trimitem enum-urile de la N in sus,
    plafonat la FOUR (semantica "4+", conform specificatiei). None daca invalid.
    """
    try:
        n = int(camere_min)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    n = min(n, 4)
    enums = [v for k, v in sorted(_ROOMS_ENUM.items()) if k >= n]
    return "[" + ",".join(enums) + "]" if enums else None


# Oras (valoarea din dropdown-ul de keyword) -> segment de path Storia. CONFIRMAT LIVE
# 2026-07-05 prin fetch-uri reale pe storia.ro: orasele care sunt resedinta de judet cu
# ACELASI nume merg singure (bucuresti/iasi/brasov/constanta/sibiu/arad); restul au nevoie
# de {judet}/{oras} (timis/timisoara, bihor/oradea, arges/pitesti). Cluj-Napoca foloseste
# DUBLU-cratima in slug-ul de oras (cluj/cluj--napoca) — confirmat din __NEXT_DATA__ storia.
# Cheile sunt slug-uri normalizate (fara diacritice, lowercase). Doar cele 10 orase din
# dropdown-ul de keyword (CITIES). Necunoscut -> fara segment (toata-romania, ca inainte).
_STORIA_LOCATION_PATHS = {
    "bucuresti": "bucuresti",
    "cluj-napoca": "cluj/cluj--napoca",
    "iasi": "iasi",
    "timisoara": "timis/timisoara",
    "brasov": "brasov",
    "constanta": "constanta",
    "sibiu": "sibiu",
    "oradea": "bihor/oradea",
    "arad": "arad",
    "pitesti": "arges/pitesti",
}


def _category_path(tip_anunt: str, tip_proprietate: str, locatie=None) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    tr = "inchiriere" if rent else "vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        prop = "casa"
    elif tp.startswith("teren"):
        prop = "teren"
    elif tp.startswith("comerc"):
        # CONFIRMAT LIVE 2026-07-06 pe 2 orase (Bucuresti + Cluj), HTTP 200 cu anunturi
        # comerciale reale: /ro/rezultate/vanzare/spatiu-comercial/{oras}. Slug SINGULAR;
        # "spatii-comerciale"/"birou"/"comercial" redirectau la apartament (?fromNoEstate=true).
        prop = "spatiu-comercial"
    else:
        prop = "apartament"
    base = f"/ro/rezultate/{tr}/{prop}"
    # Locatia e PATH (nu query) — vezi re_categories["storia"]. Adaugam segmentul de oras/judet
    # DOAR pentru orasele confirmate; altfel lasam fara (storia redirectioneaza la /toata-romania).
    loc_seg = _STORIA_LOCATION_PATHS.get(norm_city_slug(locatie)) if locatie else None
    return f"{base}/{loc_seg}" if loc_seg else base


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

    # VERIFY listed_at (IM-7): __NEXT_DATA__ ar putea expune dateCreated/pushedUpAt, dar semantica
    # (postare initiala vs repromovare) e neclara — neconfirmat, NU se conecteaza fara o sonda.
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
    url = _BASE + _category_path(tip_anunt, tip_proprietate, filters.get("locatie"))

    params = {}
    # Pret via campurile confirmate (priceMin/priceMax) — vezi re_categories["storia"].
    apply_re_filters("storia", filters, params, aliases=RE_FILTER_ALIASES)
    # Camere: format special cu paranteze [X,Y] (style "custom" in re_categories, aplicat aici).
    rooms_val = _rooms_from_min(filters.get("camere_min"))
    if rooms_val:
        params["roomsNumber"] = rooms_val

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("real_estate", "SCAN", f"Storia: {tip_proprietate} {tip_anunt}")
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params or None, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[storia] HTTP {resp.status_code}")
                log_manager.emit("real_estate", "ERR", f"Storia: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[storia] error: {exc}")
        log_manager.emit("real_estate", "ERR", f"Storia eroare: {str(exc)[:80]}")
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
    log_manager.emit("real_estate", "OK", f"Storia: {len(results)} anunturi gasite")
    return results[:MAX_RESULTS]
