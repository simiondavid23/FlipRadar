"""Imobiliare.ro — anunturi imobiliare. platform="imobiliare"."""
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price, parse_int,
    extract_rooms, extract_surface, detect_currency, make_re_listing, norm_city_slug,
)
from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES
from app.services.log_manager import log_manager

_BASE = "https://www.imobiliare.ro"


def _path(tip_anunt: str, tip_proprietate: str):
    """URL de categorie imobiliare.ro. RESCRIS 2026-07-06 dupa ce site-ul si-a schimbat
    structura (re-confirmat live pe TOATE cele 10 combinatii tip_anunt x tip_proprietate):
      - prefixul de chirie e PLURAL 'inchirieri' (vechiul 'inchiriere-...' da 404 => TOATE
        chiriile erau rupte, nu doar comercial);
      - casa = 'case-vile' (vechiul slug 'case' da 410 — slug complet nou, nu doar prefixul);
      - garsoniera are slug PROPRIU 'garsoniere' (inainte cadea pe 'apartamente');
      - apartament='apartamente', teren='terenuri', comercial='spatii-comerciale'.
    Returneaza None pentru combinatiile FARA categorie valida: /inchirieri-terenuri/ intoarce
    200 dar redirecteaza SILENTIOS la /inchirieri-spatii-comerciale/ (imobiliare.ro n-are
    'teren de inchiriat') -> None ca sa nu salvam spatii comerciale drept terenuri."""
    rent = (tip_anunt or "").lower().startswith("inchiri")
    tr = "inchirieri" if rent else "vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("garsonier"):
        prop = "garsoniere"
    elif tp.startswith("cas"):
        prop = "case-vile"
    elif tp.startswith("teren"):
        if rent:
            return None
        prop = "terenuri"
    elif tp.startswith("comerc"):
        prop = "spatii-comerciale"
    else:
        prop = "apartamente"
    return f"/{tr}-{prop}/"


def _passes_imob_filters(listing: dict, filters: dict) -> bool:
    """Post-filtru local pentru Imobiliare.ro.

    Imobiliare.ro NU aplica server-side pret/camere/suprafata: returneaza un set 'featured'
    scopat DOAR pe locatie (path), ignorand param-urii pret_min/pret_max/nr_camere/suprafata_min
    din URL (confirmat live). Filtram aici pe valorile deja extrase din card (pret/camere/
    suprafata_mp — vezi make_re_listing).

    TOLERANTA (la fel ca la Grupuri Facebook): daca listing-ul nu are o valoare cunoscuta pentru
    un criteriu, NU respinge din acel motiv — necunoscut = "nu se poate verifica".
    """
    # Pret — filtrele sunt in EUR (default keyword + moneda uzuala pe imobiliare); daca listing-ul
    # e in alta moneda, nu comparam numeric (toleranta).
    price = listing.get("pret")
    if price is not None and (listing.get("moneda") or "EUR").upper() == "EUR":
        try:
            pmin, pmax = filters.get("pret_min"), filters.get("pret_max")
            if pmin is not None and float(price) < float(pmin):
                return False
            if pmax is not None and float(price) > float(pmax):
                return False
        except (TypeError, ValueError):
            pass
    # Camere — camere_min = minim.
    rooms, cmin = listing.get("camere"), filters.get("camere_min")
    if rooms is not None and cmin is not None:
        try:
            if int(rooms) < int(cmin):
                return False
        except (TypeError, ValueError):
            pass
    # Suprafata — suprafata_min = minim.
    area, amin = listing.get("suprafata_mp"), filters.get("suprafata_min")
    if area is not None and amin is not None:
        try:
            if float(area) < float(amin):
                return False
        except (TypeError, ValueError):
            pass
    # Suprafata — suprafata_max = maxim (aceeasi toleranta la valori lipsa).
    amax = filters.get("suprafata_max")
    if area is not None and amax is not None:
        try:
            if float(area) > float(amax):
                return False
        except (TypeError, ValueError):
            pass
    return True


async def search_imobiliare_ro(filters: dict = {}) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    path = _path(tip_anunt, tip_proprietate)
    if not path:
        log_manager.emit("real_estate", "WARN",
            f"Imobiliare.ro: {tip_anunt}/{tip_proprietate} nu are categorie valida "
            f"(ex. teren de inchiriat redirecteaza la spatii comerciale) — scan omis, 0 rezultate.")
        return []
    if filters.get("locatie"):
        # FIX diacritice: normalizam slug-ul de oras ("București" -> "bucuresti", nu "bucurești").
        # Fara asta imobiliare.ro nu rezolva orasul si intoarce rezultate din alte judete (mixate).
        path += f"{norm_city_slug(filters['locatie'])}/"
    url = _BASE + path

    params = {}
    # Campuri confirmate: pret_min/pret_max/nr_camere/suprafata_min — vezi re_categories.
    apply_re_filters("imobiliare_ro", filters, params, aliases=RE_FILTER_ALIASES)

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

    # CONFIRMAT LIVE 2026-07-05 (fetch real pe imobiliare.ro): pagina nu mai are
    # div.box-anunt/[data-id-anunt]/article — cardurile sunt <div data-bi="product-basic">
    # cu atribute data-* semantice (data-name, data-price, data-bi-listing-currency,
    # data-list-id, data-area/data-city/data-county). Selectoarele vechi dadeau 0 rezultate.
    cards = soup.select('div[data-bi="product-basic"]')
    for card in cards:
        try:
            # Titlu: atributul data-name (curat); fallback pe heading.
            titlu = card.get("data-name") or ""
            if not titlu:
                h = card.find(["h2", "h3"])
                titlu = h.get_text(" ", strip=True) if h else ""
            if not titlu:
                continue

            link = card.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            # Pret + moneda din atribute (data-price = pretul afisat; currency dat de site).
            price_raw = (card.get("data-price") or card.get("data-item-price")
                         or card.get("data-bi-listing-price"))
            pret = parse_price(price_raw)
            moneda = (card.get("data-bi-listing-currency") or "EUR").upper()

            # Locatie din atribute (zona/oras/judet).
            locatie = card.get("data-area") or card.get("data-city") or card.get("data-county")

            card_text = card.get_text(" ", strip=True)
            an_el = re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", card_text)
            an = int(an_el.group(0)) if an_el else None
            etaj_m = re.search(r"etaj[ul]*\s*([\w/]+)", card_text, re.I)
            etaj = etaj_m.group(1) if etaj_m else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src") or img.get("data-original")) if img else None

            # VERIFY listed_at (IM-7): niciun atribut data-* parsat azi nu expune data postarii —
            # neconfirmat, NU se conecteaza fara o sonda.
            results.append(make_re_listing(
                platform="imobiliare", external_id=card.get("data-list-id") or card.get("data-url-id"),
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

    # Filtrare locala: imobiliare.ro ignora pret/camere/suprafata server-side (vezi
    # _passes_imob_filters) — eliminam aici din lista finala ce nu se potriveste criteriilor.
    filtered = [r for r in results if _passes_imob_filters(r, filters)]

    print(f"[imobiliare] {len(results)} brute -> {len(filtered)} dupa filtru local ({tip_proprietate} {tip_anunt})")
    log_manager.emit("real_estate", "OK", f"Imobiliare.ro: {len(filtered)} anunturi gasite")
    return filtered[:MAX_RESULTS]
