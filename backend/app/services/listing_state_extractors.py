"""VAL D rundele 4a/4b — extractoare de listare pe STARE, nu pe selectori CSS.

De ce exista fisierul asta. Scannerul de listari (`listing_scanner`) citeste o
pagina de reduceri prin selectori CSS declarati in descriptor: `card`, `link`,
`title`, `price_text`... Extractia R4 a masurat insa o familie intreaga de
magazine la care datele de produs ale LISTARII nu sunt in DOM, ci intr-un
payload structurat — si acolo un selector CSS n-are ce descrie:

    toolnation.nl   ld+json: un bloc care e o LISTA de `Product`
    bonami.ro       `__NEXT_DATA__`: initialCataloguePageState.blocks[].products[]
    cellini.ro      un array JS: `var products = [...]`
    ro.vivre.eu     payload RSC: initialData.items[]

Runda 4a a adus structura plus primul extractor (toolnation); 4b a inchis lotul
cu celelalte trei. Fiecare helper de sursa — `ldjson_product_list`,
`rsc_initial_data`, `js_array`, `next_data` — a intrat abia odata cu domeniul lui,
pe dump-ul lui, niciunul pe speculatie. Sunt scrisi generic si refolosibili, dar
masurati pe un singur magazin fiecare: al doilea consumator ii poate cere ajustari,
si asta e normal, nu o regresie.

CONTRACTUL, identic cu al caii CSS (`listing_scanner.extrage_carduri`): un
extractor primeste `(html, descriptor)` si intoarce o lista de dicturi cu EXACT
sase chei — `url`, `external_id`, `handle`, `title`, `price`, `compare_at` —
deja filtrate dupa aceleasi reguli (fara link sau fara pret valid => cardul se
SARE, niciodata nu se ghiceste). Restul scannerului — memoria R2, `_evalueaza`,
`Deal` — nu stie si nu trebuie sa stie din ce sursa a venit cardul.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)

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
    from app.services.listing_scanner import _external_id, normalizeaza_imagine

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
        # IMG-1b — `image` e un STRING pe toate obiectele masurate, dar acceptam si
        # celelalte doua forme din schema (lista, ImageObject) ca sa nu depindem de o
        # observatie de o zi. Pe dump-ul IMG-1a valoarea e acelasi placeholder
        # (`/placeholder/default/toolnation-no-image-2_3.jpg`) pe 24/24, deci
        # rezultatul ASTEPTAT aici e None — nu e un bug, e ce publica magazinul.
        brut = p.get("image")
        if isinstance(brut, list):
            brut = brut[0] if brut else None
        if isinstance(brut, dict):
            brut = brut.get("url") or brut.get("contentUrl")
        iesire.append({
            "url": url,
            "external_id": _external_id(url),
            "handle": urllib.parse.urlsplit(url).path[:255],
            "title": (p.get("name") or "").strip()[:500],
            "price": pret,
            "compare_at": None,
            "image_url": normalizeaza_imagine(brut, urllib.parse.urlsplit(url).netloc),
        })
    return iesire


# ── infrastructura comuna celor trei surse de mai jos ───────────────────────
def _baza(descriptor: dict) -> str:
    """`https://<gazda>` derivat din URL-ul listarii.

    Trei dintre extractoare construiesc linkul PDP din stare (slug sau id+slug) si
    au deci nevoie de o gazda. O luam din `descriptor["url"]`, nu dintr-o constanta
    in cod si nici din cheia de registru: cheia poate fi fara `www` acolo unde
    magazinul serveste CU `www` (cellini), iar o constanta ar fi a doua sursa de
    adevar, care se poate desincroniza tacit de descriptor.
    """
    p = urllib.parse.urlsplit(descriptor["url"])
    return f"{p.scheme}://{p.netloc}"


def _card(url: str, titlu: str, pret: float, compare, image_url=None) -> dict:
    """Cardul normalizat, in forma EXACTA a caii CSS (`extrage_carduri`).

    Aici traiesc si cele doua filtre pe care calea CSS le aplica dupa citire:
    referinta <= 0 devine None (nu se raporteaza o reducere din nimic), iar
    trunchierile de lungime sunt aceleasi — `handle` 255, `title` 500.

    IMG-1b — `image_url` trece prin ACELASI normalizator ca pe calea CSS, cu gazda
    luata din URL-ul deja construit al produsului. Doua motive: valorile din stare pot
    fi la fel de relative ca cele din DOM, si respingerea placeholderelor trebuie sa
    fie o singura regula, nu doua care se pot desincroniza (toolnation serveste un
    placeholder prin `image`, exact cazul pe care regula il prinde).
    """
    from app.services.listing_scanner import _external_id, normalizeaza_imagine

    if compare is not None and compare <= 0:
        compare = None
    gazda = urllib.parse.urlsplit(url).netloc
    return {
        "url": url,
        "external_id": _external_id(url),
        "handle": urllib.parse.urlsplit(url).path[:255],
        "title": (titlu or "").strip()[:500],
        "price": pret,
        "compare_at": compare,
        "image_url": normalizeaza_imagine(image_url, gazda),
    }


# ── ro.vivre.eu — payload RSC (`self.__next_f`) ─────────────────────────────
def rsc_initial_data(html: str) -> dict | None:
    """`initialData` din payload-ul RSC al unui Next.js modern, sau None.

    Payload-ul e spart in bucati emise ca `self.__next_f.push([1,"..."])`, fiecare
    un SIR JS escapat. Se decodeaza fiecare bucata cu `raw_decode` (nu cu un regex:
    sirurile contin ghilimele escapate si `\\n`-uri) si abia apoi se CONCATENEAZA —
    masurat pe vivre, `initialData` cade la granita dintre bucati, deci o parsare
    bucata-cu-bucata l-ar rata. 23 de bucati pe dump-ul LST-2.
    """
    dec = json.JSONDecoder()
    marca = "self.__next_f.push([1,"
    bucati, poz = [], 0
    while True:
        i = (html or "").find(marca, poz)
        if i < 0:
            break
        try:
            j = html.index('"', i + len(marca) - 1)
            valoare, capat = dec.raw_decode(html, j)
            bucati.append(valoare)
            poz = capat
        except Exception:                                        # noqa: BLE001
            poz = i + len(marca)          # bucata nedecodabila: se sare, nu se cade
    payload = "".join(b for b in bucati if isinstance(b, str))
    i = payload.find('"initialData"')
    if i < 0:
        return None
    try:
        obj, _ = dec.raw_decode(payload, payload.index("{", i + len('"initialData"')))
    except Exception:                                            # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


def vivre_rsc(html: str, descriptor: dict) -> list[dict]:
    """ro.vivre.eu — `/products?qf=discount`, listare din payload-ul RSC.

    REFERINTA E `lowestPrice`, NU `originalPrice`. Obiectul `price` are amandoua, si
    al doilea e o momeala: masurat pe dump-ul LST-2, `originalPrice` e **0 pe 19 din
    24** de produse, in timp ce `lowestPrice` e populat pe 24/24 si strict peste
    pretul curent pe 24/24. Pe cele cinci unde `originalPrice` e nenul, el e si mult
    mai mare (3586,99 fata de 1799,99 `lowestPrice`, la un pret de 1151,99), deci
    l-am fi raportat ca o marja umflata. `discountPercentage` din stare se
    calculeaza tot fata de `lowestPrice`, ceea ce confirma alegerea.

    `lowestPrice` e si Omnibus-ul: i18n-ul paginii il eticheteaza verbatim „Cel mai
    mic pret in ultimele 30 de zile" — singurul domeniu din familie cu fereastra
    scrisa explicit, de unde `reference_kind: min30`.

    Linkul se CONSTRUIESTE `/p-{id}/{slug}` si e verificat: coincide cu cele 24 de
    ancore randate de pagina (ele poarta in plus `?ch_type=0&ch_id=products`, sufix
    de urmarire pe care nu-l reproducem — `external_id` ia oricum doar calea).

    Stocul NU se citeste, desi starea are `stock` numeric si `flags.inStock`:
    domeniul poarta deja `ldjson_availability: "untrusted"` fiindca PDP-urile lui
    contrazic listarea proprie, iar aici `inStock` e True pe 24/24 — acelasi tipar
    de constanta suspecta ca la toolnation.
    """
    date = rsc_initial_data(html)
    if not date or not isinstance(date.get("items"), list):
        return []
    baza = _baza(descriptor)
    iesire = []
    for it in date["items"]:
        if not isinstance(it, dict):
            continue
        pid, slug = it.get("id"), it.get("slug")
        if not pid or not slug:
            continue
        p = it.get("price") or {}
        pret = _pret_numeric(p.get("price"))
        if pret is None or pret <= 0:
            continue
        # IMG-1b — `photo.main.thumb`, singura cheie image-like a produsului (IMG-1a2).
        foto = it.get("photo")
        principala = foto.get("main") if isinstance(foto, dict) else None
        thumb = principala.get("thumb") if isinstance(principala, dict) else None
        iesire.append(_card(f"{baza}/p-{pid}/{slug}", it.get("name"), pret,
                            _pret_numeric(p.get("lowestPrice")), thumb))
    return iesire


# ── cellini.ro — array JS (`var products = [...]`) ──────────────────────────
def js_array(html: str, nume_variabila: str) -> list | None:
    """Array-ul JS atribuit lui `var <nume> = [...]`, taiat prin numarare de paranteze.

    Nu cu regex: obiectele contin `[` si `]` in siruri (descrieri, JSON imbricat),
    deci o potrivire lacoma sau lenesa ar taia gresit. Numararea porneste de la
    prima paranteza dupa `=` si se opreste la inchiderea ei.
    """
    marca = f"var {nume_variabila} = "
    if not html or marca not in html:
        return None
    i = html.index(marca) + len(marca)
    adanc = 0
    for k in range(i, len(html)):
        if html[k] == "[":
            adanc += 1
        elif html[k] == "]":
            adanc -= 1
            if adanc == 0:
                try:
                    return json.loads(html[i:k + 1], strict=False)
                except Exception:                                # noqa: BLE001
                    return None
    return None


def _titlu_din_slug(fisier: str) -> str:
    """Numele produsului din slug-ul fisierului: cratime -> spatii, `.html` taiat.

    DECIZIE DE DESIGN (cellini): starea are `name: null` pe 48/48 si `metatitle` /
    `subtitle` goale, deci nu exista titlu de citit. Alternativa era `code` (SKU-ul,
    „AD_CT18CO27927") — stabil, dar in feed cititorul ar vedea un cod de inventar in
    loc de un produs. Slug-ul e lizibil si vine din aceeasi sursa ca linkul.
    Sufixul de cod din slug NU se taie: n-avem un criteriu masurat pentru unde se
    termina numele, iar a ghici ar rupe titluri.
    """
    baza = re.sub(r"\.html?$", "", (fisier or "").strip())
    return baza.replace("-", " ").strip().capitalize()


def cellini_js(html: str, descriptor: dict) -> list[dict]:
    """cellini.ro — `/bijuterii/filtre/promo-promotii`, listare din `var products`.

    PRETUL E SPART IN DOUA in stare: `price` e intregul de lei (14739) si
    `decimalprice` e sirul de bani ("00"). Se recompun, ca sa nu se piarda tacit
    banii. Referinta, `oldprice`, e deja sir zecimal ("17340.00") si e nenula pe
    48/48 — pagina e o listare de promotii, prin definitie.

    DOM-ul NU e o alternativa: `.price-product` da „17.340 , 00 Lei (-15%) 14.739 ,
    00 Lei" — ambele preturi intr-un nod, cu spatii in jurul virgulei, deci un parser
    de text le-ar concatena in gunoi. Starea e sursa curata aici.

    LINKUL: `url` din stare e un nume de fisier GOL, pe care `<base href=".../">` il
    ancoreaza la RADACINA. Sonda LST-4 (C6) a masurat ca forma-radacina raspunde 200
    fara redirect si e SELF-CANONICAL, in timp ce `/bijuterii/filtre/<fisier>`
    canonicalizeaza spre categorie. Radacina e deci calea corecta — si, fiindca
    `external_id` e sha1 pe CALE, ea decide identitatea produsului.
    """
    produse = js_array(html, "products")
    if not produse:
        return []
    baza = _baza(descriptor)
    iesire = []
    for p in produse:
        if not isinstance(p, dict):
            continue
        fisier = (p.get("url") or "").strip().lstrip("/")
        if not fisier:
            continue
        intreg = _pret_numeric(p.get("price"))
        if intreg is None:
            continue
        bani = str(p.get("decimalprice") or "0")[:2] or "0"
        pret = _pret_numeric(f"{int(intreg)}.{bani.zfill(2)}")
        if pret is None or pret <= 0:
            continue
        # IMG-1b — `picture` e un dict de variante de marime; `thumb` inaintea lui
        # `mini` fiindca e cea mai mare dintre cele doua masurate. `brand_picture` si
        # `secondPicture` sunt DELIBERAT ignorate: prima e sigla marcii, a doua e o
        # poza de ambalaj (`punga_cellini.jpg`) — niciuna nu e produsul.
        poza = p.get("picture") if isinstance(p.get("picture"), dict) else {}
        # IMG-1b — titlul vine acum din `product`. Vezi docstring-ul de mai sus.
        titlu = (p.get("product") or p.get("master_product") or "").strip()
        iesire.append(_card(f"{baza}/{fisier}", titlu or _titlu_din_slug(fisier), pret,
                            _pret_numeric(p.get("oldprice")),
                            poza.get("thumb") or poza.get("mini")))
    return iesire


# ── bonami.ro — `__NEXT_DATA__` ─────────────────────────────────────────────
def next_data(html: str) -> dict | None:
    """Obiectul `__NEXT_DATA__`, sau None. Un singur bloc, JSON curat."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1), strict=False)
    except Exception:                                            # noqa: BLE001
        return None


def _suma_units_scale(obiect) -> float | None:
    """`{"amount": {"scale": 2, "units": 57290}}` -> 572.90.

    Forma bonami: banii ca INTREG plus exponentul zecimal, ca sa nu existe erori de
    virgula mobila in transport. `round` la final fiindca `units / 10**scale` poate
    da 572.9000000000001 pe alte valori.
    """
    if not isinstance(obiect, dict):
        return None
    suma = obiect.get("amount")
    if not isinstance(suma, dict):
        return None
    unitati, scara = suma.get("units"), suma.get("scale")
    if not isinstance(unitati, (int, float)) or not isinstance(scara, int):
        return None
    return round(float(unitati) / (10 ** scara), 2)


# IMG-1c — sablonul CDN al imaginilor bonami, derivat pe pagina de PRODUS.
#
# Starea listarii poarta doar hash-uri, deci sonda IMG-1c a deschis doua PDP-uri si a
# cautat acolo hash-urile produsului: 74 de URL-uri, TOATE de forma de mai jos, zero
# exceptii. Sursele care confirma primul URL sunt cele autoritative ale paginii —
# `og:image` si `image` din ld+json (`@type=Product`, o lista in ordinea din
# `productImages`).
#
# Sardul NU e o constanta: cele doua segmente hex de dinaintea numelui de fisier sunt
# chiar primele doua perechi ALE hash-ului (`ed39fe55…` -> `/ed/39/`). Verificat pe
# 74/74. O derivare care ar trata `/ed/39/` ca literal ar lipi hash-ul unui produs de
# sardul altuia si ar produce 404-uri — greseala e usor de facut, sonda a facut-o
# prima data.
#
# 600x600 e dimensiunea pe care PDP-ul o pune el insusi in `<img src>`; cardul de feed
# afiseaza imaginea pe 168 px inaltime, deci e amplu si nu platim un 1200x1200 degeaba.
# CDN-ul serveste si `.webp`, dar `.jpeg` e forma din `og:image`/ld+json, deci si cea
# mai probabil stabila.
#
# Verificat LIVE la implementare: trei HEAD-uri pe primele trei produse din dump-ul de
# listare -> 200 + `image/jpeg` pe toate trei.
_BONAMI_IMG = "https://1.bonami.ro/images/fit-crop-fill/{h0}/{h1}/{hash}-600x600.jpeg"


def _bonami_imagine(p: dict) -> str | None:
    """URL-ul imaginii principale din hash, sau None.

    `imageHash` intai, `productImages[0].hash` ca rezerva — la produsele masurate
    coincid, dar sunt campuri diferite si nimic nu garanteaza ca vor coincide mereu.

    Forma hash-ului se VERIFICA (40 de hex): un camp lipsa, gol sau de alt tip ar
    produce altfel un URL sintactic valid care da 404, iar feed-ul ar arata rame
    goale in loc sa cada pe placeholderul „FARA FOTO". Mai bine None decat un URL rupt.
    """
    hash_ = p.get("imageHash") or next(
        (i.get("hash") for i in (p.get("productImages") or [])
         if isinstance(i, dict) and i.get("hash")), None)
    if not isinstance(hash_, str) or not re.fullmatch(r"[0-9a-f]{40}", hash_):
        return None
    return _BONAMI_IMG.format(h0=hash_[:2], h1=hash_[2:4], hash=hash_)


def bonami_next(html: str, descriptor: dict) -> list[dict]:
    """bonami.ro — `/c/oferte-speciale-si-reduceri`, listare din `__NEXT_DATA__`.

    Produsele stau in `initialCataloguePageState.blocks[*].products[]`, si accentul
    e pe STEA: `blocks` are sapte elemente, iar `products` apare pe TREI dintre ele
    (indicii 4, 5, 6, cate 16 = 48). Celelalte patru sunt breadcrumbs, banner si
    carusel — se sar curat. Un extractor care ar lua primul bloc cu produse ar
    raporta 16 din 48, tacut.

    Pagina-UNICA, masurat: `nextPagePath` e None, nu exista `rel=next` si niciun
    href cu `?page=`, iar `productList` (magazinul de infinite-scroll) e GOL la
    randare — de unde `max_pages: 1` in registru.

    Linkul se CONSTRUIESTE `/p/<slug>`: DOM-ul listarii n-are NICIO ancora de produs
    (masurat: zero `a[href^="/p/"]`), fiindca grila e hidratata client-side. Forma
    `/p/<slug>` vine de pe axa L, unde a fost confirmata pe viu (200, fara redirect).

    `retailPrice` e referinta si e in aceeasi forma `units`/10^`scale` ca pretul
    platit. Stocul (`availability.usableStock`, numeric!) NU se citeste: schema de
    descriptor n-are camp de stoc pe stare, iar a-l inventa aici ar fi o conventie
    per-domeniu nescrisa nicaieri.
    """
    date = next_data(html)
    if not date:
        return []
    try:
        blocuri = date["props"]["pageProps"]["initialCataloguePageState"]["blocks"]
    except (KeyError, TypeError):
        return []
    if not isinstance(blocuri, list):
        return []

    baza = _baza(descriptor)
    iesire = []
    for bloc in blocuri:
        if not isinstance(bloc, dict):
            continue
        produse = bloc.get("products")
        if not isinstance(produse, list):
            continue                      # breadcrumbs / banner / carusel: se sar
        for p in produse:
            if not isinstance(p, dict):
                continue
            slug = (p.get("slug") or "").strip()
            if not slug:
                continue
            pret = _suma_units_scale(p.get("customerPrice"))
            if pret is None or pret <= 0:
                continue
            # IMG-1c — poza se CONSTRUIESTE din hash, vezi `_bonami_imagine` si
            # sablonul de mai sus. Pagina de listare tot n-are URL-uri de imagine
            # (IMG-1a2: hash-ul apare de doua ori, ambele in JSON, in zero atribute
            # `src`/`srcset`), dar nici nu mai e nevoie sa aiba.
            iesire.append(_card(f"{baza}/p/{slug}", p.get("name"), pret,
                                _suma_units_scale(p.get("retailPrice")),
                                _bonami_imagine(p)))
    return iesire


# -- flip.ro - `__NEXT_DATA__`, cache de react-query --------------------------
def _identitate_exacta(card: dict, url: str) -> dict:
    """STATE-1 - `external_id`/`handle` pe cale + QUERY, pentru flip.ro.

    `_external_id` din scanner hasheaza doar CALEA, si pe buna dreptate: acolo
    query-ul e de obicei `?utm_source=...`, iar acelasi produs ajuns pe doua rute
    trebuie sa fie UN deal. La flip e invers, si registrul o spune deja prin
    `url_identity: "exact"` (LOT1): starea unitatii - `?shape=Excelent` - face
    parte din identitatea produsului. Acelasi model in doua grade are ACEEASI cale
    si doua preturi diferite.

    Fara garda asta, cele doua grade ar primi acelasi `external_id`, iar al doilea
    ar fi sarit de garda SCAN-1 (produs deja vazut in scanul asta) - adica
    jumatate de catalog ar disparea TACUT, si ar disparea tocmai varianta pe care
    ordinea paginii o pune a doua.

    Pe dump-ul LST-D3 cele 32 de cai sunt distincte, deci coliziunea nu se vede pe
    o singura pagina; ea apare intre pagini (604 de produse, 19 pagini). Garda e
    deci scrisa pe forma masurata a datelor si pe conventia de registru, nu pe o
    coliziune observata - iar testul o fixeaza explicit.
    """
    parti = urllib.parse.urlsplit(url)
    coada = f"?{parti.query}" if parti.query else ""
    cale_si_query = (parti.path.rstrip("/").lower() or "/") + coada
    card["external_id"] = "lst:" + hashlib.sha1(
        cale_si_query.encode("utf-8")).hexdigest()
    card["handle"] = (parti.path + coada)[:255]
    return card


def flip_next(html: str, descriptor: dict) -> list[dict]:
    """flip.ro - `/magazin/`, listare din cache-ul react-query al lui `__NEXT_DATA__`.

    Calea, verbatim din `dumps_lstd3/flip.ro_p1.html`:

        props.pageProps.dehydratedState.queries[*].state.data.data.productsPage

    - un array PLAT de 32 de obiecte (`total: 604`, deci 19 pagini). Cheile unui
    produs, tot verbatim:

        price                 1429.99   (float, RON)
        retailPrice           2250      (pretul unitatii NOI a aceluiasi model)
        previousPrice         1429.99   (EGAL cu `price` pe 32/32 - NU se citeste)
        lowestPriceOfTheYear  false     (constant pe 32/32 - NU se citeste)
        currency              "RON"
        naming.title          "Apple iPhone 13, Midnight, 128 GB, Excelent"
        pdpUrl                absolut, cu `?shape=Excelent`
        imagePath             absolut, pe cdn.flip.ro
        spec.shape            "EXCELENT"

    TREI decizii, fiecare platita de o masuratoare:

    1. Query-ul NU se ia dupa indice. `queries` are doua elemente si abia primul
       are `productsPage`; al doilea (`plp-promotional-cards`) are `state.data`
       None. Azi indicele 0 ar nimeri - dar ordinea unui cache de react-query nu e
       un contract, iar ziua in care se inverseaza n-ar da o eroare, ci zero
       produse, adica "magazinul n-are reduceri". Se alege deci query-ul al carui
       `state.data.data.productsPage` E o lista.

    2. `previousPrice` NU e referinta. E egal cu `price` pe 32/32 - exact capcana
       constantei de la vivre. Citit ca `compare_at`, ar produce reduceri de 0%
       pe tot catalogul. La fel `lowestPriceOfTheYear`, constant `false`.

    3. `compare_at = retailPrice` doar cand e > `price`. Semantica e "pretul
       unitatii NOI a aceluiasi model", aceeasi decizie ca "NOU" la eMAG si "Nou:"
       la altex; de aceea `reference_kind: "nemarcat"`, nu `min30`. Pe dump
       `retailPrice` exista pe 32/32 dar e > `price` doar pe 27/32 - restul au
       `retailPrice: 0`, deci fara garda ar fi iesit o "reducere" de la zero.

    Gradul ramane in titlu, si vine gratis: `naming.title` il are deja ca sufix.
    """
    date = next_data(html)
    if not date:
        return []
    try:
        interogari = date["props"]["pageProps"]["dehydratedState"]["queries"]
    except (KeyError, TypeError):
        return []
    if not isinstance(interogari, list):
        return []

    produse = None
    for interogare in interogari:
        if not isinstance(interogare, dict):
            continue
        stare = (interogare.get("state") or {}).get("data")
        interior = stare.get("data") if isinstance(stare, dict) else None
        candidat = interior.get("productsPage") if isinstance(interior, dict) else None
        if isinstance(candidat, list):
            produse = candidat
            break
    if produse is None:
        return []

    iesire = []
    for produs in produse:
        if not isinstance(produs, dict):
            continue
        url = (produs.get("pdpUrl") or "").strip()
        if not url:
            continue
        pret = _pret_numeric(produs.get("price"))
        if pret is None or pret <= 0:
            continue
        referinta = _pret_numeric(produs.get("retailPrice"))
        if referinta is not None and referinta <= pret:
            referinta = None            # `retailPrice: 0`, sau egal cu pretul
        titlu = ((produs.get("naming") or {}).get("title") or "").strip()
        iesire.append(_identitate_exacta(
            _card(url, titlu, pret, referinta, produs.get("imagePath")), url))
    return iesire


# -- marionnaud.ro - <script type="application/json"> (SAP Commerce/Spartacus) --
_BLOC_JSON = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', re.I | re.S)


def _cauta_search_model(radacina, adancime: int = 0) -> list | None:
    """Primul `searchModel.products` care e lista, oriunde in structura.

    Se coboara in adancime fiindca `searchModel` sta sub o cheie care e un ID de
    componenta CMS (`e2-breadcrumb-pageBreadCrumbs$`) - un literal pe care nu-l
    putem lega in cod fara sa-l facem sa se rupa la prima reasezare a paginii.
    """
    if adancime > 8:
        return None
    if isinstance(radacina, dict):
        model = radacina.get("searchModel")
        if isinstance(model, dict) and isinstance(model.get("products"), list):
            return model["products"]
        for valoare in radacina.values():
            gasit = _cauta_search_model(valoare, adancime + 1)
            if gasit is not None:
                return gasit
    elif isinstance(radacina, list):
        for element in radacina[:20]:
            gasit = _cauta_search_model(element, adancime + 1)
            if gasit is not None:
                return gasit
    return None


def marionnaud_json(html: str, descriptor: dict) -> list[dict]:
    """marionnaud.ro - `/promotii/c/F`, listare din blocul `application/json`.

    Pagina are UN singur `<script type="application/json">`, FARA atribut `id`, si
    cheile lui de radacina sunt nume de componente Spartacus. `searchModel` nu e
    la radacina, ci sub prima dintre ele - calea verbatim din
    `dumps_lstd4/marionnaud.ro_p1.html`:

        $["e2-breadcrumb-pageBreadCrumbs$"].searchModel.products

    Numele cheii aleia e un ID de componenta CMS, deci nu se poate pune in cod ca
    literal fara sa devina fragil la prima reasezare a paginii. Se cauta deci
    `searchModel` in adancime si se ia primul care are `products` lista.

    `pagination`, verbatim: `{"currentPage": 0, "pageSize": 20, "totalPages": 42,
    "totalResults": 834}` - paginare ZERO-INDEXATA, ceea ce conteaza pentru
    descriptor (v. registrul).

    Cheile unui produs, verbatim:

        code                        "BP_45540"
        name                        "La Vie est Belle Apa de Parfum"
        url                         "/lancome/.../p/BP_45540"   RELATIV la radacina
        price.value                 374        (NUMERIC - asta se citeste)
        price.formattedValue        "374,00 RON"   (sir, cu virgula - NU se citeste)
        price.currencyIso           "RON"
        price.priceType             "BUY" sau "FROM"
        images.PRIMARY.list.url     absolut, pe media.marionnaud.ro
        masterBrand.name            "Lancome"

    REFERINTA LIPSESTE, masurat pe 20/20: `otherPrices` e lista goala,
    `otherPricesMap` gol, `priceRange` gol, iar `price.savePrice` e sirul vid.
    Exista `promotions` pe 20/20, dar recompensa e un PROCENT
    (`"formattedRewardValue": "33%"`), nu un pret anterior - un procent nu e o
    referinta din care se poate reconstitui pretul vechi fara sa presupui baza de
    calcul. Deci fara `compare_at` si `reference_kind: "nemarcat"`: raftul intra
    pe axa D doar pe R2.

    O rezerva de semantica, consemnata fiindca se vede in date: `priceType` are
    doua valori, iar `FROM` inseamna "de la", adica pretul celei mai ieftine
    variante de gramaj, nu al unui produs anume. Se citeste tot, fiindca ala e
    pretul afisat pe card si tot el e cel pe care il vede clientul in raft.
    """
    for bloc in _BLOC_JSON.finditer(html or ""):
        try:
            date = json.loads(bloc.group(1), strict=False)
        except Exception:                                        # noqa: BLE001
            continue
        produse = _cauta_search_model(date)
        if produse is None:
            continue

        baza = _baza(descriptor)
        iesire = []
        for produs in produse:
            if not isinstance(produs, dict):
                continue
            cale = (produs.get("url") or "").strip()
            if not cale:
                continue
            pret = _pret_numeric((produs.get("price") or {}).get("value"))
            if pret is None or pret <= 0:
                continue
            imagine = ((((produs.get("images") or {}).get("PRIMARY") or {})
                        .get("list") or {}).get("url"))
            iesire.append(_card(urllib.parse.urljoin(baza + "/", cale),
                                produs.get("name"), pret, None, imagine))
        return iesire
    return []


# ── altex.ro + mediagalaxy.ro — `__NEXT_DATA__`, Redux ──────────────────────
def altex_next(html: str, descriptor: dict) -> list[dict]:
    """altex.ro si mediagalaxy.ro — `/resigilate/`, listare din starea Redux.

    UN SINGUR extractor pentru AMBII frati. DEAL-D2 masurase frateria pe clasele
    DOM (Jaccard 1.000, acelasi prim produs la acelasi pret); JSON-0 a masurat-o si
    pe STARE: aceeasi cale de chei, acelasi `id: 844256` la aceleasi preturi in
    ambele dump-uri. Singurul lucru care difera e gazda, si aia se CITESTE din
    stare (v. mai jos), nu se scrie in cod.

    Caile, verbatim din `dumps_lstd2/{altex,mediagalaxy}.ro_p1.html`:

        props.initialReduxState.resealed.currentCategory.products      48 de obiecte
        props.initialReduxState.resealed.currentCategory.toolbar.pagination
        runtimeConfig.settings.baseUrl     "https://altex.ro" / "https://mediagalaxy.ro"

    ATENTIE la a treia cale: `settings` NU e sub `initialReduxState`, cum ar sugera
    vecinatatea din pagina, ci sub `runtimeConfig`, frate cu `props`. Cautarea a
    confirmat-o pe ambele dump-uri; o cale gresita ar fi facut extractorul sa cada
    tacit pe rezerva de mai jos si sa lege produsele mediagalaxy de gazda altex.

    Cheile unui produs, verbatim:

        id             844256          (numeric — NU se foloseste in URL, v. mai jos)
        sku            "LAP9S715S121071"
        name           "Laptop MSI Modern 15 F13MG-071XRO, ..."
        url_key        "laptop-msi-modern-15-f13mg-071xro-..."
        price          2399.9          (pretul unitatii NOI — „Nou:" in DOM)
        lowest_price   1919.92         (pretul RESIGILAT — „de la ..." in DOM)
        regular_price  2399.9
        stock_status   1
        image          "/media/catalog/product/m/o/modern_15_..._24e97af1.jpg"

    TREI decizii, fiecare platita de o masuratoare din JSON-0 §3.1:

    1. SEMANTICA PRETURILOR E INVERSATA FATA DE NUME. `price` NU e pretul platit:
       e pretul unitatii NOI a aceluiasi SKU, adica exact ce DOM-ul eticheteaza
       „Nou:" si ce descriptorul CSS din DEAL-D2 citea drept `compare_text`.
       Pretul platit e `lowest_price`, cel pe care DOM-ul il arata in
       `.text-red-brand` ca „de la 1.919,92 lei". Deci `price ← lowest_price` si
       `compare_at ← price`. Un mapper care ar lua `price` drept pret platit ar
       raporta pretul de NOU pe tot catalogul — adica ar rata fix reducerea pentru
       care exista scanul. Referinta ramane `nemarcat` (ca „NOU" la eMAG), nu
       Omnibus, si se pastreaza doar cand e STRICT mai mare, ca la `flip_next`.

    2. URL-UL SE COMPUNE CU `sku`, NU CU `id`. Ancorele reale din DOM, verbatim:
       `/laptop-msi-modern-15-.../cpd/LAP9S715S121071/#resigilate`. Prima varianta
       a controlului JSON-0 a folosit `id`-ul numeric si a raportat linistita
       „48/48 carduri complete" — cu toate cele 48 de URL-uri GRESITE, fiindca un
       control de completitudine se uita doar daca URL-ul e nevid. Proba tare a
       fost comparatia cu ancorele DOM: cu `sku`, 48/48 coincid exact. Fragmentul
       `#resigilate` se pastreaza (duce la sectiunea de oferte resigilate a PDP-ului,
       ca `#used-products` la eMAG) si nu atinge dedup-ul, fiindca `external_id` si
       `handle` se calculeaza pe CALE.

    3. `stock_status` SE CITESTE, DAR NU FILTREAZA. Pe cele 48 de produse are
       valoarea 1 pe 48/48, deci un filtru pe el ar fi o regula fara contra-exemplu:
       n-avem nicio dovada ca 0 inseamna „indisponibil" si nici macar ca apare. Se
       lasa afara deliberat, si aici e locul unde se adauga la prima masuratoare.

    IMAGINEA — o cerere care a schimbat raspunsul. Calea din stare
    (`/media/catalog/product/m/o/modern_15_..._24e97af1.jpg`) NU e cea din DOM:
    acolo sta `https://lcdn.altex.ro/resize/media/catalog/product/m/o/<hash>/<nume>`,
    cu un segment de HASH in plus care nu apare nicaieri in obiectul produsului.
    JSON-0 a concluzionat de aici ca imaginea „nu se poate compune". STATE-2 a
    cheltuit o cerere ca sa verifice in loc sa deduca, pe forma FARA hash:

        https://lcdn.altex.ro/media/catalog/product/m/o/modern_15_..._24e97af1.jpg
        -> 200, content-type: image/jpeg, 95.192 octeti

    Deci CDN-ul serveste calea din stare direct, iar segmentul cu hash e doar
    varianta redimensionata pe care o cere DOM-ul. `{cdn}{image}`, cu `cdn` din
    `runtimeConfig.settings.cdn`, ca sa ramana un singur extractor pentru ambii
    frati (`lcdn.altex.ro` vs `lcdn.mediagalaxy.ro`). Fara `cdn` in stare,
    `image_url` iese None si cardul trece fara poza — nu se ghiceste o gazda.
    """
    date = next_data(html)
    if not date:
        return []
    try:
        categorie = (date["props"]["initialReduxState"]["resealed"]["currentCategory"])
        produse = categorie["products"]
    except (KeyError, TypeError):
        return []
    if not isinstance(produse, list) or not produse:
        # Fara produse la cale = final de paginare, nu eroare: acelasi verdict ca
        # „grila goala pe 200" de pe calea CSS.
        return []

    # Gazda din STARE, cu URL-ul descriptorului ca rezerva. Ordinea conteaza: e
    # singurul lucru care difera intre cei doi frati, deci e si singurul care poate
    # lega tacit produsele unuia de gazda celuilalt daca se citeste gresit.
    setari = (date.get("runtimeConfig") or {}).get("settings") or {}
    baza = setari.get("baseUrl")
    if not isinstance(baza, str) or not baza.startswith("http"):
        baza = _baza(descriptor)
    baza = baza.rstrip("/")
    cdn = setari.get("cdn")
    cdn = cdn.rstrip("/") if isinstance(cdn, str) and cdn.startswith("http") else None

    iesire = []
    for produs in produse:
        if not isinstance(produs, dict):
            continue
        slug = (produs.get("url_key") or "").strip()
        sku = str(produs.get("sku") or "").strip()
        if not slug or not sku:
            continue
        pret = _pret_numeric(produs.get("lowest_price"))
        if pret is None or pret <= 0:
            continue
        referinta = _pret_numeric(produs.get("price"))
        if referinta is not None and referinta <= pret:
            referinta = None
        cale_poza = (produs.get("image") or "").strip()
        poza = f"{cdn}{cale_poza}" if (cdn and cale_poza.startswith("/")) else None
        iesire.append(_card(f"{baza}/{slug}/cpd/{sku}/#resigilate",
                            produs.get("name"), pret, referinta, poza))
    return iesire


# ── lego.com — `__NEXT_DATA__` cu cache Apollo NORMALIZAT ───────────────────
#
# Prefixul PDP-ului. Literal, si masurat: cele 42 de URL-uri compuse pe cele trei
# pagini cu produse (18 + 4 categorie, 20 campanie) se regasesc TOATE in ancorele
# DOM ale paginii lor, iar pe categorie cache-ul poarta si campul `pdpPath`,
# identic cu ce compunem noi pe 18/18. Nu se poate deriva din descriptor:
# intrarile sunt `/ro-ro/categories/...` si `/ro-ro/page/...`, alte sectiuni.
_LEGO_PDP = "https://www.lego.com/ro-ro/product/"


def _apollo_referinta(valoare) -> str | None:
    """Cheia catre care arata o referinta de cache Apollo, sau None.

    Doua forme, fiindca Apollo si-a schimbat serializarea intre versiuni majore:
    `{"__ref": "<cheie>"}` (Apollo 3) si `{"type": "id", "generated": <bool>,
    "id": "<cheie>"}` (forma mai veche). Pe lego s-a masurat NUMAI a doua, pe
    42/42 de produse si pe ambele pagini — `__ref` nu apare deloc. E acceptata si
    prima fiindca cele doua nu coexista: o singura serializare per build, deci
    ramura in plus n-are cum sa citeasca altfel ceva ce forma masurata citea deja.
    """
    if not isinstance(valoare, dict):
        return None
    cheie = valoare.get("__ref") or valoare.get("id")
    return cheie if isinstance(cheie, str) and cheie else None


def _apollo_pret(stare: dict, cheie_variantei: str, camp: str):
    """`(valoare, moneda)` pentru `price` / `listPrice` al unei variante.

    DOUA subtilitati, amandoua din acelasi motiv: setul de campuri al cache-ului
    depinde de QUERY-ul din spatele paginii, nu de produs.

    1. Obiectul `Price` se ia prin referinta daca varianta o poarta, altfel prin
       cheia CONSTRUITA `$<cheia variantei>.<camp>`. Pe lego cele doua cai duc in
       acelasi loc — referinta e `generated: true` si `id`-ul ei ESTE cheia
       construita (masurat 42/42, pe ambele pagini) — deci rezerva nu poate
       diverge de masuratoare; e acolo pentru o serializare care ar lasa campul
       afara din obiectul variantei.
    2. Valoarea e `formattedValue` cand e numerica, ALTFEL `centAmount / 100`.
       Nu e preferinta de stil: pe pagina de CATEGORIE obiectul `listPrice` are
       doar `formattedAmount` („84,99 lei") si `centAmount` (8499) — zero
       `formattedValue` pe 22/22 — in timp ce pe campanie il are pe 20/20. Un
       resolver doar-pe-`formattedValue` da deci ZERO referinte pe categorie,
       adica un catalog fara nicio reducere, tacut. `formattedAmount` NU se
       parseaza: e text localizat, exact felul de sursa pe care `centAmount` o
       face inutila.

    Moneda iese separat fiindca nu e pe toate obiectele: `currencyCode` e prezent
    pe `price` 42/42, dar pe `listPrice` doar pe campanie (20/20 acolo, 0/22 pe
    categorie). Cine cheama decide ce face cu absenta ei.
    """
    referinta = _apollo_referinta((stare.get(cheie_variantei) or {}).get(camp))
    obiect = stare.get(referinta) if referinta else None
    if not isinstance(obiect, dict):
        obiect = stare.get(f"${cheie_variantei}.{camp}")
    if not isinstance(obiect, dict):
        return None, None

    moneda = obiect.get("currencyCode")
    moneda = moneda if isinstance(moneda, str) and moneda else None
    valoare = _pret_numeric(obiect.get("formattedValue"))
    if valoare is None:
        centi = obiect.get("centAmount")
        if isinstance(centi, (int, float)) and not isinstance(centi, bool):
            valoare = round(float(centi) / 100, 2)
    return valoare, moneda


def lego_apollo(html: str, descriptor: dict) -> list[dict]:
    """lego.com — categoria de reduceri SI pagina de campanie, din cache Apollo.

    UN extractor, DOUA intrari (`entries`): `/ro-ro/categories/sales-and-deals`
    (18 produse pe p1, 4 pe p2, 0 comune) si `/ro-ro/page/lego-offers-promotions`
    (20). Cache-ul sta la `props.pageProps.__APOLLO_STATE__` si e NORMALIZAT — o
    harta plata de la chei `<Tip>:<id>` la obiecte, legate prin referinte:

        SingleVariantProduct:<cod>   -> slug, name, primaryImage, variant
        ProductVariant:<sku>         -> price, listPrice
        $ProductVariant:<sku>.price  -> {formattedAmount, centAmount,
                                         currencyCode, formattedValue}

    DE CE STARE SI NU CSS. Selectorii exista si merg (`article[data-test=
    'product-leaf']` da 18/18 si 4/4), dar dau imagine pe 0/22: `img[data-test=
    'product-leaf-image-1']` n-are nici `src`, nici `srcset` in HTML-ul brut.
    Si mai important, atributele de test sunt INVERSATE fata de intuitie, exact
    ca la altex:

        <span data-test="product-leaf-price">84,99 lei</span>            TAIAT
        <span data-test="product-leaf-discounted-price">50,99 lei</span> PLATIT

    Un descriptor care ar lua `product-leaf-price` drept pret platit ar raporta
    pretul vechi pe tot catalogul (verificat 22/22: `discounted` e mereu strict
    mai mic). Din cache ambiguitatea dispare: `price` si `listPrice` sunt campuri
    NUMITE, nu pozitii intr-un sablon. Tot din cache se ocolesc si pragurile de
    livrare pe care pagina le poarta ca text alaturi de preturi (`100` / `300` /
    `500` / `1000 lei`) — capcana consemnata inca de la G4-V2b, pe PDP.

    ORDINEA cardurilor e cea a cheilor, adica ordinea din documentul JSON. Nu e o
    aproximare: pagina poarta si o lista ordonata — `ProductQueryResult:<uuid>.
    results` pe categorie, `SKUCarousel:<id>.products` pe campanie — si ea iese
    IDENTICA cu ordinea cheilor pe toate cele trei pagini cu produse (18, 4, 20).
    Deci nu se plimba nimeni prin referintele listei ca sa afle ce se stie deja.

    MONEDA se citeste din cache si se confrunta cu `currency` din descriptor; nu
    se presupune din `/ro-ro/`. O nepotrivire SARE cardul, cu WARN — un pret in
    alta moneda ar intra in scorare ca si cum ar fi in RON. Absenta codului NU e
    nepotrivire: pe `listPrice` de categorie el lipseste pe 22/22, si acolo
    referinta se citeste ca atare (aceeasi varianta, acelasi cos).

    `compare_at` = `listPrice`, doar cand e STRICT mai mare decat pretul platit.
    E pretul de lista LEGO, adica un PRP — nemarcat legal, de unde
    `reference_kind: "nemarcat"` in registru.

    Fara produse -> `[]`: pe `?page=500` pagina raspunde 200 cu grila goala si un
    cache fara nicio cheie `SingleVariantProduct:*`, adica oprirea curata pe care
    conditia compozita din scanner o asteapta (aceeasi semnatura ca altex/flip).
    """
    date = next_data(html)
    stare = (((date or {}).get("props") or {}).get("pageProps") or {}).get(
        "__APOLLO_STATE__")
    if not isinstance(stare, dict):
        return []

    asteptata = descriptor.get("currency")
    iesire = []
    for cheie, produs in stare.items():
        if (not cheie.startswith("SingleVariantProduct:")
                or not isinstance(produs, dict)):
            continue
        # `overrideUrl` inaintea lui `slug`: e campul prin care LEGO poate muta un
        # produs pe alta cale. Masurat null pe 42/42, deci azi lucreaza `slug` —
        # dar precedenta e a magazinului, nu a noastra.
        slug = (produs.get("overrideUrl") or produs.get("slug") or "").strip()
        cheie_variantei = _apollo_referinta(produs.get("variant"))
        if not slug or not cheie_variantei:
            continue

        pret, moneda = _apollo_pret(stare, cheie_variantei, "price")
        if pret is None or pret <= 0:
            continue
        if moneda and asteptata and moneda != asteptata:
            logger.warning(
                "[lego_apollo] %s: moneda %s in cache, descriptorul cere %s — "
                "cardul se sare", slug, moneda, asteptata)
            continue

        referinta, moneda_referintei = _apollo_pret(stare, cheie_variantei,
                                                    "listPrice")
        # O referinta in ALTA moneda nu sare cardul: pretul platit ramane valid,
        # doar reducerea ar fi calculata din doua unitati diferite. Se pierde
        # referinta, nu produsul.
        if moneda_referintei and asteptata and moneda_referintei != asteptata:
            referinta = None
        if referinta is not None and referinta <= pret:
            referinta = None

        # `primaryImage`, nu `primaryImage({"size":"THUMBNAIL"})`: campul cu
        # argumente e emis doar de query-ul de categorie (18/18 acolo, 0/20 pe
        # campanie), iar cel simplu e pe 42/42. Un extractor legat de forma cu
        # argumente ar merge pe o intrare si ar da rame goale pe cealalta.
        iesire.append(_card(_LEGO_PDP + slug, produs.get("name"), pret,
                            referinta, produs.get("primaryImage")))
    return iesire


# ── answear.ro — `window.__REACT_QUERY_STATE__` ─────────────────────────────
#
# Sablonul de imagine. Nu e ghicit: hit-urile poarta doar `{name, version}`, iar
# forma URL-ului o da ld+json-ul ACELEIASI pagini, unde `image` e
# `https://img2.ans-media.com/i/474x717/SS26-BDDZZC-80D_F1.avif?v=1779887811`
# pentru produsul al carui `mainImage.name` e `SS26-BDDZZC-80D_F1.avif` si
# `version` e `1779887811`. Verificat pe primul produs al listarii; aceeasi
# metoda ca la `_BONAMI_IMG`, unde sablonul s-a derivat tot dintr-o sursa
# autoritativa a paginii.
_ANSWEAR_IMG = "https://img2.ans-media.com/i/474x717/{nume}?v={versiune}"

_ANSWEAR_STARE = re.compile(r"window\.__REACT_QUERY_STATE__\s*=\s*")


def react_query_state(html: str) -> dict | None:
    """Cache-ul react-query al paginii, sau None.

    Blobul e o ATRIBUIRE JS, nu un `<script type=application/json>`: se decodeaza
    cu `raw_decode` de la pozitia semnului egal, ca la `rsc_initial_data`. Un
    regex care ar cauta acolada de inchidere ar trebui sa numere acolade prin
    siruri cu ghilimele escapate — exact ce face deja decodorul.
    """
    m = _ANSWEAR_STARE.search(html or "")
    if not m:
        return None
    try:
        obiect, _ = json.JSONDecoder().raw_decode(html[m.end():])
    except Exception:                                            # noqa: BLE001
        return None
    return obiect if isinstance(obiect, dict) else None


def answear_state(html: str, descriptor: dict) -> list[dict]:
    """answear.ro — listarea din cache-ul react-query.

    DE CE STARE SI NU CSS, cu cifre. Pagina are ancore `data-test` stabile
    (`productCard`, `productItemLink`, `priceSaleWithMinimalDesktop`,
    `priceWithMinimalDesktop`) — exact ce cauti cand clasele sunt module CSS cu
    hash. Un descriptor scris pe ele arata impecabil si e gresit in DOUA feluri,
    amandoua tacute (masurate la LST-D7 §3.2):

      * `[data-test="priceSaleWithMinimalDesktop"]` poarta doar ETICHETA („Pret
        actual:"), fara numar. Pretul iese None, deci `extrage_carduri` sare
        TOATE cele 80 de carduri: zero produse, raportate ca „azi n-are reduceri".
      * `[data-test="priceWithMinimalDesktop"]` poarta textul intreg al
        Omnibusului — „Cel mai mic pret din ultimele 30 de zile inainte de
        reducere: 309,90 LEI" — iar `eu_comma` lipeste cele doua numere si
        intoarce 30309.9. O referinta de treizeci de mii de lei pe fiecare card.

    Din stare ambiguitatea dispare: `price`, `priceRegular` si `priceMinimal` sunt
    campuri numerice numite.

    REFERINTA E `priceMinimal`, NU `priceRegular`. Cele doua NU sunt acelasi
    lucru: diverg pe 7/80 (p1) si 27/80 (p2), de pilda `price 329.9,
    priceRegular 478.9, priceMinimal 359.9`. `priceMinimal` e cel etichetat pe
    card drept „cel mai mic pret din ultimele 30 de zile inainte de reducere",
    adica referinta Omnibus; `priceRegular` e pretul de lista, mai mare, si un
    descriptor pe el ar raporta reduceri mai mari decat cele legale. A doua oara
    dupa modivo (LST-3b), unde doua linii ETICHETATE divergeau la fel.

    Interogarea se alege dupa `queryKey[0] == "products"`, nu dupa pozitie: in
    dump exista sase interogari (config, footer, menu, products, newsletter,
    staticPages) si doar una are produse. O alegere pe indice ar tine pana la
    primul deploy care schimba ordinea.
    """
    date = react_query_state(html)
    interogari = (date or {}).get("queries")
    if not isinstance(interogari, list):
        return []
    produse = None
    for q in interogari:
        cheie = (q or {}).get("queryKey")
        if isinstance(cheie, list) and cheie and cheie[0] == "products":
            produse = (((q.get("state") or {}).get("data")) or {}).get("items")
            break
    if not isinstance(produse, list) or not produse:
        return []                    # fara interogare de produse = final/pagina goala

    baza = _baza(descriptor)
    iesire = []
    for p in produse:
        if not isinstance(p, dict):
            continue
        cale = (p.get("url") or "").strip()
        pret = _pret_numeric(p.get("price"))
        if not cale or pret is None or pret <= 0:
            continue
        referinta = _pret_numeric(p.get("priceMinimal"))
        if referinta is not None and referinta <= pret:
            referinta = None         # produs necoborat sub minimul de 30 de zile
        poza = (p.get("productImages") or {}).get("mainImage")
        url_poza = None
        if isinstance(poza, dict) and poza.get("name"):
            url_poza = _ANSWEAR_IMG.format(nume=poza["name"],
                                           versiune=poza.get("version") or "")
        iesire.append(_card(urllib.parse.urljoin(baza, cale), p.get("name"),
                            pret, referinta, url_poza))
    return iesire


# ── endclothing.com — `__NEXT_DATA__` cu raspunsul Algolia inlinat ──────────
#
# IMAGINEA NU SE POATE RAPORTA, si merita scris de ce, fiindca arata a omisiune.
#
# Magazinul serveste pozele printr-un CDN de tip Cloudinary, unde transformarile
# stau intr-un segment cu VIRGULE:
#   https://media.endclothing.com/media/f_auto,q_auto:eco,w_400,h_400
#          /prodmedia/media/catalog/product/B/R/BR_SS26-100-OAT_1_1.jpg
# Asta e SINGURA forma pe care pagina o emite (242 de aparitii; celelalte 818
# URL-uri de pe acelasi CDN sunt bannere de categorie, alta cale), si e forma
# care merge — verificata pe fir la DEAL-D7: 200, `image/jpeg`, 5.131 octeti.
# Aceeasi cale FARA segmentul de transformare da 404.
#
# Dar `normalizeaza_imagine` taie la prima virgula, fiindca acolo virgula
# inseamna „urmatorul candidat de `srcset`". Rezultatul ar fi
# `https://media.endclothing.com/media/f_auto` — o imagine RUPTA pe fiecare card,
# adica mai rau decat niciuna: feed-ul are deja un placeholder „FARA FOTO" pentru
# lipsa, dar n-are cum sa se apere de un URL care pare valid.
#
# Deci extractorul trimite None, deliberat. Reparatia nu e aici: normalizatorul
# ar trebui sa taie pe virgula doar cand urmeaza un descriptor de latime
# (`\d+[wx]`), ceea ce ar atinge `listing_scanner.py` — in afara rundei asteia.
# Cand se face, sablonul de mai jos e gata masurat.
_END_IMG = ("https://media.endclothing.com/media/f_auto,q_auto:eco,w_400,h_400"
            "/prodmedia/media/catalog/product{cale}")


def endclothing_state(html: str, descriptor: dict) -> list[dict]:
    """endclothing.com — categoriile de sale, din raspunsul Algolia INLINAT.

    Pagina nu cheama API-ul ca sa afiseze prima grila: raspunsul e deja in
    `__NEXT_DATA__`, la `props.initialProps.pageProps.initialAlgoliaState.results`
    — 120 de hit-uri, plus `nbHits`, `nbPages`, `hitsPerPage` si chiar `params`-ul
    cererii, cu filtrul de sale verbatim (`filters=NOT "sale_type":"not on sale"`).
    DOM-ul are ZERO carduri (grila e randata client-side), deci CSS e imposibil.

    MONEDA — capcana rundei, si motivul pentru care descriptorul spune EUR desi
    magazinul afiseaza RON. Fiecare hit poarta `full_price_<N>` / `final_price_<N>`
    pentru SAISPREZECE website-uri. Cel corect e `website_id` din
    `config.country` (3 pe vitrina noastra), si se citeste DE ACOLO, nu dintr-o
    constanta: acelasi cod trebuie sa ramana valid daca vitrina se schimba.
    Valoarea de acolo e insa in moneda de BAZA, EUR, nu in `currency_code`:
    pagina afiseaza `RON 552` pentru `full_price_3 = 105`, adica exact
    `105 x 5.252101`, unde 5.252101 e `config.country.rate` — CURSUL MAGAZINULUI.
    Descriptorul declara deci EUR si lasa conversia pe BNR; altfel am importa in
    scorare cursul comercial al magazinului, care nu e cursul pietei.

    `compare_at` = `full_price_<id>`, adica pretul dinainte de reducere al
    aceluiasi produs. Nu poarta nicio eticheta legala pe pagina (nici Omnibus,
    nici PRP), de unde `reference_kind: "nemarcat"` in registru.

    Gazda si prefixul de locala NU sunt constante: vin din
    `config.general.secure_store_url` (`https://www.endclothing.com/eu/`), iar
    calea produsului e `<store_url><url_key>.html` — forma confirmata pe o ancora
    reala a paginii, `/eu/aboutblank-bottle-t-shirt-ss26-100-oat.html`.
    """
    date = next_data(html)
    props = (date or {}).get("props") or {}
    stare = (((props.get("initialProps") or {}).get("pageProps") or {})
             .get("initialAlgoliaState") or {})
    hituri = (stare.get("results") or {}).get("hits")
    config = ((props.get("initialState") or {}).get("config") or {})
    tara = config.get("country") or {}
    id_site = tara.get("website_id")
    if not isinstance(hituri, list) or not hituri or not isinstance(id_site, int):
        return []                    # fara hit-uri = categorie goala / final

    baza = ((config.get("general") or {}).get("secure_store_url") or "").strip()
    if not baza:
        return []                    # fara gazda din stare nu se compune niciun URL

    iesire = []
    for h in hituri:
        if not isinstance(h, dict):
            continue
        slug = (h.get("url_key") or "").strip()
        pret = _pret_numeric(h.get(f"final_price_{id_site}"))
        if not slug or pret is None or pret <= 0:
            continue
        referinta = _pret_numeric(h.get(f"full_price_{id_site}"))
        if referinta is not None and referinta <= pret:
            referinta = None
        # `small_image` exista pe toate hit-urile, dar URL-ul construit din el nu
        # supravietuieste normalizatorului (v. comentariul lui `_END_IMG`), deci
        # nu se raporteaza nicio imagine. Cardul ramane complet in rest.
        iesire.append(_card(urllib.parse.urljoin(baza, f"{slug}.html"),
                            h.get("name"), pret, referinta, None))
    return iesire


# Numele sunt CHEI de descriptor (`state_extractor`), deci se schimba doar odata
# cu registrul. Un nume necunoscut ridica `KeyError` in scanner, deliberat: o
# listare goala ar arata ca „azi n-are reduceri" si ar inchide tacit dealurile.
LISTING_STATE_EXTRACTORS = {
    "toolnation_ldjson": toolnation_ldjson,
    "vivre_rsc": vivre_rsc,
    "cellini_js": cellini_js,
    "bonami_next": bonami_next,
    # STATE-1
    "flip_next": flip_next,
    "marionnaud_json": marionnaud_json,
    # STATE-2 — UN extractor, DOI frati de platforma (altex.ro + mediagalaxy.ro):
    # gazda si CDN-ul se citesc din `runtimeConfig.settings`, nu din cod.
    "altex_next": altex_next,
    # DEAL-D6 — tot UN extractor pentru DOUA intrari ale aceluiasi magazin
    # (categoria de reduceri + pagina de campanie), care difera prin ce
    # campuri emite query-ul din spate, nu prin structura.
    "lego_apollo": lego_apollo,
    # DEAL-D7 — doua listari care NU sunt in DOM: answear.ro (cache react-query,
    # unde CSS-ul are doua capcane tacute) si endclothing.com (raspuns Algolia
    # inlinat, cu grila randata client-side). Familia ajunge la ZECE.
    "answear_state": answear_state,
    "endclothing_state": endclothing_state,
}
