"""Imobiliare.ro — anunturi imobiliare. platform="imobiliare"."""
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price, parse_int,
    extract_rooms, extract_surface, detect_currency, make_re_listing,
)
from app.services.log_manager import log_manager

_BASE = "https://www.imobiliare.ro"


def _path(tip_anunt: str, tip_proprietate: str) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    tr = "inchiriere" if rent else "vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        prop = "case"
    elif tp.startswith("teren"):
        prop = "terenuri"
    else:
        prop = "apartamente"
    return f"/{tr}-{prop}/"


async def search_imobiliare_ro(filters: dict = {}) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    path = _path(tip_anunt, tip_proprietate)
    if filters.get("locatie"):
        path += f"{str(filters['locatie']).strip().lower().replace(' ', '-')}/"
    url = _BASE + path

    params = {}
    if filters.get("pret_min") is not None:
        params["pret_min"] = int(float(filters["pret_min"]))
    if filters.get("pret_max") is not None:
        params["pret_max"] = int(float(filters["pret_max"]))
    if filters.get("camere_min") is not None:
        params["nr_camere"] = int(filters["camere_min"])
    if filters.get("suprafata_min") is not None:
        params["suprafata_min"] = int(filters["suprafata_min"])

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("real_estate", "SCAN", f"Imobiliare.ro: {tip_proprietate} {tip_anunt}")
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params or None, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[imobiliare] HTTP {resp.status_code}")
                log_manager.emit("real_estate", "ERR", f"Imobiliare.ro: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[imobiliare] error: {exc}")
        log_manager.emit("real_estate", "ERR", f"Imobiliare.ro eroare: {str(exc)[:80]}")
        return []

    cards = (
        soup.select("div.box-anunt")
        or soup.select("[data-id-anunt]")
        or soup.select(".listing-item")
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

            title_el = card.find(["h2", "h3"]) or card.find(class_=re.compile(r"titlu|title", re.I)) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            price_el = card.find(class_=re.compile(r"pret|price", re.I))
            price_raw = price_el.get_text(" ", strip=True) if price_el else card_text
            pret = parse_price(price_raw)
            moneda = detect_currency(price_raw)

            loc_el = card.find(class_=re.compile(r"locatie|location|zona|oras", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            an_el = re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", card_text)
            an = int(an_el.group(0)) if an_el else None

            etaj_m = re.search(r"etaj[ul]*\s*([\w/]+)", card_text, re.I)
            etaj = etaj_m.group(1) if etaj_m else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src") or img.get("data-original")) if img else None

            results.append(make_re_listing(
                platform="imobiliare", external_id=card.get("data-id-anunt"),
                tip_anunt=tip_anunt, tip_proprietate=tip_proprietate,
                camere=extract_rooms(titlu) or extract_rooms(card_text),
                suprafata_mp=extract_surface(titlu) or extract_surface(card_text),
                etaj=etaj, an_constructie=an, pret=pret, moneda=moneda,
                locatie_oras=locatie, titlu=titlu, source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[imobiliare] card parse error: {exc}")
            continue

    print(f"[imobiliare] {len(results)} anunturi ({tip_proprietate} {tip_anunt})")
    log_manager.emit("real_estate", "OK", f"Imobiliare.ro: {len(results)} anunturi gasite")
    return results[:MAX_RESULTS]
