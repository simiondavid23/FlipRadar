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
            # IMG-1b — image_url ramane None, DELIBERAT. Starea poarta doar HASH-uri
            # (`imageHash`, `contextImageHash`, `productImages[].hash`), nu URL-uri, iar
            # sonda IMG-1a2 a cautat hash-ul primului produs in tot dump-ul: apare de
            # doua ori, ambele in JSON, in ZERO atribute `src`/`srcset`/`data-src`.
            # Sablonul de URL nu e deci deductibil din pagina — ramane pentru IMG-1c.
            iesire.append(_card(f"{baza}/p/{slug}", p.get("name"), pret,
                                _suma_units_scale(p.get("retailPrice")), None))
    return iesire


# Numele sunt CHEI de descriptor (`state_extractor`), deci se schimba doar odata
# cu registrul. Un nume necunoscut ridica `KeyError` in scanner, deliberat: o
# listare goala ar arata ca „azi n-are reduceri" si ar inchide tacit dealurile.
LISTING_STATE_EXTRACTORS = {
    "toolnation_ldjson": toolnation_ldjson,
    "vivre_rsc": vivre_rsc,
    "cellini_js": cellini_js,
    "bonami_next": bonami_next,
}
