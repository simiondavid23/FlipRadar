"""Kleinanzeigen.de — anunturi auto (categoria 216). platform="kleinanzeigen_auto".

KA-1 (markup masurat 2026-09-03, regresie aparuta intre 13 aug si 2 sep): site-ul a
inlocuit clasele semantice cu clase Tailwind generate, deci `article.aditem`,
`.aditem-main--middle--title`, `.aditem-main--middle--price-shipping--price` si
`.aditem-main--top--left` dau ZERO. Pagina raspunde in continuare 200, ~1 MB, fara
niciun marker de blocaj — datele sunt toate acolo, doar ambalajul s-a schimbat.

ANCORELE de azi, alese pentru ca NU sunt clase (clasele Tailwind se pot regenera la
orice build al lor):
  - cardul      : `<article data-adid="3496315529" data-href="/s-anzeige/...">`
  - link-ul     : atributul `data-href` (RELATIV, se prefixeaza cu _BASE)
  - titlul      : `<script type="application/ld+json">` din INTERIORUL cardului
  - imaginea    : acelasi JSON-LD (`contentUrl`), sau `<img>` din card

JSON-LD-ul per card e `@type: ImageObject`, NU Product/Offer: are `title`, `description`
si `contentUrl`, dar NU are pret, moneda sau locatie. Deci:
  - pretul   se ia din DOM, dintr-un element FRUNZA scurt care incepe cu cifre si
    contine €. Textul intreg al cardului NU merge: descrierea poate contine un pret
    momeala (masurat: "39.033,61€ Netto" intr-un card al carui pret cerut e 46.450 €).
    Cand cardul are doua preturi (cerut + taiat), primul in ordinea DOM e cel cerut.
  - locatia  se ia dintr-o frunza de forma "PLZ Oras" (5 cifre + nume).
  - titlul, la rezerva, e cea mai LUNGA ancora `/s-anzeige/` — nu prima: prima e
    insigna cu numarul de poze ("20", "15", "6").
"""
import json
import re
import urllib.parse

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
    safe_soup, thumb_from_img,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters

_BASE = "https://www.kleinanzeigen.de"

# Frunza de pret: incepe cu cifre, are separatoare de mii/zecimale si se termina in €.
# Ancorata la INCEPUT ca sa nu prinda proza din descriere ("... ausweisbar. 39.033,61€").
_RE_PRET = re.compile(r"^[\d][\d.\s]*(?:,\d+)?\s*€")
# "64283 Darmstadt", "81825 Trudering-Riem" — PLZ german + localitate.
_RE_LOC = re.compile(r"^\d{5}\s+[A-ZÄÖÜ][\w\-\. ]*$")
_MAX_FRUNZA = 40   # peste atat nu mai e o eticheta, e proza


def _ld_din_card(card) -> dict:
    """JSON-LD-ul dinauntrul unui card. {} la lipsa sau JSON invalid.

    NU se poate folosi `_common.extract_ld_offers`: aceea cauta `itemListElement[]`
    (o LISTA de produse la nivel de pagina), pe cand aici e cate un obiect singur per
    card, si de tip ImageObject — fara `offers`, deci fara pret.
    """
    tag = card.find("script", attrs={"type": "application/ld+json"})
    if tag is None or not tag.string:
        return {}
    try:
        date = json.loads(tag.string)
    except Exception:
        return {}
    return date if isinstance(date, dict) else {}


def _frunze(card):
    """Elementele fara copii-element: etichetele scurte (pret, locatie), nu containerele."""
    for el in card.find_all(True):
        if el.find(True) is None:
            yield el.get_text(" ", strip=True)


def _pret_din_card(card):
    """Primul pret in ordinea DOM. Al doilea, cand exista, e pretul TAIAT."""
    for text in _frunze(card):
        if len(text) <= _MAX_FRUNZA and _RE_PRET.match(text):
            return parse_price(text)
    return None


def _locatie_din_card(card):
    for text in _frunze(card):
        if len(text) <= _MAX_FRUNZA and _RE_LOC.match(text):
            return text
    return None


def _titlu_din_card(card, ld: dict) -> str:
    """JSON-LD `title` (nu `name` — asa il cheama ImageObject), altfel cea mai lunga
    ancora `/s-anzeige/`: prima e insigna cu numarul de poze."""
    titlu = (ld.get("title") or "").strip()
    if titlu:
        return titlu
    ancore = [a.get_text(" ", strip=True) for a in card.find_all("a", href=True)
              if "/s-anzeige/" in (a.get("href") or "")]
    ancore = [t for t in ancore if t]
    if ancore:
        return max(ancore, key=len)
    h2 = card.find("h2")
    return h2.get_text(" ", strip=True) if h2 else ""


async def search_kleinanzeigen_auto(query: str = "", make: str = "", model: str = "",
                                    filters: dict = {}, page: int = 1) -> list:
    filters = dict(filters or {})
    # Task 4 — marca ajunge la filtrul STRUCTURAT (autos.marke_s), nu doar in textul liber:
    # cautarea full-text Kleinanzeigen NU filtreaza dupa marca (confirmat live — "volkswagen
    # passat" ca text returna Renault/Opel/BMW/Fiat), pe cand marke_s garanteaza marca. Setam
    # doar daca nu e deja explicit in filters (ca sa nu suprascriem ceva trimis intentionat).
    if make and not filters.get("make"):
        filters["make"] = make
    # Categoria auto = c216. Keyword-ul (make + model + query) se prefixeaza in slug.
    keyword = " ".join(x for x in [(make or "").strip(), (model or "").strip(), (query or "").strip()] if x).strip()
    if keyword:
        url = f"{_BASE}/s-autos/{urllib.parse.quote(keyword)}/c216"
    else:
        url = f"{_BASE}/s-autos/c216"
    if page > 1:
        # Kleinanzeigen pagineaza in path: /s-autos/seite:N/.../c216
        url = url.replace("/s-autos/", f"/s-autos/seite:{page}/", 1)

    params = {}
    if filters.get("price_min") is not None or filters.get("price_max") is not None:
        lo = int(float(filters["price_min"])) if filters.get("price_min") is not None else ""
        hi = int(float(filters["price_max"])) if filters.get("price_max") is not None else ""
        params["priceType"] = "FIXED"
        params["minPrice"] = lo
        params["maxPrice"] = hi
    if filters.get("plz"):
        params["locationCity"] = filters["plz"]
    if filters.get("radius_km"):
        params["locationRadius"] = filters["radius_km"]
    # Campuri confirmate ca SUFIX de path "+autos.CAMP:VALOARE", adaugat DUPA /c216 (categoria
    # ramane ultimul segment de path inainte de sufix, conform exemplelor reale). Scanner-ul
    # trimite "fuel"/"body"/"km_max" pentru fuel_type/body_type/mileage_max.
    suffix = apply_confirmed_filters(
        "kleinanzeigen_auto", filters, params,
        aliases={"fuel_type": "fuel", "body_type": "body", "mileage_max": "km_max"})
    if suffix:
        url += suffix

    headers = build_headers({"Referer": _BASE + "/", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params or None, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[kleinanzeigen_auto] HTTP {resp.status_code}")
                return []
            soup = safe_soup(resp.text)
    except Exception as exc:
        print(f"[kleinanzeigen_auto] error: {exc}")
        return []

    # `data-adid` e contractul, nu clasele: clasele Tailwind se regenereaza la orice
    # build al site-ului, atributul a supravietuit rescrierii din 2026-09.
    cards = soup.select("article[data-adid]")
    if not cards:
        # Semnalul ajunge in `zgomot`-ul lui scraper_audit.py, deci un markup schimbat
        # din nou se vede ca BLOCAT/GOL cu motiv, nu ca o pagina goala tacuta.
        print("[kleinanzeigen_auto] 0 carduri: markup fara data-adid (site schimbat?)")
    for card in cards:
        try:
            ld = _ld_din_card(card)
            titlu = _titlu_din_card(card, ld)
            if not titlu:
                continue

            href = card.get("data-href")
            if not href:
                link = card.find("a", href=True)
                href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            pret = _pret_din_card(card)
            locatie = _locatie_din_card(card)

            thumb = thumb_from_img(card.find("img")) or (ld.get("contentUrl") or None)

            card_text = card.get_text(" ", strip=True)
            results.append(make_listing(
                platform="kleinanzeigen_auto", external_id=card.get("data-adid"), titlu=titlu,
                make=make or None, year=extract_year(titlu) or extract_year(card_text),
                km=extract_km(card_text), pret=pret, moneda="EUR",
                locatie=locatie or "Germania", source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[kleinanzeigen_auto] card parse error: {exc}")
            continue

    print(f"[kleinanzeigen_auto] {len(results)} anunturi (make='{make}', q='{query}')")
    return results[:MAX_LISTINGS]
