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

KLEIN-1 (fixture 2026-09-06, aceeasi structura ca la KA-1 — `article[data-adid]` = 27,
`aditem` = 0) adauga doua campuri care lipseau:
  - `listed_at` : data de pe card ("Heute, 13:25"), NEETICHETATA, deci data publicarii
    (regula DATE-1). Cardul nu spune nimic despre repromovare -> `refreshed_at` = None.
    Cele doua carduri TOP promovate n-au data deloc si raman cu None, dar NU se sar.
  - anul        : din eticheta "EZ MM/YYYY" (Erstzulassung), nu din `extract_year` pe
    textul cardului, care ia primul an plauzibil si nimereste in descriere.
"""
import json
import re
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    IMPERSONATE, MAX_LISTINGS, build_headers, parse_price, extract_year, extract_km, make_listing,
    safe_soup, thumb_from_img,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters
from app.utils.listing_dates import din_fus

_BASE = "https://www.kleinanzeigen.de"

# Frunza de pret: incepe cu cifre, are separatoare de mii/zecimale si se termina in €.
# Ancorata la INCEPUT ca sa nu prinda proza din descriere ("... ausweisbar. 39.033,61€").
_RE_PRET = re.compile(r"^[\d][\d.\s]*(?:,\d+)?\s*€")
# "64283 Darmstadt", "81825 Trudering-Riem" — PLZ german + localitate.
_RE_LOC = re.compile(r"^\d{5}\s+[A-ZÄÖÜ][\w\-\. ]*$")
_MAX_FRUNZA = 40   # peste atat nu mai e o eticheta, e proza

# ── KLEIN-1: data si anul de pe card ─────────────────────────────────────────────
# Data sta intr-un `div.text-onSurfaceNonessential` (confirmat pe fixture 2026-09-06:
# 25/27 carduri o au; cele doua carduri TOP promovate n-au deloc data). ACELASI
# container tine si locatia ("59192 Bergkamen"), iar in parintele comun cele doua se
# lipesc la `get_text()` fara spatiu ("59192 BergkamenHeute, 13:25"). De aceea nu
# indexam pozitional, ci luam primul text pe care `_parse_card_date` stie sa-l citeasca:
# o locatie nu se potriveste pe niciunul dintre cele trei formate de data.
# Clasa e semantica (rolul textului), nu de layout — `flex`/`mb-xsmall`/`p-medium` se
# schimba primele la un rebuild Tailwind, asa cum s-a intamplat la KA-1.
_SEL_META_CARD = "div.text-onSurfaceNonessential"

_RE_ORA = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_RE_DATA_DE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

# "EZ 03/2017" = Erstzulassung (prima inmatriculare) — sursa CORECTA a anului.
# Confirmat pe fixture 2026-09-06: 27/27 carduri au eticheta, in timp ce `extract_year`
# pe textul intreg al cardului greseste pe 4 din 27, fiindca ia primul an plauzibil din
# descriere ("...bis Mai 2031" -> 2031 in loc de EZ 2025; un Touran EZ 2011 -> 1996).
_RE_EZ = re.compile(r"\bEZ\s*(\d{1,2})/(\d{4})\b")

# TZ-1 — orele de pe kleinanzeigen.de sunt ore GERMANE; feed-ul le vrea in ora
# anunturilor (vezi utils/listing_dates). Vara diferenta e de o ora.
_FUS_SITE = "Europe/Berlin"


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


def _parse_card_date(text, now=None):
    """Data de pe cardul Kleinanzeigen -> datetime NAIV LOCAL (conventia Auto).

    Trei formate, toate masurate sau confirmate pe pagina de detaliu:
      * "Heute, 13:25"   -> azi la ora data (singura forma din fixture-ul 2026-09-06,
                            care e sortat dupa noutate);
      * "Gestern, 09:05" -> ieri la ora data;
      * "12.08.2026"     -> acea zi, ora 00:00 (forma confirmata in
                            `detail.py::fetch_kleinanzeigen_detail`).
    Ora lipsa -> 00:00, ca la ceilalti parseri de card din proiect. `now` e injectabil
    pentru teste. Orice altceva ("TOP", gol, None, ora imposibila) -> None, fara exceptie.

    DATE-1: data de pe card e NEETICHETATA, deci e data de PUBLICARE -> `listed_at`.
    Cardul nu expune nicio informatie de repromovare, deci `refreshed_at` ramane None.
    """
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    # TZ-1 — „Heute"/„Gestern" se judeca in ZIUA GERMANIEI, nu a masinii: intre
    # 00:00 si 01:00 ora Romaniei, la Berlin e inca ziua precedenta, deci un
    # „Heute, 23:40" ar fi primit data de maine. `now` intra naiv-local si se muta
    # in fusul sursa inainte de a decide ziua; rezultatul se intoarce prin `din_fus`.
    acum = (now or datetime.now()).astimezone().astimezone(ZoneInfo(_FUS_SITE))\
        .replace(tzinfo=None)

    m_ora = _RE_ORA.search(t)
    ora = int(m_ora.group(1)) if m_ora else 0
    minut = int(m_ora.group(2)) if m_ora else 0

    jos = t.lower()
    if jos.startswith("heute") or jos.startswith("gestern"):
        zi = acum - timedelta(days=1) if jos.startswith("gestern") else acum
        try:
            return din_fus(
                zi.replace(hour=ora, minute=minut, second=0, microsecond=0), _FUS_SITE)
        except ValueError:          # "Heute, 99:99"
            return None

    m = _RE_DATA_DE.search(t)
    if m:
        try:
            return din_fus(
                datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))), _FUS_SITE)
        except ValueError:          # "32.13.2026"
            return None
    return None


def _data_din_card(card, now=None):
    """Prima data citibila dintre textele `_SEL_META_CARD` ale cardului; None la TOP."""
    for el in card.select(_SEL_META_CARD):
        dt = _parse_card_date(el.get_text(" ", strip=True), now=now)
        if dt is not None:
            return dt
    return None


def _an_din_ez(text):
    """Anul din eticheta "EZ MM/YYYY" (Erstzulassung). None cand eticheta lipseste.

    Preferat lui `extract_year` pe textul cardului, care ia PRIMUL an plauzibil din
    text si nimereste in descriere (masurat: 4 greseli din 27 pe fixture).
    """
    m = _RE_EZ.search(text or "")
    if not m:
        return None
    an = int(m.group(2))
    return an if 1900 <= an <= 2100 else None


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
                make=make or None,
                # KLEIN-1: "EZ MM/YYYY" e anul REAL de inmatriculare; lantul vechi ramane
                # rezerva pentru cardurile fara eticheta.
                year=_an_din_ez(card_text) or extract_year(titlu) or extract_year(card_text),
                km=extract_km(card_text), pret=pret, moneda="EUR",
                locatie=locatie or "Germania", source_url=href, thumbnail_url=thumb,
                # KLEIN-1: data de pe card e data publicarii (neetichetata -> `listed_at`,
                # regula DATE-1). Cardurile TOP promovate n-au data deloc -> None.
                listed_at=_data_din_card(card), refreshed_at=None,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[kleinanzeigen_auto] card parse error: {exc}")
            continue

    print(f"[kleinanzeigen_auto] {len(results)} anunturi (make='{make}', q='{query}')")
    return results[:MAX_LISTINGS]
