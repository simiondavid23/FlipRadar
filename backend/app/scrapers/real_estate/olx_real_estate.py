"""OLX.ro — anunturi imobiliare. platform="olx"."""
import re
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price,
    extract_rooms, extract_surface, detect_currency, make_re_listing,
)
from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES
from app.services.log_manager import log_manager

_BASE = "https://www.olx.ro"


def _olx_id(href: str):
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", href or "")
    return m.group(1) if m else None


def _olx_rooms_segment(camere_min) -> Optional[str]:
    """camere_min -> segment de path "{N}-camere/" (N=1..4, /4-camere/ = 4+). None daca invalid.

    CONFIRMAT LIVE 2026-07-05: filtrul de camere OLX merge ca PATH (/2-camere/ -> carduri SSR
    doar cu 2 camere). Query-ul search[filter_enum_rooms][0]=two intoarce o pagina JS FARA
    carduri SSR (0 rezultate) — cauza reala a filtrului "mort" din varianta veche. Match exact
    pana la 3; /4-camere/ include 4+.
    """
    try:
        n = int(camere_min)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return f"{min(n, 4)}-camere/"


def _olx_path(tip_anunt: str, tip_proprietate: str) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    suffix = "de-inchiriat" if rent else "de-vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        return f"/imobiliare/case-{suffix}/"
    if tp.startswith("teren"):
        return "/imobiliare/terenuri/"
    if tp.startswith("comerc"):
        return f"/imobiliare/spatii-comerciale-{suffix}/"
    # apartament / garsoniera
    return f"/imobiliare/apartamente-garsoniere-{suffix}/"


async def search_olx_real_estate(filters: dict = {}) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url = _BASE + _olx_path(tip_anunt, tip_proprietate)

    params = {"search[order]": "created_at:desc"}
    # Pret via campuri confirmate (search[filter_float_price:from/to]) — vezi re_categories.
    apply_re_filters("olx_real_estate", filters, params, aliases=RE_FILTER_ALIASES)
    # Camere: PATH /{N}-camere/ (confirmat live), inserat dupa categoria de baza. NU query param.
    rooms_seg = _olx_rooms_segment(filters.get("camere_min"))
    if rooms_seg:
        url = url.rstrip("/") + "/" + rooms_seg
    if filters.get("locatie"):
        url += f"q-{filters['locatie']}/"

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("real_estate", "SCAN", f"OLX Imobiliare: {tip_proprietate} {tip_anunt}")
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[olx_re] HTTP {resp.status_code}")
                log_manager.emit("real_estate", "ERR", f"OLX Imobiliare: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[olx_re] error: {exc}")
        log_manager.emit("real_estate", "ERR", f"OLX Imobiliare eroare: {str(exc)[:80]}")
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
            moneda = detect_currency(price_raw)

            loc_el = card.find(attrs={"data-testid": "location-date"})
            locatie = None
            if loc_el:
                raw = loc_el.get_text(" ", strip=True)
                locatie = raw.split("-")[0].strip() if "-" in raw else raw.strip()

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_re_listing(
                platform="olx", external_id=_olx_id(href),
                tip_anunt=tip_anunt, tip_proprietate=tip_proprietate,
                camere=extract_rooms(titlu), suprafata_mp=extract_surface(titlu),
                pret=pret, moneda=moneda, locatie_oras=locatie,
                titlu=titlu, source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[olx_re] card parse error: {exc}")
            continue

    print(f"[olx_re] {len(results)} anunturi ({tip_proprietate} {tip_anunt})")
    log_manager.emit("real_estate", "OK", f"OLX Imobiliare: {len(results)} anunturi gasite")
    return results[:MAX_RESULTS]
