"""Autovit.ro — anunturi auto. platform="autovit"."""
import json
import re
import urllib.parse

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price,
    extract_year, extract_km, normalize_fuel, normalize_gearbox, make_listing,
    safe_soup, thumb_from_img,
    # SCRAPE-1b: plierea de diacritice s-a mutat in _common cand a ajuns sa fie
    # folosita si de facebook_auto_scraper (A5). Alias-ul pastreaza numele local.
    fold_auto as _fold_auto,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters, AUTO_PLATFORM_CATEGORIES
from app.services.log_manager import log_manager
from app.utils.listing_dates import iso_to_naive_local

_BASE = "https://www.autovit.ro"
# Categorii confirmate (auto_categories.py). Orice altceva -> fallback "autoturisme".
_AUTOVIT_CATEGORIES = {c["value"] for c in AUTO_PLATFORM_CATEGORIES["autovit"] if c.get("value")}


def _slug(text: str) -> str:
    return urllib.parse.quote((text or "").strip().lower().replace(" ", "-"))


def _extract_ld_prices(soup) -> list:
    """Extrage preturile curate din JSON-LD (schema.org OfferCatalog).

    Autovit NU pune pretul in markup-ul cardului (e randat separat / in alt
    container), dar il expune curat in blocul JSON-LD ca lista de Offer-uri,
    aliniata 1:1 si in aceeasi ordine cu cardurile <article data-id>.
    Returneaza [{"name", "price", "currency"}, ...] sau [] daca lipseste.
    """
    def _find_catalog(node):
        if isinstance(node, dict):
            if node.get("@type") == "OfferCatalog" and isinstance(node.get("itemListElement"), list):
                return node["itemListElement"]
            for value in node.values():
                found = _find_catalog(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = _find_catalog(value)
                if found is not None:
                    return found
        return None

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (ValueError, TypeError):
            continue
        catalog = _find_catalog(data)
        if not catalog:
            continue
        offers = []
        for entry in catalog:
            spec = (entry.get("priceSpecification") if isinstance(entry, dict) else None) or {}
            item = (entry.get("itemOffered") if isinstance(entry, dict) else None) or {}
            offers.append({
                "name": str(item.get("name") or ""),
                "price": spec.get("price"),
                "currency": spec.get("priceCurrency") or "EUR",
            })
        return offers
    return []


def _extract_autovit_dates(soup) -> dict:
    """DATE-2 — {node_id: (createdAt, bumpDate|None)} din `__NEXT_DATA__`.

    Autovit nu pune datele in markup-ul cardului, dar le expune in
    `props.pageProps.urqlState` — un dict al carui fiecare valoare are un camp `data`
    care e el insusi un STRING JSON (deci mai e nevoie de un `json.loads`). Dupa
    decodare, fiecare rezultat e un edge cu:
      * `node.id` — acelasi ID ca `data-id` de pe card (confirmat pe fixture, 32/32);
      * `node.createdAt` — prima publicare (`listed_at`);
      * `vas.bumpDate`   — ultima repromovare (`refreshed_at`), poate lipsi.

    Alinierea se face pe ID, NU pe pozitie: ordinea din `urqlState` coincide azi cu
    ordinea cardurilor, dar e o coincidenta pe care nu ne bazam (spre deosebire de
    `_extract_ld_prices`, unde alinierea 1:1 e verificata prin titlu).

    Functie PURA. `{}` la orice esec, un `data` nedecodabil se sare fara sa opreasca
    restul — apelantul ramane fara date, nu fara anunturi.
    """
    def _walk(node, out):
        if isinstance(node, dict):
            n = node.get("node")
            if isinstance(n, dict) and n.get("id") is not None and n.get("createdAt"):
                vas = node.get("vas")
                out[str(n["id"])] = (n.get("createdAt"),
                                     vas.get("bumpDate") if isinstance(vas, dict) else None)
            for value in node.values():
                _walk(value, out)
        elif isinstance(node, list):
            for value in node:
                _walk(value, out)

    try:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return {}
        urql = (json.loads(script.string).get("props") or {}).get("pageProps", {}).get("urqlState")
        if not isinstance(urql, dict):
            return {}
        rezultat: dict = {}
        for intrare in urql.values():
            brut = intrare.get("data") if isinstance(intrare, dict) else None
            if not isinstance(brut, str):
                continue
            try:
                _walk(json.loads(brut), rezultat)
            except (ValueError, TypeError):
                continue
        return rezultat
    except Exception as exc:
        print(f"[autovit] __NEXT_DATA__ dates parse error: {exc}")
        return {}


async def search_autovit(make: str = "", model: str = "", filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    cat = (filters.get("category") or "").strip()
    category = cat if cat in _AUTOVIT_CATEGORIES else "autoturisme"
    path = f"/{category}/"
    if make:
        path += f"{_slug(make)}/"
        if model:
            path += f"{_slug(model)}/"
    url = _BASE + path

    params = {}
    if page > 1:
        params["page"] = page
    # SCRAPE-AUDIT: scanner-ul trimite modelul in filters["model"], dar parametrul
    # functiei ramanea "" -> filtrul de model era ignorat COMPLET (BMW "Seria 3"
    # aducea toate BMW-urile) si model=None se salva pe listing.
    model = model or str((filters or {}).get("model") or "")
    if make:
        params["search[filter_enum_make][0]"] = make
    if filters.get("price_min") is not None:
        params["search[filter_float_price:from]"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["search[filter_float_price:to]"] = int(float(filters["price_max"]))
    if filters.get("year_min") is not None:
        params["search[filter_float_year:from]"] = int(filters["year_min"])
    # Campuri tehnice confirmate (autovit: doar fuel_type). Scanner-ul trimite "fuel".
    # SCRAPE-AUDIT: + body_type (confirmat in auto_categories; scanner-ul trimite "body").
    apply_confirmed_filters("autovit", filters, params,
                            aliases={"fuel_type": "fuel", "body_type": "body"})

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("auto_listings", "SCAN", f"Autovit: cautare {(make + ' ' + model).strip() or 'auto'}")
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[autovit] HTTP {resp.status_code}")
                log_manager.emit("auto_listings", "ERR", f"Autovit: HTTP {resp.status_code}")
                return []
            soup = safe_soup(resp.text)
    except Exception as exc:
        print(f"[autovit] error: {exc}")
        log_manager.emit("auto_listings", "ERR", f"Autovit eroare: {str(exc)[:80]}")
        return []

    cards = (
        soup.select("article[data-id]")
        or soup.select('[data-testid="listing-ad"]')
        or soup.select("article")
    )
    # Preturile curate vin din JSON-LD (aliniate 1:1 cu cardurile), pentru ca
    # markup-ul cardului nu contine pretul.
    ld_prices = _extract_ld_prices(soup)
    # DATE-2 — prima publicare + ultima repromovare, din acelasi HTML (fara request extra).
    date_map = _extract_autovit_dates(soup)
    for idx, card in enumerate(cards):
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
            # Pretul vine din JSON-LD, asociat pe pozitie si validat dupa titlu.
            # NU mai cadem niciodata pe parse_price(card_text) — acolo aparea
            # overflow-ul (tot textul cardului concatenat intr-un numar urias).
            pret, moneda = None, "EUR"
            offer = ld_prices[idx] if idx < len(ld_prices) else None
            if offer and offer["name"].strip().lower() == titlu.strip().lower():
                pret = parse_price(offer["price"])
                moneda = offer["currency"] or "EUR"

            loc_el = card.find(class_=re.compile(r"location", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = thumb_from_img(img) or None

            # DATE-2 — cheia e `data-id`, NU `idx`: spre deosebire de preturile JSON-LD,
            # datele nu sunt garantat aliniate pozitional cu cardurile.
            _creat, _bump = date_map.get(card.get("data-id") or "", (None, None))

            results.append(make_listing(
                platform="autovit", external_id=card.get("data-id"), titlu=titlu,
                make=make or None, model=model or None,
                year=extract_year(titlu) or extract_year(card_text),
                km=extract_km(card_text),
                engine_type=normalize_fuel(card_text),
                gearbox=normalize_gearbox(card_text),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
                listed_at=iso_to_naive_local(_creat),
                refreshed_at=iso_to_naive_local(_bump),
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[autovit] card parse error: {exc}")
            continue

    # SCRAPE-AUDIT: fara parametru server-side confirmat pentru model, filtram
    # LOCAL pe titlu (fold de diacritice pe ambele parti) — aceeasi abordare ca
    # relevanta mobile.de. Fail-open cand modelul e gol.
    if model:
        _mtok = _fold_auto(model).strip()
        if _mtok:
            results = [r for r in results
                       if _mtok in _fold_auto(r.get("titlu") or r.get("title") or "")]

    print(f"[autovit] {len(results)} anunturi (make='{make}')")
    log_manager.emit("auto_listings", "OK", f"Autovit: {len(results)} anunturi gasite")
    return results[:MAX_LISTINGS]
