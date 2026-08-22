"""VAL D runda 4a — extractoare de listare pe STARE, nu pe selectori CSS.

De ce exista fisierul asta. Scannerul de listari (`listing_scanner`) citeste o
pagina de reduceri prin selectori CSS declarati in descriptor: `card`, `link`,
`title`, `price_text`... Extractia R4 a masurat insa o familie intreaga de
magazine la care datele de produs ale LISTARII nu sunt in DOM, ci intr-un
payload structurat — si acolo un selector CSS n-are ce descrie:

    toolnation.nl   ld+json: un bloc care e o LISTA de `Product`
    bonami.ro       `__NEXT_DATA__`: initialCataloguePageState.blocks[].products[]
    cellini.ro      un array JS: `var products = [...]`
    ro.vivre.eu     payload RSC: initialData.items[]

Runda asta aduce DOAR structura care le primeste plus primul extractor
(toolnation). Helperii pentru `__NEXT_DATA__`, RSC si array JS nu se scriu aici
pe speculatie — fiecare intra cu domeniul lui, pe dump-ul lui.

CONTRACTUL, identic cu al caii CSS (`listing_scanner.extrage_carduri`): un
extractor primeste `(html, descriptor)` si intoarce o lista de dicturi cu EXACT
sase chei — `url`, `external_id`, `handle`, `title`, `price`, `compare_at` —
deja filtrate dupa aceleasi reguli (fara link sau fara pret valid => cardul se
SARE, niciodata nu se ghiceste). Restul scannerului — memoria R2, `_evalueaza`,
`Deal` — nu stie si nu trebuie sa stie din ce sursa a venit cardul.
"""
from __future__ import annotations

import json
import re
import urllib.parse

_BLOC_LDJSON = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)


def ldjson_product_list(html: str) -> list[dict] | None:
    """Blocul ld+json care e o LISTA de `Product`, sau None.

    NU primul bloc si NU concatenarea tuturor: pe listarea toolnation exista SAPTE
    blocuri — `WebSite`, `HardwareStore`, doua `BreadcrumbList`, `Organization`,
    inca un `WebSite` — si abia al saptelea e lista de produse. Un extractor care
    ar lua primul bloc ar citi `WebSite` si ar raporta zero produse, adica exact
    forma unei listari goale: „magazinul n-are reduceri azi", tacut si fals.

    `strict=False` la `json.loads` e treapta laxa adaugata la LOT5 (caractere de
    control brute in descrieri) — aceeasi rezerva, acelasi motiv.
    """
    for m in _BLOC_LDJSON.finditer(html or ""):
        try:
            d = json.loads(m.group(1), strict=False)
        except Exception:                                        # noqa: BLE001
            continue
        if (isinstance(d, list) and d
                and all(isinstance(o, dict) and o.get("@type") == "Product" for o in d)):
            return d
    return None


def _prima_oferta(produs: dict) -> dict | None:
    """`offers` e lista pe toolnation (o oferta per produs, masurat 24/24 pe ambele
    pagini), dar schema.org permite si un obiect singular — acceptam ambele forme,
    ca la `_aplatizeaza_oferte` de pe axa L."""
    oferte = produs.get("offers")
    if isinstance(oferte, dict):
        return oferte
    if isinstance(oferte, list):
        for o in oferte:
            if isinstance(o, dict):
                return o
    return None


def _pret_numeric(valoare) -> float | None:
    """`price` e NUMERIC pe toolnation (20.93, nu sir), dar schema.org il da adesea
    ca sir cu punct zecimal. Acceptam ambele; virgula zecimala NU se ghiceste —
    ar fi ambigua cu separatorul de mii — si iese None, adica se sare cardul."""
    if isinstance(valoare, (int, float)) and not isinstance(valoare, bool):
        return float(valoare)
    if isinstance(valoare, str):
        try:
            return float(valoare.strip())
        except ValueError:
            return None
    return None


def toolnation_ldjson(html: str, descriptor: dict) -> list[dict]:
    """toolnation.nl — `/aanbiedingen.html`, listare din ld+json.

    Masurat identic pe p1 (G2F-1/G2F-2) si p2 (LST-4): 24 de `Product` cu ACELEASI
    noua chei pe 24/24, fiecare cu o singura `Offer` cu opt chei pe 24/24, iar
    `p1 ∩ p2 = 0`. Doua lucruri din stare sunt DELIBERAT nefolosite:

      * `description` e IDENTIC pe toate cele 24 („Sale % bij Toolnation. Ontdek
        alle producten binnen deze categorie.") — e text de categorie, componenta
        partajata, nu descriere de produs. Titlul vine din `name`, distinct 24/24.
      * `availability` e `InStock` pe 24/24 pe AMBELE pagini. Nu se poate deosebi
        de o constanta de sablon (capcana dovedita pe vivre, unde PDP-urile emiteau
        `OutOfStock` pe produse pe care listarea proprie le dadea in stoc), deci
        stocul nu se citeste deloc: 24/24 e la fel de compatibil cu „tot catalogul
        e in stoc" cat si cu „campul e decorativ".

    `compare_at` iese None pe tot: in ld+json nu exista NICIO cheie de referinta
    (`highPrice`/`listPrice`/`was`), masurat pe ambele pagini. Domeniul califica
    deci doar pe R2 (minim istoric), acelasi regim ca buzzsneakers.
    """
    from app.services.listing_scanner import _external_id

    produse = ldjson_product_list(html)
    if not produse:
        return []                    # pagina fara bloc-lista = final de paginare

    iesire = []
    for p in produse:
        url = (p.get("url") or "").strip()
        if not url:
            continue                 # fara link nu e actionabil, ca pe calea CSS
        oferta = _prima_oferta(p)
        if oferta is None:
            continue
        pret = _pret_numeric(oferta.get("price"))
        if pret is None or pret <= 0:
            continue                 # fara pret valid se sare, niciodata nu se ghiceste
        iesire.append({
            "url": url,
            "external_id": _external_id(url),
            "handle": urllib.parse.urlsplit(url).path[:255],
            "title": (p.get("name") or "").strip()[:500],
            "price": pret,
            "compare_at": None,
        })
    return iesire


# Numele sunt CHEI de descriptor (`state_extractor`), deci se schimba doar odata
# cu registrul. Un nume necunoscut ridica `KeyError` in scanner, deliberat: o
# listare goala ar arata ca „azi n-are reduceri" si ar inchide tacit dealurile.
LISTING_STATE_EXTRACTORS = {
    "toolnation_ldjson": toolnation_ldjson,
}
