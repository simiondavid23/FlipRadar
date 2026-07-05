"""AutoScout24.ro — anunturi auto. platform="autoscout24"."""
import json
import re
import urllib.parse

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_ld_offers,
    extract_year, extract_km, normalize_fuel, normalize_gearbox, make_listing,
    safe_soup,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters

_BASE = "https://www.autoscout24.ro"


def _extract_price_autoscout24(card, ld_offers=None, card_idx=0) -> tuple:
    """Returneaza (pret: float | None, moneda). Nu cade niciodata pe textul cardului.

    AutoScout24 expune pretul curat in atributul data-price de pe fiecare
    <article> (sursa primara, per-card — fara riscul de aliniere gresita) si in
    JSON-LD (rezerva, asociata pe pozitie).
    """
    # Strategy C — atributul data-price de pe card (cel mai sigur).
    raw = card.get("data-price")
    if not raw:
        el = card.select_one("[data-price]")
        raw = el.get("data-price") if el else None
    if raw:
        p = parse_price(str(raw))
        if p:
            return p, "EUR"

    # Strategy A — JSON-LD, asociat pe pozitie (rezerva).
    if ld_offers and card_idx < len(ld_offers):
        offer = ld_offers[card_idx]
        p = parse_price(str(offer.get("price") or ""))
        if p:
            return p, offer.get("currency") or "EUR"

    return None, "EUR"


def _autoscout24_offer_urls(soup) -> dict:
    """{listing_id: URL absolut de anunt} din __NEXT_DATA__.

    AutoScout24.ro e client-rendered (Next.js): HTML-ul static are pe fiecare card DOAR
    un link /dealerinfo/ (spre pagina dealerului), NU spre anunt. URL-urile reale de anunt
    sunt in props.pageProps.listings[].url ("/oferte/<slug>-<uuid>"), iar listings[].id ==
    atributul data-guid al cardului (confirmat live 20/20). Intoarce {} daca structura lipseste,
    caz in care scraper-ul nu produce URL-uri de anunt (mai bine nimic decat link de dealer).
    """
    nd = soup.select_one("script#__NEXT_DATA__")
    if not nd or not nd.string:
        return {}
    try:
        listings = json.loads(nd.string)["props"]["pageProps"]["listings"]
    except (ValueError, KeyError, TypeError):
        return {}
    urls = {}
    for lst in listings if isinstance(listings, list) else []:
        lid, path = (lst or {}).get("id"), (lst or {}).get("url")
        if lid and isinstance(path, str) and path:
            urls[lid] = path if path.startswith("http") else _BASE + path
    return urls


async def search_autoscout24(make: str = "", filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    path = f"/lst/{urllib.parse.quote((make or '').strip().lower())}" if make else "/lst/"
    url = _BASE + path

    params = {"sort": "standard", "desc": "0", "ustate": "N,U", "atype": "C"}
    if page > 1:
        params["page"] = page
    if filters.get("price_min") is not None:
        params["pricefrom"] = int(float(filters["price_min"]))
    if filters.get("price_max") is not None:
        params["priceto"] = int(float(filters["price_max"]))
    if filters.get("year_min") is not None:
        params["fregfrom"] = int(filters["year_min"])
    # Campuri tehnice confirmate (autoscout24: mileage_max->kmto, power_unit->powertype).
    # Scanner-ul trimite "km_max" pentru mileage_max. fuel/gearbox raman NECONFIRMATE (nu se adauga).
    apply_confirmed_filters("autoscout24", filters, params, aliases={"mileage_max": "km_max"})

    headers = build_headers({"Referer": _BASE + "/"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[autoscout24] HTTP {resp.status_code}")
                return []
            soup = safe_soup(resp.text)
    except Exception as exc:
        print(f"[autoscout24] error: {exc}")
        return []

    cards = (
        soup.select("article.cldt-summary-full-item")
        or soup.select('[data-testid="list-item"]')
        or soup.select("article")
    )
    ld_offers = extract_ld_offers(soup)  # rezerva pentru data-price
    nd_urls = _autoscout24_offer_urls(soup)  # {id: URL anunt} din __NEXT_DATA__ (vezi bug dealerinfo)
    for idx, card in enumerate(cards):
        try:
            link = card.find("a", href=True)
            # URL-ul de anunt vine EXCLUSIV din __NEXT_DATA__ (join pe data-guid == listings[].id):
            # linkul <a> din card duce la /dealerinfo/ (dealer), nu la anunt. Fara potrivire ->
            # sarim cardul (nu stocam un link de dealer ca si cum ar fi anuntul).
            guid = card.get("data-guid") or card.get("id")
            href = nd_urls.get(guid)
            if not href:
                continue

            title_el = card.find(["h2", "h3"]) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            # Pret din data-price (per-card) cu rezerva JSON-LD; niciodata din
            # textul cardului — acolo aparea overflow-ul (toate cifrele concatenate).
            pret, moneda = _extract_price_autoscout24(card, ld_offers, idx)

            loc_el = card.find(class_=re.compile(r"location|seller", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="autoscout24", external_id=card.get("data-guid") or card.get("id"),
                titlu=titlu, make=make or None,
                year=extract_year(titlu) or extract_year(card_text), km=extract_km(card_text),
                engine_type=normalize_fuel(card_text), gearbox=normalize_gearbox(card_text),
                pret=pret, moneda=moneda, locatie=locatie,
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[autoscout24] card parse error: {exc}")
            continue

    print(f"[autoscout24] {len(results)} anunturi (make='{make}')")
    return results[:MAX_LISTINGS]
