"""Autovit.ro — anunturi auto. platform="autovit"."""
import json
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price,
    extract_year, extract_km, normalize_fuel, normalize_gearbox, make_listing,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters, AUTO_PLATFORM_CATEGORIES
from app.services.log_manager import log_manager

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
    if make:
        params["search[filter_enum_make][0]"] = make
    if filters.get("price_min") is not None:
        params["search[filter_float_price:from]"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["search[filter_float_price:to]"] = int(float(filters["price_max"]))
    if filters.get("year_min") is not None:
        params["search[filter_float_year:from]"] = int(filters["year_min"])
    # Campuri tehnice confirmate (autovit: doar fuel_type). Scanner-ul trimite "fuel".
    apply_confirmed_filters("autovit", filters, params, aliases={"fuel_type": "fuel"})

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
            soup = BeautifulSoup(resp.text, "html.parser")
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
    log_manager.emit("auto_listings", "OK", f"Autovit: {len(results)} anunturi gasite")
    return results[:MAX_LISTINGS]
