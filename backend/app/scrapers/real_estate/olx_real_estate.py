"""OLX.ro — anunturi imobiliare. platform="olx"."""
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price,
    extract_rooms, extract_surface, detect_currency, make_re_listing, norm_city_slug,
)
from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES
from app.services.log_manager import log_manager

_BASE = "https://www.olx.ro"


def _olx_id(href: str):
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", href or "")
    return m.group(1) if m else None


def _olx_path(tip_anunt: str, tip_proprietate: str) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    suffix = "de-inchiriat" if rent else "de-vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        return f"/imobiliare/case-{suffix}/"
    if tp.startswith("teren"):
        return "/imobiliare/terenuri/"
    if tp.startswith("comerc"):
        # CONFIRMAT LIVE 2026-07-06: categoria reala e /imobiliare/birouri-spatii-comerciale/
        # — o SINGURA categorie pt vanzare+inchiriere, FARA suffix. Vechiul
        # /imobiliare/spatii-comerciale-{de-vanzare|de-inchiriat}/ dadea HTTP 404.
        return "/imobiliare/birouri-spatii-comerciale/"
    # apartament / garsoniera
    return f"/imobiliare/apartamente-garsoniere-{suffix}/"


def _olx_build_url(filters: dict) -> tuple:
    """Construieste (url, params) pentru cautarea OLX Imobiliare. Functie pura, testabila.

    - baza: categoria din _olx_path(tip_anunt, tip_proprietate);
    - ORAS: daca filters["locatie"] e setat -> segment de path norm_city_slug(locatie) + "/".
      Confirmat live 2026-07-11 (sonda T3 bucuresti / T4 cluj-napoca / T5 +filter_float_price /
      T8 +q-text): path-ul de oras filtreaza corect si coexista cu pretul si cu q-.
    - CAMERE: NU se mai pune segment /N-camere/. Path-ul ar filtra EXACT N, dar semantica
      produsului e MINIM N => camerele se filtreaza LOCAL in post-filtrul scannerului (IM-1).
    - QUERY (cautare libera): daca filters["query"] e setat -> segment "q-" +
      norm_city_slug(query) + "/", DUPA oras (ordinea oras -> q- confirmata de sonda T8).
    - params: search[order]=created_at:desc + campurile confirmate (pret) via apply_re_filters.
    """
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url = _BASE + _olx_path(tip_anunt, tip_proprietate)
    if filters.get("locatie"):
        url = url.rstrip("/") + "/" + norm_city_slug(filters["locatie"]) + "/"
    if filters.get("query"):
        url = url.rstrip("/") + "/q-" + norm_city_slug(filters["query"]) + "/"

    params = {"search[order]": "created_at:desc"}
    # Pret via campuri confirmate (search[filter_float_price:from/to]) — vezi re_categories.
    apply_re_filters("olx_real_estate", filters, params, aliases=RE_FILTER_ALIASES)
    return url, params


async def search_olx_real_estate(filters: dict = {}) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url, params = _olx_build_url(filters)

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
