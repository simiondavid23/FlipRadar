"""RETAIL-1 — extractor generic de pagina de produs (nume, pret, moneda, stoc).

Fundatia monitorizarii de pret prin link: primeste URL-ul unei pagini de produs
si intoarce un dict normalizat. Parsarea (`parse_product_html`) e PURA — fara
retea, fara DB — ca sa fie testabila offline pe HTML capturat; fetch-ul live
(`extract_product`) refoloseste infrastructura existenta din scraper_service.

Ordinea surselor, per camp: override pe domeniu > JSON-LD > OpenGraph > microdata.
JSON-LD (schema.org/Product) e sursa principala fiindca e stabila intre magazine
si nu depinde de clase CSS; OG e plasa de siguranta; DOMAIN_OVERRIDES ramane
supapa pentru magazinele care nu publica date structurate corecte.

Microdata (schema.org in atribute HTML: itemprop name/price/priceCurrency/
availability) a intrat ultima, la CONTENT-2, pentru magazinele care publica datele
de produs EXCLUSIV asa — evomag.ro nu are niciun Product in ld+json si nici og:title
sau og:price. E un fallback MARGINIT prin constructie: completeaza doar campurile
ramase GOALE dupa celelalte trei surse, niciodata nu suprascrie. Pe un domeniu deja
validat pretul ramane deci exact cel de dinainte; ce se poate schimba e un camp care
era None — in practica `in_stock`, unde sursa principala nu publica availability
(masurat pe flanco.ro la validarea offline: pret neschimbat, stoc completat din
microdata). Pretul din microdata are in plus o regula de siguranta la ambiguitate
(vezi _collect_microdata).

Inaintea intregului flux de mai sus sta registrul CUSTOM_EXTRACTORS (DISCOVERY-2):
domenii unde datele de produs NU se afla in HTML-ul paginii, deci nu exista sursa
de citit indiferent de ordine. Acolo `extract_product` deleaga integral catre un
extractor dedicat, care ridica aceleasi ProductExtractionError si foloseste aceeasi
poarta guarded C-14. Primul caz: asos.com, unde pretul vine din API-ul public de
stoc/pret, nu din pagina.

Modulul nu logheaza nimic (log_manager ramane la apelanti) si nu importa
scraper_service la nivel de modul — vezi comentariul din extract_product.
"""
import json
import random
import re
import time
import urllib.parse

from bs4 import BeautifulSoup

from app.services.shop_registry import (
    SHOP_REGISTRY,
    browser_domains,
    domain_overrides,
    shopify_domains,
    validated_domains,
)


class ProductExtractionError(Exception):
    """Esec de extragere, cu motiv structurat pentru apelanti (UI/scheduler).

    `reason` e unul dintre: "domain_not_allowed" (allow-list-ul SSRF a respins
    URL-ul), "fetch_failed" (retea / status non-200), "challenge" (interstitiu
    anti-bot), "no_product_data" (pagina nu contine date de produs),
    "invalid_price" (exista un pret in pagina, dar e 0/negativ/neparsabil).
    """

    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or reason)


# Registry per domeniu (cheia = domeniu fara "www."). Toate campurile sunt
# optionale si se aplica DOAR peste rezultatul de baza:
#   price_regex — regex cu UN grup de captura, cautat in HTML-ul BRUT; grupul se
#                 parseaza STRICT ca float in format masina (JSON/JS embedded).
#                 Are precedenta peste price_selector; match lipsa sau valoare
#                 invalida => ignorat, se cade pe price_selector, apoi jsonld/og.
#   price_selector / name_selector / image_selector — selectori CSS. Pentru pret,
#                 sursa e textul elementului; daca acesta nu produce un pret valid
#                 se citeste atributul `content` (BR-1: pe makeup.ro purtatorul e
#                 un <meta itemprop="price" content="49.29">, fara text).
#   out_of_stock_text — substring case-insensitive in pagina => in_stock False
#   currency — moneda fixa a magazinului
#   vat_prices — True pe magazinele care publica DOUA preturi: net in JSON-LD si
#                brut in microdata (senetic.ro, raport 1.21 = TVA, masurat 3/3 la
#                LOT1). Precedenta normala ar lua netul, adica un pret cu 21% sub
#                cel platit — pe un comparator, fiecare produs ar parea chilipir.
#                Efectul: `price` devine brutul, iar ambele preturi se expun ca
#                VARIANTE ("cu TVA" / "fara TVA"), prin masinaria existenta din
#                FASHION-1b. Se aplica DOAR daca ambele preturi sunt valide si
#                brutul e mai mare ca netul; altfel comportamentul ramane cel de azi.
DOMAIN_OVERRIDES: dict[str, dict] = domain_overrides()

# Domeniile pe care extractorul a fost validat pe pagini de produs REALE.
# refresh_source le reimprospateaza citind direct pagina de produs; celelalte
# raman pe re-cautare. Un domeniu se adauga DOAR dupa o sonda live, niciodata pe
# presupunere: o extractie gresita ar scrie preturi false in istoric.
#
# Sursa canonica a listei e app/services/shop_registry.py; jurnalul sondelor per
# domeniu (ce s-a masurat, ce s-a infirmat, de ce a intrat fiecare magazin) sta
# in docs/catalog_domain_log.md.
VALIDATED_DOMAINS: set[str] = validated_domains()


# Headers proprii modulului: generice, fara Referer (pagina de produs e ceruta
# direct, dintr-un link salvat de user, nu dintr-o navigare de pe site).
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}
_TIMEOUT = 25

# schema.org/ItemAvailability — valorile acceptate cu sau fara prefixul
# "https://schema.org/", case-insensitive (vezi _normalize_availability).
_AVAILABILITY_TRUE = {
    "instock", "limitedavailability", "onlineonly", "instoreonly",
    "preorder", "backorder",
}
_AVAILABILITY_FALSE = {"outofstock", "soldout", "discontinued"}

# "2.499" -> 2499 (mii), dar "24.99" -> 24.99 (zecimala): punctul e separator de
# mii DOAR daca grupeaza exact cate 3 cifre.
_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")


# ── normalizari ───────────────────────────────────────────────────────────────

def _clean_text(value) -> str | None:
    """Text curatat de spatii multiple; None daca nu ramane nimic."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return text or None


def _parse_price_any(value) -> float | None:
    """Pret din orice reprezentare intalnita in paginile de magazin.

    Accepta int/float direct; pentru string curata simboluri, spatii, nbsp si
    sufixe de moneda, apoi decide separatorul zecimal:
      - si "." si "," => ultimul dintre ele e zecimalul, celalalt se elimina
        ("1.234,56" -> 1234.56, "1,234.56" -> 1234.56)
      - doar ","      => zecimal ("24,99" -> 24.99)
      - doar "."      => mii DOAR pe grupuri de 3 ("2.499" -> 2499.0),
                         altfel zecimal ("24.99" -> 24.99)
    Intoarce None daca nu se poate extrage un numar.
    """
    if isinstance(value, bool):
        return None  # True/False sunt int in Python — nu sunt preturi
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    cleaned = re.sub(r"[^\d,.]", "", value.replace("\xa0", " "))
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None

    last_dot, last_comma = cleaned.rfind("."), cleaned.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        if last_dot > last_comma:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif last_comma >= 0:
        cleaned = cleaned.replace(",", ".")
    elif last_dot >= 0 and _THOUSANDS_DOT.match(cleaned):
        cleaned = cleaned.replace(".", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_currency(value) -> str | None:
    """"lei"/"RON" -> RON, "eur"/"€" -> EUR, "usd"/"$" -> USD; restul upper()."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if "lei" in text or "ron" in text:
        return "RON"
    if "eur" in text or "€" in text:
        return "EUR"
    if "usd" in text or "$" in text:
        return "USD"
    return text.upper()


def _normalize_availability(value) -> bool | None:
    """schema.org/ItemAvailability -> True / False / None (necunoscut)."""
    if not isinstance(value, str):
        return None
    token = re.sub(r"[^a-z]", "", value.strip().rsplit("/", 1)[-1].lower())
    if token in _AVAILABILITY_TRUE:
        return True
    if token in _AVAILABILITY_FALSE:
        return False
    return None


def match_shop_domain(hostname: str, domains) -> str | None:
    """Intrarea din `domains` care acopera `hostname`: egalitate sau subdomeniu cu
    GRANITA PE PUNCT (m.emag.ro -> emag.ro; evilcel.ro -> None). Aceeasi regula ca
    _is_allowed_shop_url din scraper_service — auditul retail a gasit ca lookup-urile
    pe egalitate exacta lasau subdomeniile legitime fara override si fara refresh
    (comenzi.farmaciatei.ro salvat ca sursa -> refresh permanent None, tacut).
    Intrarile CU subdomeniu (en.afew-store.com) raman acoperite doar exact/copil —
    domeniul gol NU se potriveste cu ele (fail-closed, ca pana acum)."""
    h = (hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    for d in domains:
        if h == d or h.endswith("." + d):
            return d
    return None


def _domain_of(url: str) -> str:
    """Hostname lowercase, fara "www." (cheia din DOMAIN_OVERRIDES)."""
    try:
        host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


# ── JSON-LD ───────────────────────────────────────────────────────────────────

def _flatten_jsonld(node, depth: int = 0):
    """Toate dict-urile dintr-un bloc ld+json: liste top-level si @graph incluse."""
    if depth > 6:  # plasa contra structurilor auto-referentiale
        return
    if isinstance(node, list):
        for item in node:
            yield from _flatten_jsonld(item, depth + 1)
    elif isinstance(node, dict):
        yield node
        graph = node.get("@graph")
        if graph is not None:
            yield from _flatten_jsonld(graph, depth + 1)


def _iter_jsonld_objects(soup):
    """Obiectele din toate blocurile application/ld+json ale paginii.

    json.loads e tolerant per bloc: un singur bloc corupt (destul de frecvent —
    template-uri cu variabile neinlocuite) nu trebuie sa arunce restul paginii —
    dar cand blocul corupt e SINGURUL (LOT5b: control-characters in descrieri
    multi-linie), treapta laxa il recupereaza inainte de a renunta.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Ordinea conteaza: strictul ramane calea normala, deci semantica
            # tuturor paginilor care parsau pana azi e neschimbata. Laxul e o
            # SINGURA reincercare pe ACELASI bloc si accepta exclusiv ce permite
            # `strict=False` — caractere de control brute (newline/tab literal) in
            # valorile de string. Nimic altceva: sintaxa stricata, ghilimelele
            # dublate si virgulele finale pica in continuare (masurat la LOT5b pe
            # pagina brickdepot cu `"...salvate local""`).
            try:
                data = json.loads(raw, strict=False)
            except Exception:
                continue
        yield from _flatten_jsonld(data)


def _has_type(obj: dict, wanted: str) -> bool:
    """@type == `wanted` (lowercase), inclusiv cand @type e lista (["Product", "Thing"])."""
    node_type = obj.get("@type")
    if isinstance(node_type, str):
        return node_type.strip().lower() == wanted
    if isinstance(node_type, list):
        return any(isinstance(t, str) and t.strip().lower() == wanted for t in node_type)
    return False


def _is_product(obj: dict) -> bool:
    return _has_type(obj, "product")


def _is_product_group(obj: dict) -> bool:
    """@type "ProductGroup" — grupul de variante (marimi) al aceluiasi produs."""
    return _has_type(obj, "productgroup")


def _first_image(value) -> str | None:
    """image poate fi string, lista sau ImageObject — ia primul URL utilizabil."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _first_image(value.get("url") or value.get("contentUrl"))
    if isinstance(value, list):
        for item in value:
            got = _first_image(item)
            if got:
                return got
    return None


def _price_from_offers(offers):
    """(pret, is_aggregate, offer_folosit, s_a_vazut_candidat) din `offers`.

    `offers` poate fi dict sau lista — pe lista castiga oferta cu pretul MINIM
    (G2F-4; inainte castiga PRIMA cu pret). In cadrul unei oferte ordinea ramane
    price > lowPrice (AggregateOffer => is_aggregate) > priceSpecification.price.
    Flag-ul de candidat separa "nu exista pret in pagina" (no_product_data) de
    "exista dar e invalid" (invalid_price).

    G2F-4 — de ce minimul, si nu primul: o lista de `Offer` sub acelasi `Product`
    sunt variantele aceluiasi produs (gramaje, capacitati, pachete), iar ordinea
    lor in JSON-LD e ARBITRARA — magazinul n-o declara nicaieri ca semnificativa.
    "Primul cu pret" lega asadar pretul produsului de un accident de serializare:
    la o reordonare tacuta a feed-ului, acelasi produs isi schimba pretul fara ca
    magazinul sa fi schimbat ceva.

    Minimul NU e o conventie noua — e conventia pe care extractorul o aplica DEJA
    celorlalte doua forme de variante, doar ca acestea o poarta in alta haina:
      * `lowPrice` la AggregateOffer (tezyo, f64) — magazinul insusi publica
        minimul, si il citim ca atare;
      * `_aggregate_variants` — minimul marimilor in stoc, pentru
        ProductGroup.hasVariant (FASHION-1) si pentru offers-lista-cu-`size`
        (FASHION-2).
    Ramasese descoperita exact forma fara `size`: lista de oferte pe care
    `_variants_from_offer_list` o refuza, fiindca nu poate numi variantele. G2F-4
    ii da aceeasi semantica — "cea mai ieftina varianta", indiferent de haina.

    Oferta INTOARSA e cea care a castigat pretul, nu prima din lista: moneda si
    disponibilitatea se citesc din ea (`_offer_currency`, `availability`), deci
    trebuie sa descrie exact varianta cotata, altfel pretul ar veni de la o
    varianta si moneda de la alta. La egalitate castiga prima intalnita, ca
    rezultatul sa ramana stabil pe liste cu preturi identice.

    Masurat la G2F-4 pe cele 150 de dump-uri de sonda: doar 3 noduri au lista cu
    >=2 preturi valide (tezyo pdp1, otter prod1, direct-running pdp2) si la toate
    primul era deja minimul — deci regula nu misca niciun pret cunoscut azi; e o
    plasa pentru ordinea viitoare, nu o corectie de valori. (zooplus, care a
    declansat runda, nu trece pe aici deloc: e ProductGroup cu `hasVariant`.)
    """
    saw_candidate = False
    first_offer = None
    best = None  # (pret, is_aggregate, offer) — cel mai mic pret valid de pana acum
    for offer in (offers if isinstance(offers, list) else [offers]):
        if not isinstance(offer, dict):
            continue
        if first_offer is None:
            first_offer = offer
        # Pretul UNEI oferte, cu precedenta neschimbata; None daca oferta n-are
        # niciun pret valid (element corupt) — atunci se sare, nu invalideaza lista.
        gasit = None
        for key, is_aggregate in (("price", False), ("lowPrice", True)):
            if offer.get(key) is not None:
                saw_candidate = True
                price = _parse_price_any(offer.get(key))
                if price is not None:
                    gasit = (price, is_aggregate, offer)
                    break
        if gasit is None:
            spec = offer.get("priceSpecification")
            for node in (spec if isinstance(spec, list) else [spec]):
                if isinstance(node, dict) and node.get("price") is not None:
                    saw_candidate = True
                    price = _parse_price_any(node.get("price"))
                    if price is not None:
                        gasit = (price, False, offer)
                        break
        if gasit is not None and (best is None or gasit[0] < best[0]):
            best = gasit
    if best is not None:
        return best[0], best[1], best[2], saw_candidate
    return None, False, first_offer, saw_candidate


def _offer_currency(offer):
    """Moneda unei oferte: nivelul ofertei intai, apoi `priceSpecification`.

    LOT4 — parfumdreams.de publica AMBELE in spec, iar oferta n-are nici `price`,
    nici `priceCurrency`:

        "offers": {"@type": "Offer",
                   "priceSpecification": {"@type": "UnitPriceSpecification",
                                          "price": 59.9, "priceCurrency": "EUR"}}

    Pretul se citea deja de acolo (vezi _price_from_offers), moneda nu — deci
    cadea pe implicitul romanesc din parse_product_html si 59.90 EUR ajungea
    59.90 RON, adica produsul parea de ~5 ori mai ieftin. E o forma generala,
    nu o ciudatenie a unui magazin.

    Neutralitate: oferta care isi declara propria `priceCurrency` se comporta
    exact ca inainte — spec-ul conteaza doar unde nivelul de oferta lipsea.
    Normalizarea ramane la apelanti, ca peste tot.
    """
    if not isinstance(offer, dict):
        return None
    if offer.get("priceCurrency"):
        return offer["priceCurrency"]
    spec = offer.get("priceSpecification")
    for node in (spec if isinstance(spec, list) else [spec]):
        if isinstance(node, dict) and node.get("priceCurrency"):
            return node["priceCurrency"]
    return None


def _availability_din_oferte_imbricate(offer) -> bool | None:
    """VTX-2 — disponibilitatea din `offers` IMBRICATE intr-un AggregateOffer.

    A treia forma de `offers`, dupa ProductGroup/hasVariant (FASHION-1) si lista
    de oferte cu `size` (FASHION-2): un `Product` simplu al carui `offers` e un
    singur `AggregateOffer`, care poarta preturile in low/highPrice si tine
    ofertele reale intr-o lista imbricata. Agregatul NU are `availability`, deci
    citirea lui dadea None si stocul se pierdea desi era publicat corect — masurat
    pe f64.ro (VTEX): `offers.@type = AggregateOffer`, `availability` absenta pe
    agregat, dar `offers[0].availability = "http://schema.org/InStock"`.

    Agregare optimista, ca la `_aggregate_variants`: produsul e cumparabil daca
    MACAR o oferta imbricata e in stoc. Toate False -> False. Niciuna cunoscuta ->
    None, adica "necunoscut" — nu se inventeaza un True.
    """
    if not isinstance(offer, dict):
        return None
    stari = [_normalize_availability(nod.get("availability"))
             for nod in (offer.get("offers") or [])
             if isinstance(nod, dict)]
    cunoscute = [s for s in stari if s is not None]
    if not cunoscute:
        return None
    return True if any(cunoscute) else False


def _variant_label(variant: dict, *, fallback_name: bool = True) -> str:
    """Eticheta unei variante: campul `size`, cu numele ca plasa de siguranta.

    Ramane STRING LIBER, fara normalizare numerica: eobuwie publica jumatatile si
    taliile compuse ca '40_5' / '28_32', BSTN publica '4,0 US' si '36 2/3 EU' —
    orice "curatare" ori ar pierde informatie, ori ar confunda 40.5 cu un interval.
    Cine o afiseaza o arata ca atare.

    `fallback_name=False` cere o marime DECLARATA (FASHION-2): pe o lista de
    oferte, caderea pe `name` ar inventa o marime din numele produsului si ar
    transforma ofertele obisnuite in variante.
    """
    size = variant.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        size = str(size)
    # `size` poate fi si o LISTA de marimi la nivel de produs (pattern answear) —
    # aia nu e eticheta unei variante, deci se cade pe nume.
    label = _clean_text(size) if isinstance(size, str) else None
    if label or not fallback_name:
        return label or ""
    return _clean_text(variant.get("name")) or ""


def _variesby_dims(group: dict) -> list[str]:
    """Dimensiunile de variatie declarate de un ProductGroup, IN ORDINEA lor.

    `variesBy` poarta URL-uri schema.org ("https://schema.org/size"); dimensiunea e
    ultimul segment, lowercase. Acceptam si valoarea scalara (un singur URL, nu
    lista) — schema.org o permite.
    """
    raw = group.get("variesBy")
    if raw is None:
        return []
    valori = raw if isinstance(raw, list) else [raw]
    dims = []
    for valoare in valori:
        if not isinstance(valoare, str):
            continue
        dim = valoare.rstrip("/").rsplit("/", 1)[-1].strip().lower()
        if dim and dim not in dims:
            dims.append(dim)
    return dims


def _compound_label(variant: dict, dims: list[str]) -> str:
    """Eticheta compusa din dimensiunile declarate, unite cu " / ".

    Partile lipsa se SAR (o varianta fara `color` da doar "S"). Ramane STRING
    LIBER, ca `_variant_label` — aceleasi motive: valorile publicate sunt deja
    etichete de magazin ('40_5', '36 2/3 EU'), iar orice normalizare ar pierde
    informatie sau ar confunda intervale.
    """
    parti = []
    for dim in dims:
        valoare = variant.get(dim)
        if isinstance(valoare, (int, float)) and not isinstance(valoare, bool):
            valoare = str(valoare)
        parte = _clean_text(valoare) if isinstance(valoare, str) else None
        if parte:
            parti.append(parte)
    return " / ".join(parti)


def _aggregate_variants(variants: list) -> tuple:
    """(pret, in_stock) product-level dintr-o lista NEVIDA de variante cotate.

    Acelasi calcul pentru AMBELE forme de variante — ProductGroup.hasVariant si
    Product.offers-lista cu `size` — ca acelasi produs sa fie raportat identic
    indiferent cum si-l publica magazinul:
      pret = minimul marimilor IN STOC (semantica "de la"), cu fallback pe minimul
             tuturor cand nimic nu e cumparabil, ca produsul sa ramana monitorizabil;
      stoc = True daca macar o marime e in stoc, False cand TOATE sunt explicit
             epuizate, None altfel (necunoscut).
    """
    states = [v["in_stock"] for v in variants]
    in_stock_prices = [v["price"] for v in variants if v["in_stock"] is True]
    price = min(in_stock_prices) if in_stock_prices else min(v["price"] for v in variants)
    if any(s is True for s in states):
        return price, True
    if all(s is False for s in states):
        return price, False
    return price, None


def _variants_from_offer_list(offers):
    """Variante din forma #2: `offers` e o LISTA de oferte, fiecare cu `size`
    propriu, fara ProductGroup (masurat pe BSTN, sonda 2026-07-26).

    Intoarce None cand forma nu se aplica — `offers` nu e lista, niciun element
    nu declara o marime, sau niciunul cotat nu are pret valid. In toate cazurile
    astea calea Product ramane EXACT cea de dinainte de FASHION-2.
    """
    if not isinstance(offers, list):
        return None
    variants = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        # Doar ofertele cu marime DECLARATA devin variante: pe o lista mixta,
        # restul raman oferte obisnuite si nu intra in agregare.
        label = _variant_label(offer, fallback_name=False)
        if not label:
            continue
        # Acelasi parser de pret ca oriunde, pe un singur element.
        price, _is_aggregate, used, _seen = _price_from_offers([offer])
        # Marimea necotata se SARE, nu invalideaza restul listei.
        if price is None or price <= 0:
            continue
        variants.append({
            "variant": label,
            "price": price,
            "in_stock": _normalize_availability((used or offer).get("availability")),
        })
    return variants or None


def _candidate_from_group(group: dict):
    """Candidat product-level dintr-un ProductGroup + lista lui de variante.

    Forma masurata pe eobuwie (epantofi/modivo) si About You, sonda 2026-07-26:
    `hasVariant` e o lista de produse-varianta, fiecare cu `size` la nivelul ei si
    cu propria `offers`. Pretul si disponibilitatea trec prin logica EXISTENTA
    (_price_from_offers / _normalize_availability), ca variantele sa se comporte
    exact ca ofertele obisnuite.

    VARIATIE MULTI-DIMENSIONALA (LOT2b): bergfreunde.eu publica grupuri cu
    `variesBy: [size, color]` — 24 de variante = 8 marimi x 3 culori, cu preturi
    care DIFERA pe culoare la aceeasi marime (S/Olive 67.96 vs S/Timber 63.96).
    Etichetate doar cu `size`, variantele devin NEunice, iar selectia per-varianta
    din create_product_from_url ia prima potrivire — userul care alege "S" putea
    primi tacut pretul si stocul altei culori. De aceea, cand grupul declara MAI
    MULT de o dimensiune, eticheta se COMPUNE din toate, in ordinea din `variesBy`
    ("S / Olive Green").

    Garda de activare: compunerea porneste oricand `variesBy` e declarat si
    parsabil; absent sau neparsabil, eticheta ramane exact `_variant_label` — deci
    grupurile masurate pana acum (eobuwie, About You) se comporta byte-identic.
    Pe o singura dimensiune `[size]` rezultatul coincide oricum cu
    `_variant_label`; extinderea de la LOT3b conteaza pentru dimensiunile NON-size:
    pe boozt/booztlet grupurile declara `variesBy: [color]`, iar fara compunere
    eticheta cadea pe plasa de nume ("Adrian Cherry Red Arcadia - CHERRY RED")
    in loc de culoarea curata.

    LIMITA CONSTIENTA: pe un grup care produce etichete duplicate FARA sa declare
    `variesBy` multi, coliziunea ramane — n-avem din ce compune. Cazul n-a fost
    intalnit inca; daca apare, se rezolva cu identitatea variantei (`sku`), nu prin
    ghicirea dimensiunilor.

    Intoarce None daca obiectul nu poarta deloc `hasVariant`.
    """
    raw = group.get("hasVariant")
    if raw is None:
        return None
    entries = raw if isinstance(raw, list) else [raw]

    dims = _variesby_dims(group)
    # LOT3b: compunerea se aplica oricand grupul DECLARA dimensiunile, chiar si una
    # singura. Pe `[size]` rezultatul e identic cu cel de dinainte (partea `size`
    # singura E `_variant_label`-ul pe size, iar lipsa lui cade pe acelasi fallback),
    # dar pe `[color]` — boozt/booztlet — eticheta devine culoarea ("CHERRY RED") in
    # loc de numele intreg al produsului ("Adrian Cherry Red Arcadia - CHERRY RED"),
    # care venea din plasa de siguranta. `variesBy` absent sau neparsabil => plasa.
    compune = bool(dims)

    variants, currency, saw_candidate = [], None, False
    for variant in entries:
        if not isinstance(variant, dict):
            continue
        price, _is_aggregate, offer, seen = _price_from_offers(variant.get("offers"))
        saw_candidate = saw_candidate or seen
        # Varianta fara pret utilizabil se SARE, nu arunca: o marime pe care
        # magazinul n-o mai coteaza nu trebuie sa invalideze restul grupului.
        if price is None or price <= 0:
            continue
        offer = offer or {}
        if currency is None:
            currency = _normalize_currency(_offer_currency(offer))
        # Toate partile lipsa => cadem pe plasa existenta, ca variantele fara
        # dimensiunile declarate sa nu ramana cu eticheta goala.
        compusa = _compound_label(variant, dims) if compune else ""
        variants.append({
            "variant": compusa or _variant_label(variant),
            "price": price,
            "in_stock": _normalize_availability(offer.get("availability")),
        })

    first = next((v for v in entries if isinstance(v, dict)), {})
    candidate = {
        "name": _clean_text(group.get("name")) or _clean_text(first.get("name")),
        "price": None,
        "currency": currency or _normalize_currency(group.get("priceCurrency")),
        "in_stock": None,
        # Pretul e un MINIM peste marimi ("de la"), nu o valoare unica.
        "is_aggregate": True,
        "image_url": _first_image(group.get("image")) or _first_image(first.get("image")),
        "price_seen": saw_candidate,
        "variants": None,
    }
    if not variants:
        # Grup fara nicio varianta cotata: lasam price=None si price_seen asa cum a
        # iesit, ca fluxul existent de eroare sa aleaga intre invalid_price si
        # no_product_data exact ca la un Product simplu.
        return candidate

    candidate["price"], candidate["in_stock"] = _aggregate_variants(variants)
    candidate["variants"] = variants
    return candidate


def _collect_jsonld(soup):
    """(rezultat_complet | None, primul_candidat | None).

    Castiga primul Product cu nume SI pret rezolvabil; primul Product intalnit se
    pastreaza oricum ca `partial`, ca sa putem clasifica eroarea (un Product cu
    pret "0" e invalid_price, nu no_product_data).

    ProductGroup e plasa de dedesubt, nu concurent: se foloseste DOAR daca niciun
    Product n-a dat un pret rezolvabil (magazinele de moda publica si un Product
    simplu langa grup, iar acela ramane sursa preferata).
    """
    partial = None
    group_result = None
    for obj in _iter_jsonld_objects(soup):
        if _is_product_group(obj):
            if group_result is None:
                group = _candidate_from_group(obj)
                if group is not None:
                    if partial is None:
                        partial = group
                    if group["name"] and group["price"] is not None and group["price"] > 0:
                        group_result = group
            continue
        if not _is_product(obj):
            continue
        price, is_aggregate, offer, saw_candidate = _price_from_offers(obj.get("offers"))
        offer = offer or {}
        # FASHION-2 — forma #2: un singur Product, dar `offers` e o lista de oferte
        # cu `size` pe fiecare. Cand se aplica, pretul product-level vine din
        # AGREGARE (minimul marimilor in stoc), nu din "primul cu pret" — pe BSTN
        # primul element e adesea o marime epuizata, deci pretul de dinainte era
        # cel al primei marimi din lista. Listele fara `size` nu ating nimic:
        # `variants` ramane None si pretul e exact cel de azi.
        # NU fabricam variante dintr-o lista de marimi fara oferte per marime
        # (pattern answear) — n-am avea nici pret, nici stoc pe marime.
        variants = _variants_from_offer_list(obj.get("offers"))
        if variants:
            price, in_stock = _aggregate_variants(variants)
            is_aggregate = True
        else:
            in_stock = _normalize_availability(offer.get("availability"))
            if in_stock is None:
                in_stock = _availability_din_oferte_imbricate(offer)
        candidate = {
            "name": _clean_text(obj.get("name")),
            "price": price,
            "currency": _normalize_currency(_offer_currency(offer) or obj.get("priceCurrency")),
            "in_stock": in_stock,
            "is_aggregate": is_aggregate,
            "image_url": _first_image(obj.get("image")),
            "price_seen": saw_candidate,
            "variants": variants,
        }
        if partial is None:
            partial = candidate
        if candidate["name"] and price is not None and price > 0:
            return candidate, partial
    return group_result, partial


# ── OpenGraph ─────────────────────────────────────────────────────────────────

def _meta(soup, *names) -> str | None:
    """Continutul primului <meta> cu property= sau name= dintre `names`."""
    for name in names:
        for attr in ("property", "name"):
            el = soup.find("meta", attrs={attr: name})
            if el is not None:
                content = _clean_text(el.get("content"))
                if content:
                    return content
    return None


def _collect_og(soup):
    """Fallback OpenGraph. Stocul nu are echivalent OG de incredere — ramane
    None (poate fi acoperit de out_of_stock_text din DOMAIN_OVERRIDES)."""
    price_raw = _meta(soup, "product:price:amount", "og:price:amount")
    return {
        "name": _meta(soup, "og:title"),
        "price": _parse_price_any(price_raw),
        "currency": _normalize_currency(_meta(soup, "product:price:currency", "og:price:currency")),
        "in_stock": None,
        "is_aggregate": False,
        "image_url": _meta(soup, "og:image"),
        "price_seen": price_raw is not None,
        "variants": None,   # OG nu descrie variante
    }


def _in_scope(el, root) -> bool:
    """True daca `el` apartine DIRECT scope-ului `root`, nu unui obiect NESTED.

    Regula standard de scopare microdata: o proprietate apartine itemului al carui
    `itemscope` e cel mai apropiat stramos al ei. Urcam din `el`; daca dam peste
    root inainte de orice alt `itemscope`, proprietatea e a root-ului.
    """
    parent = el.parent
    while parent is not None:
        if parent is root:
            return True
        if parent.has_attr("itemscope"):
            return False
        parent = parent.parent
    return False


def _collect_microdata(soup):
    """Microdata schema.org (itemprop in atribute HTML) — a PATRA sursa, ultima.

    Exista magazine care publica datele de produs doar asa: evomag.ro (sonda
    CONTENT-1b, 2026-07-28) are ld+json fara niciun Product (doar BreadcrumbList /
    ElectronicsStore / Organization / WebSite) si nu are nici og:title, nici
    og:price — tot ce descrie produsul sta in microdata.

    SCOPARE: daca pagina are EXACT un `itemtype=.../Product`, cautam doar in el.
    Fara scopare, `itemprop="name"` prinde si titluri din afara produsului (pe
    evomag: 2 elemente in pagina, 1 singur in scope), iar pe paginile cu recenzii
    ar intra si autorii (Review/Rating au propriile scope-uri). Cu 0 sau mai multe
    scope-uri Product cautam in tot documentul si lasam regulile de mai jos sa
    decida.

    Pretul are REGULA DE SIGURANTA proprie: cu 0 sau >=2 elemente de pret nu
    furnizam nimic, nici macar `price_seen`. Un pret gresit ajunge in istoric si in
    alerte, deci ambiguitatea trebuie sa ramana esec, nu ghicitoare.

    SCOPARE NESTED, DOAR PE NUME (LOT1): un obiect microdata nested isi poarta
    propriile proprietati, iar `brand` are si el un `name`. Pe pcgarage.ro scope-ul
    Product contine DOUA `itemprop="name"` — `<td>`-ul produsului si un
    `<meta itemprop="name" content="Lenovo">` care apartine obiectului nested
    `itemprop="brand"` — deci regula "un singur candidat sau h1-ul" pica si numele
    ramane None. Filtram numele la elementele al caror cel mai apropiat stramos cu
    `itemscope` E CHIAR root-ul.
    Filtrul se opreste DELIBERAT la nume. Pretul, moneda si stocul apartin PRIN
    DESIGN obiectului nested `offers` (asa e si pe evomag, si pe pcgarage — exact
    ca `Product.offers.price` din JSON-LD), deci aceeasi filtrare aplicata lor le-ar
    face zero candidati si ar rupe domeniile care merg azi (masurat la LOT1).
    """
    scopes = soup.select('[itemtype*="schema.org/Product"]')
    root = scopes[0] if len(scopes) == 1 else soup

    def _valoare(el):
        """content= are prioritate (e forma pentru masini), altfel textul."""
        return _clean_text(el.get("content")) or _clean_text(el.get_text(" ", strip=True))

    # --- pret ---
    price, price_seen = None, False
    preturi = root.select('[itemprop="price"]')
    if len(preturi) == 1:
        el = preturi[0]
        price_seen = True
        continut = _clean_text(el.get("content"))
        if continut:
            # `content` e prin conventie format masina ("1349.99"), deci float()
            # STRICT: prin _parse_price_any, "1234.567" ar fi citit ca mii.
            try:
                price = float(continut)
            except (TypeError, ValueError):
                price = None
        else:
            price = _parse_price_any(el.get_text(" ", strip=True))
        if price is not None and price <= 0:
            price = None

    # --- nume: un singur candidat, sau h1-ul dintre ei ---
    name = None
    nume = root.select('[itemprop="name"]')
    if len(scopes) == 1:
        # Doar proprietatile Product-ului INSUSI; brand/Review/Rating isi tin ale lor.
        nume = [el for el in nume if _in_scope(el, root)]
    if len(nume) == 1:
        name = _valoare(nume[0])
    elif len(nume) > 1:
        titluri = [el for el in nume if el.name == "h1"]
        if len(titluri) == 1:
            name = _valoare(titluri[0])

    # --- moneda ---
    currency = None
    monede = root.select('[itemprop="priceCurrency"]')
    if monede:
        currency = _normalize_currency(_valoare(monede[0]))

    # --- stoc: URL-ul schema.org, din content= sau href= (<link itemprop=...>) ---
    in_stock = None
    stocuri = root.select('[itemprop="availability"]')
    if stocuri:
        el = stocuri[0]
        in_stock = _normalize_availability(
            _clean_text(el.get("content")) or _clean_text(el.get("href")) or "")

    return {"name": name, "price": price, "currency": currency,
            "in_stock": in_stock, "price_seen": price_seen}


# ── API public ────────────────────────────────────────────────────────────────

def _canonical_url(soup, url: str) -> str:
    """<link rel=canonical> absolut daca exista, altfel URL-ul de intrare fara
    fragment (parametrii de tracking raman — nu stim care sunt semnificativi)."""
    link = soup.find("link", rel="canonical")
    if link is not None:
        href = (link.get("href") or "").strip()
        if href.lower().startswith(("http://", "https://")):
            return href
    return urllib.parse.urldefrag(url or "")[0] or (url or "")


def parse_product_html(html: str, url: str) -> dict:
    """Extrage {name, price, currency, in_stock, ...} din HTML-ul unei pagini de
    produs. PURA: fara retea, fara DB — tinta testelor.

    Ridica ProductExtractionError daca lipseste numele sau pretul valid.
    """
    soup = BeautifulSoup(html or "", "html.parser")

    result, partial = _collect_jsonld(soup)
    method = "jsonld"
    if result is None:
        og = _collect_og(soup)
        if og["name"] or og["price"] is not None or og["price_seen"]:
            result, method = og, "og"
        elif partial is not None:
            result = partial  # doar pentru clasificarea erorii (method ramane jsonld)
        else:
            result, method = og, "og"  # gol: nici JSON-LD, nici OG

    domain = _domain_of(url)
    override_key = match_shop_domain(domain, DOMAIN_OVERRIDES)
    override_applied = _apply_override(soup, html or "", result, DOMAIN_OVERRIDES.get(override_key) or {})

    # G2F-6 — flagul de registru `ldjson_availability: "untrusted"`.
    #
    # Pe unele magazine `availability` din ld+json nu e o masuratoare, ci o
    # CONSTANTA de sablon. Masurat pe ro.vivre.eu (sonda G2F-5): PDP-urile emit
    # `schema.org/OutOfStock` pentru produse pe care datele proprii de listare ale
    # ACELUIASI site le marcheaza `"inStock":true` — contradictie pe aceleasi doua
    # produse (8831337 si 1977409), iar pe tot lotul masurat `"inStock":true` apare
    # de 24 de ori, `false` niciodata, iar sirul `schema.org/InStock` NICIODATA.
    # Cu 46.536 de produse in catalog, a crede sablonul ar insemna `in_stock=False`
    # pe tot magazinul: nu o necunoastere, ci o afirmatie FALSA si activa, care ar
    # ascunde din feed exact produsele cumparabile.
    #
    # Neutralizarea sta AICI, imediat dupa override si INAINTE de microdata,
    # deliberat: flagul spune ca `availability` DIN LD+JSON nu e de incredere, nu ca
    # domeniul n-are stoc. O eventuala sursa independenta (microdata) ramane libera
    # sa completeze campul mai jos. Pe vivre cele doua citiri coincid — pagina n-are
    # microdata — deci alegerea nu schimba nimic azi, dar pastreaza flagul cinstit
    # daca maine il pune cineva pe un domeniu cu doua surse.
    #
    # Variantele se neutralizeaza odata cu produsul: stocul lor vine din exact
    # aceeasi `availability`, deci a lasa `in_stock` pe variante ar contrazice
    # produsul. Pretul si restul extractiei raman NEATINSE.
    if (method == "jsonld"
            and (SHOP_REGISTRY.get(match_shop_domain(domain, SHOP_REGISTRY)) or {}
                 ).get("ldjson_availability") == "untrusted"):
        result["in_stock"] = None
        for _v in (result.get("variants") or []):
            if isinstance(_v, dict):
                _v["in_stock"] = None

    # CONTENT-2: microdata completeaza DOAR campurile ramase goale dupa override,
    # JSON-LD si OG. Fallback marginit prin constructie — pe un domeniu unde
    # sursele de dinainte au dat un camp, microdata nu are ce suprascrie, deci nu
    # poate schimba comportamentul niciunui domeniu deja validat.
    micro = _collect_microdata(soup)
    if not result["name"] and micro["name"]:
        result["name"] = micro["name"]
    if result["price"] is None:
        if micro["price"] is not None:
            result["price"] = micro["price"]
            result["price_seen"] = True
            method = "microdata"
        elif micro["price_seen"]:
            # Exista un pret in pagina, dar nu s-a putut citi -> invalid_price,
            # nu no_product_data (aceeasi distinctie ca la celelalte surse).
            result["price_seen"] = True
    if not result["currency"] and micro["currency"]:
        result["currency"] = micro["currency"]
    if result["in_stock"] is None and micro["in_stock"] is not None:
        result["in_stock"] = micro["in_stock"]

    # LOT1 — preturi duale cu/fara TVA (senetic.ro): JSON-LD poarta NETUL, microdata
    # BRUTUL. Precedenta normala ar lua netul, adica un pret cu ~21% sub cel platit;
    # intr-un comparator, fiecare produs al magazinului ar parea chilipir.
    # Pastram AMBELE, prin masinaria de variante din FASHION-1b: `price` devine
    # brutul (comparabilul de consumator), iar netul ramane accesibil ca varianta.
    # Garda de sens (brut > net) tine flag-ul inofensiv pe o pagina care nu se
    # comporta asa: conditia neindeplinita => exact comportamentul de azi.
    if ((DOMAIN_OVERRIDES.get(override_key) or {}).get("vat_prices")
            and method == "jsonld"
            and result["price"] is not None and result["price"] > 0
            and micro["price"] is not None and micro["price"] > result["price"]):
        fara_tva, cu_tva = result["price"], micro["price"]
        result["price"] = cu_tva
        result["variants"] = [
            {"variant": "cu TVA", "price": cu_tva, "in_stock": result["in_stock"]},
            {"variant": "fara TVA", "price": fara_tva, "in_stock": result["in_stock"]},
        ]
        override_applied = True

    name, price = result["name"], result["price"]
    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Nicio structura de produs (JSON-LD/OG) in pagina: {(url or '')[:120]}")
    if price is None or price <= 0:
        raise ProductExtractionError(
            "invalid_price" if result["price_seen"] else "no_product_data",
            f"Pret lipsa sau invalid ({price!r}) pentru '{name[:60]}': {(url or '')[:120]}")

    return {
        "name": name,
        "price": price,
        # Magazinele acoperite sunt romanesti: un pret fara moneda declarata e in RON.
        "currency": result["currency"] or "RON",
        "in_stock": result["in_stock"],
        "is_aggregate": bool(result["is_aggregate"]),
        # ADITIV (FASHION-1b): lista de marimi cu pret+stoc, cand sursa e un
        # ProductGroup. None pe toate celelalte cai (Product simplu, OG, override).
        "variants": result.get("variants"),
        "image_url": result["image_url"],
        "canonical_url": _canonical_url(soup, url),
        "domain": domain,
        "method": method,
        "override_applied": override_applied,
    }


def _price_from_regex(html: str, pattern: str):
    """(a_gasit_match, pret) pentru grupul 1 al `pattern` din HTML-ul BRUT.

    Parsare STRICTA cu float(), NU _parse_price_any: sursa e o stare JSON/JS
    incorporata, unde punctul e MEREU separator zecimal. Trecut prin
    _parse_price_any, "1234.567" ar fi citit ca mii si ar da 1234567.

    Flag-ul de match e separat de valoare ca apelantul sa stie ca a EXISTAT un
    candidat de pret in pagina (invalid_price) chiar daca nu s-a putut parsa.
    """
    match = re.search(pattern, html or "", re.S)
    if match is None:
        return False, None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError, IndexError):
        return True, None  # captura neparsabila (sau pattern fara grup) -> ignorat
    return True, (value if value > 0 else None)


def _apply_override(soup, html: str, result: dict, override: dict) -> bool:
    """Patch-uieste IN-PLACE doar campurile definite in override, peste rezultatul
    de baza (doar price_selector => numele si stocul raman din JSON-LD).

    Intoarce True doar daca s-a aplicat efectiv ceva: un selector care nu se mai
    potriveste (site redesenat) nu trebuie sa raporteze override activ.
    """
    if not override:
        return False
    applied = False

    # price_regex INAINTEA price_selector: cand magazinul publica pretul afisat
    # intr-o stare JS incorporata, aceasta e mai stabila decat clasele CSS.
    # Esecul lui nu e final — se cade pe price_selector, apoi pe jsonld/og.
    price_done = False
    pattern = override.get("price_regex")
    if pattern:
        matched, regex_price = _price_from_regex(html, pattern)
        if matched:
            result["price_seen"] = True
        if regex_price is not None:
            result["price"] = regex_price
            result["is_aggregate"] = False
            applied = price_done = True

    selector = override.get("price_selector")
    if selector and not price_done:
        el = soup.select_one(selector)
        if el is not None:
            result["price_seen"] = True
            price = _parse_price_any(el.get_text(" ", strip=True))
            if price is None:
                # BR-1: purtatorul poate fi un <meta itemprop="price" content="49.29">,
                # care n-are text deloc. `content` e prin conventie format masina,
                # deci float() STRICT — aceeasi regula ca in _collect_microdata,
                # unde _parse_price_any ar citi "1234.567" ca mii.
                # TEXTUL ramane prioritar: extensia porneste doar cand el n-a dat
                # un pret valid, deci niciun override existent nu-si schimba sursa.
                try:
                    valoare = float(_clean_text(el.get("content")) or "")
                except (TypeError, ValueError):
                    valoare = None
                price = valoare if (valoare is not None and valoare > 0) else None
            if price is not None:
                result["price"] = price
                result["is_aggregate"] = False  # selectorul da pretul concret, nu un interval
                applied = True

    selector = override.get("name_selector")
    if selector:
        el = soup.select_one(selector)
        name = _clean_text(el.get_text(" ", strip=True)) if el is not None else None
        if name:
            result["name"] = name
            applied = True

    selector = override.get("image_selector")
    if selector:
        el = soup.select_one(selector)
        if el is not None:
            image = _clean_text(el.get("content") or el.get("src") or el.get("data-src") or el.get("href"))
            if image:
                result["image_url"] = image
                applied = True

    marker = override.get("out_of_stock_text")
    if marker and marker.lower() in soup.get_text(" ", strip=True).lower():
        # Doar sensul negativ e definit: absenta markerului nu inseamna "in stoc",
        # lasa valoarea de baza (poate fi si None = necunoscut).
        result["in_stock"] = False
        applied = True

    currency = override.get("currency")
    if currency:
        result["currency"] = _normalize_currency(currency)
        applied = True

    return applied


def _fetch_text_guarded(url: str, max_retries: int = 3) -> str:
    """Textul unui URL prin poarta C-14, cu taxonomia de erori din extract_product.

    NU e o refactorizare a buclei din extract_product si nu o inlocuieste: acolo
    incercarile de FETCH si cele de PARSE impart acelasi buget de `max_retries`
    (retry-ul FASHION-4 pe no_product_data reintra in aceeasi bucla), iar mutarea
    fetch-ului aici ar da 3 incercari de fetch PER incercare de parsare — alt
    comportament, cu alte numaratori de apeluri decat cele pinuite in teste.
    Helperul asta serveste extractoarele custom, care nu parseaza HTML si deci n-au
    nevoie de retry-ul de parsare.
    """
    from app.services.scraper_service import _fetch_shop_url_guarded, _is_allowed_shop_url

    last_status = None
    saw_challenge = False
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            time.sleep(random.uniform(1, 3))

        response = _fetch_shop_url_guarded(url, headers=_HEADERS, timeout=_TIMEOUT)
        if response is None:
            if not _is_allowed_shop_url(url):
                raise ProductExtractionError(
                    "domain_not_allowed", f"Domeniu neautorizat (allow-list C-14): {url[:120]}")
            continue
        last_status = response.status_code
        if (response.status_code == 403
                or response.headers.get("cf-mitigated") == "challenge"
                or "just a moment" in response.text[:2000].lower()):
            saw_challenge = True
            continue
        if response.status_code != 200:
            continue
        return response.text

    if saw_challenge:
        raise ProductExtractionError(
            "challenge", f"Blocat de challenge anti-bot dupa {max_retries} incercari: {url[:120]}")
    raise ProductExtractionError(
        "fetch_failed",
        f"Fetch esuat dupa {max_retries} incercari (ultimul status: {last_status}): {url[:120]}")


_ASOS_ID_RE = re.compile(r"/prd/(\d+)")

# store/currency/country sunt intrarea OFICIALA pentru Romania din
# /api/fashion/store/v2/stores/countries (sonda DISCOVERY-1, 2026-07-28; raspunsul e
# cache-uit in scripts/diagnostics/asos_stores.json):
#   {"country": "RO", "store": "ROE", ..., "currencies": [{"currency": "EUR", ...}]}
# `currency=EUR` SINGUR da 400 "Invalid Currency Requested" — moneda e legata de
# magazin, deci cele trei coduri merg impreuna. `keyStoreDataversion` e omis
# DELIBERAT: API-ul raspunde si fara el, iar valoarea din pagina e volatila.
_ASOS_STOCKPRICE_URL = (
    "https://www.asos.com/api/product/catalogue/v4/stockprice"
    "?productIds={pid}&store=ROE&currency=EUR&country=RO"
)


def _extract_asos(url: str) -> dict:
    """asos.com — pagina nu poarta pretul, deci il luam din API-ul public de stoc/pret.

    Masurat la DISCOVERY-1 (2026-07-28): ld+json-ul paginii are un Product FARA
    `offers`, OG n-are pret, iar blobul `stockPriceResponse` inline vine in GBP si
    nu e garantat (pagina insasi cade pe XHR cand lipseste). API-ul public
    raspunde insa cu pretul EUR corect, fara cookie-uri.

    Doua fetch-uri, AMBELE prin poarta guarded C-14: pagina (doar pentru nume) si
    API-ul (pret, moneda, stoc).
    """
    match = _ASOS_ID_RE.search(urllib.parse.urlparse(url or "").path)
    if match is None:
        raise ProductExtractionError(
            "no_product_data", f"URL ASOS fara /prd/<id>: {(url or '')[:120]}")
    product_id = int(match.group(1))

    # --- 1. pagina: numele. ld+json-ul are Product (fara offers); OG e plasa. ---
    soup = BeautifulSoup(_fetch_text_guarded(url), "html.parser")
    name = None
    for obj in _iter_jsonld_objects(soup):
        if _is_product(obj) and obj.get("name"):
            name = _clean_text(obj["name"])
            break
    name = name or _meta(soup, "og:title")
    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Pagina ASOS fara nume de produs: {(url or '')[:120]}")

    # --- 2. API: pret, moneda, stoc ---
    corp = _fetch_text_guarded(_ASOS_STOCKPRICE_URL.format(pid=product_id))
    try:
        payload = json.loads(corp)
    except Exception:
        raise ProductExtractionError(
            "no_product_data", f"Raspuns stockprice neparsabil pentru {product_id}")
    if isinstance(payload, dict):
        payload = [payload]

    intrare = None
    for candidat in payload or []:
        if not isinstance(candidat, dict):
            continue
        try:
            if int(candidat.get("productId")) == product_id:
                intrare = candidat
                break
        except (TypeError, ValueError):
            continue
    if intrare is None:
        # Lista poate contine si alte produse (recomandari): fara intrarea NOASTRA
        # nu ghicim — primul element ar fi pretul altui produs.
        raise ProductExtractionError(
            "no_product_data",
            f"Produsul {product_id} lipseste din raspunsul stockprice: {(url or '')[:120]}")

    pret_bloc = (intrare.get("productPrice") or {})
    price = _parse_price_any((pret_bloc.get("current") or {}).get("value"))
    if price is None or price <= 0:
        raise ProductExtractionError(
            "invalid_price", f"Pret invalid ({price!r}) pentru {product_id} la '{name[:60]}'")

    return {
        "name": name,
        "price": price,
        "currency": _normalize_currency(pret_bloc.get("currency")) or "EUR",
        "in_stock": intrare.get("isInStock") if isinstance(
            intrare.get("isInStock"), bool) else None,
        "is_aggregate": False,
        "variants": None,
        "image_url": _meta(soup, "og:image"),
        "canonical_url": _canonical_url(soup, url),
        "domain": _domain_of(url),
        "method": "asos_stockprice",
        "override_applied": False,
    }


# ── elefant.ro (ELF-2) ────────────────────────────────────────────────────────

# Formatul de pret MASURAT pe elefant (ELF-1/1b, trei PDP-uri): "19,31 lei",
# "89,99 lei", "10,99 lei"; mii cu punct, zecimale cu virgula, sufix "lei".
# Zecimalele sunt OPTIONALE (un pret rotund se randeaza fara ele), dar restul e
# strict: ancorat la capete, deci un nod care ar contine DOUA preturi lipite
# ("39,99 lei19,31 lei") intoarce None in loc sa produca un numar inventat.
_ELEFANT_PRET_RE = re.compile(
    r"^(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?\s*lei$", re.I)

# Payload-ul GTM al paginii de produs; `price` vine cu punct zecimal ("19.31").
_ELEFANT_GTM_RE = re.compile(r"GTMproductDetail\.push\(\s*(\{.*?\})\s*\)", re.S)


def _parse_pret_elefant(text) -> float | None:
    """Pretul din textul vizibil al unui nod de pret elefant, parsare STRICTA.

    NU foloseste _parse_price_any dinadins: acela e permisiv prin design (curata
    orice non-cifra si ghiceste separatorul), deci ar transforma si un text
    corupt intr-un numar plauzibil. Aici sursa are UN singur format masurat, iar
    o abatere de la el inseamna ca pagina s-a schimbat — semnal pe care il vrem
    ca esec curat (None), nu ca reparatie tacuta.
    """
    if not isinstance(text, str):
        return None
    curat = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    potrivire = _ELEFANT_PRET_RE.match(curat)
    if potrivire is None:
        return None
    intreg = potrivire.group(1).replace(".", "")
    zecimale = potrivire.group(2) or "0"
    try:
        return float(f"{intreg}.{zecimale}")
    except ValueError:
        return None


def _pret_elefant_din_gtm(html: str):
    """(pret, gasit_payload) din `window.ish.GTMproductDetail`.

    Rezerva pentru cazul in care ancora primara dispare. Parsare STRICTA cu
    float(), ca la _price_from_regex: sursa e o stare JS incorporata, unde
    punctul e MEREU separator zecimal.
    """
    potrivire = _ELEFANT_GTM_RE.search(html or "")
    if potrivire is None:
        return None, False
    try:
        payload = json.loads(potrivire.group(1))
    except Exception:
        return None, True
    if not isinstance(payload, dict):
        return None, True
    brut = payload.get("price")
    if not isinstance(brut, (str, int, float)) or isinstance(brut, bool):
        return None, True
    try:
        return float(brut), True
    except (TypeError, ValueError):
        return None, True


def _extract_elefant(url: str) -> dict:
    """elefant.ro — Intershop, zero date structurate in pagina.

    Masurat la VTX-1c + ELF-1/1b (2026-08-17): domeniul n-are ld+json, n-are
    microdata si n-are OG, deci fluxul generic ridica `no_product_data` pe orice
    pagina de produs. Datele stau in DOM si intr-un payload GTM.

    UN singur fetch, prin poarta guarded C-14 (pagina poarta tot ce ne trebuie).
    """
    html = _fetch_text_guarded(url)
    soup = BeautifulSoup(html, "html.parser")

    # Numele: <h1>, masurat curat pe toate cele trei PDP-uri (redus, neredus,
    # epuizat). `<title>` ar aduce si brandul si sufixul " - elefant.ro".
    titlu = soup.find("h1")
    name = _clean_text(titlu.get_text(" ", strip=True)) if titlu is not None else None

    # --- Pretul, in ordinea de incredere masurata ---------------------------
    # 1. PRIMAR: `[data-testing-id="current-price"]`, exact 1 aparitie per PDP pe
    #    toate cele trei pagini masurate, cu moneda pe ACELASI element.
    price, currency = None, None
    nod = soup.select_one('[data-testing-id="current-price"]')
    if nod is not None:
        price = _parse_pret_elefant(nod.get_text(" ", strip=True))
        if price is not None:
            currency = _normalize_currency(nod.get("data-price-currencymnemonic"))

    # 2. REZERVA: payload-ul GTM. Moneda NU e in payload, deci ramane None —
    #    DELIBERAT. Fluxul generic pune "RON" pe magazinele romanesti (vezi
    #    parse_product_html), dar acolo defaultul acopera o pagina care oricum a
    #    dovedit ca e de produs; aici am ajunge la el tocmai fiindca ancora
    #    primara a disparut, adica pagina s-a schimbat. Intr-un asemenea moment o
    #    moneda presupusa ar ascunde exact schimbarea pe care vrem s-o vedem:
    #    lasam None si semnaleaza validarea din aval.
    if price is None:
        price, _ = _pret_elefant_din_gtm(html)

    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Pagina elefant fara <h1>: {(url or '')[:120]}")
    if price is None:
        raise ProductExtractionError(
            "no_product_data",
            f"Pagina elefant fara pret citibil (nici testing-id, nici GTM): "
            f"{(url or '')[:120]}")
    if price <= 0:
        raise ProductExtractionError(
            "invalid_price", f"Pret invalid ({price!r}) la '{name[:60]}'")

    # Imaginea: masurata pe `.product-image-container img` (varianta de 1000px).
    # OG lipseste cu totul pe domeniu, dar il pastram ca plasa daca apare candva.
    img = soup.select_one(".product-image-container img[src]")
    image_url = (img.get("src") if img is not None else None) or _meta(soup, "og:image")

    return {
        "name": name,
        "price": price,
        "currency": currency,
        # STOC: None NECONDITIONAT, si e o decizie masurata, nu o scapare.
        #
        # ELF-1b a comparat PDP-ul unui produs pe care catalogul il clasa
        # `AvailableFlag-0` ("Indisponibil") cu PDP-uri de produse in stoc: din 12
        # semnale verificate, ZERO separa ramurile. elefant.ro nu randeaza stocul
        # server-side nici pe pagina de produs, nici pe placa de listare — il
        # stampileaza JS, dupa un apel la GetProductData-GetInventoryStatusForProducts.
        #
        # NU "repara" asta cu niciuna dintre urmatoarele, toate masurate ca false:
        #   * `[data-testing-id="addToCartButton"]` — prezent IDENTIC si pe produsul
        #     indisponibil (fara `disabled`, fara style); ar da True mereu;
        #   * bara sticky — `StickyAddProduct` SI `StickyNotAvailable` ("Indisponibil")
        #     exista amandoua in DOM pe ORICE produs, ambele cu `display: none`;
        #   * `data-sold-out-text="Stoc epuizat!"` — sablon pe fiecare placa din
        #     ORICE listare (61 aparitii si in cea de indisponibile, si in cea in
        #     stoc), ascuns in `div.hidden.js-product-sold-out-text`.
        #
        # Avalul e tri-state si stie sa afiseze necunoscutul (StockBadge -> "Stoc
        # necunoscut"), deci None e informatie corecta, nu lipsa de informatie.
        "in_stock": None,
        "is_aggregate": False,
        "variants": None,
        "image_url": image_url,
        "canonical_url": _canonical_url(soup, url),
        "domain": _domain_of(url),
        "method": "elefant_intershop",
        "override_applied": False,
    }


# ── Shopify (SHOP-1) ──────────────────────────────────────────────────────────

_SHOPIFY_HANDLE_RE = re.compile(r"/products/([^/?#]+)")

# Titlul pe care Shopify il da variantei unice a unui produs FARA optiuni.
_SHOPIFY_FARA_VARIANTE = "Default Title"

# Domeniile servite de extractorul generic, derivate din `method` in registru.
_SHOPIFY_DOMAINS: set[str] = shopify_domains()


def _shopify_variant_price(brut):
    """Pretul unei variante Shopify: int in unitati MINORE (24861 -> 248.61).

    Endpoint-ul Ajax da intotdeauna int (masurat 321/321 variante la sonda
    SHOP-1a); acceptam si string-ul numai-cifre, fiindca e aceeasi valoare doar
    serializata altfel. Orice alta forma (zecimale, virgule, float) intoarce None
    si varianta se SARE — aceeasi filozofie ca marimile necotate din
    _variants_from_offer_list: un element neinteligibil nu invalideaza restul.
    """
    if isinstance(brut, bool) or brut is None:
        return None
    if isinstance(brut, int):
        return brut / 100.0
    if isinstance(brut, str) and brut.isdigit():
        return int(brut) / 100.0
    return None


def _extract_shopify(url: str) -> dict:
    """Magazinele Shopify — extractie din endpoint-ul Ajax /products/<handle>.js.

    De ce `.js` si nu `.json`: sonda SHOP-1a a masurat ca varianta din
    /products/<handle>.json NU poarta deloc campul `available` (0 din 39 de
    produse, pe toate cele 13 domenii), deci regula FASHION-2 — pretul minim al
    marimilor DISPONIBILE — e imposibil de aplicat pe el. `.js` il poarta 13/13.
    In schimb formatul pretului difera: int in unitati minore, nu string zecimal.

    Moneda NU e in payload; vine din registru (campul `currency`, obligatoriu
    pentru intrarile shopify). Un singur fetch, prin poarta guarded C-14 —
    domeniile ajung in allow-list automat, fiind in VALIDATED_DOMAINS.
    """
    parsed = urllib.parse.urlparse(url or "")
    match = _SHOPIFY_HANDLE_RE.search(parsed.path or "")
    if match is None:
        raise ProductExtractionError(
            "no_product_data", f"URL Shopify fara /products/<handle>: {(url or '')[:120]}")

    # Handle-ul poate veni cu sufix de API lipit, daca userul a copiat chiar URL-ul
    # endpointului. Prefixele de locale din cale (/en/products/...) nu deranjeaza:
    # regexul ia ce urmeaza dupa /products/, iar fetch-ul refoloseste host-ul
    # ORIGINAL — subdomeniul conteaza (en.afew-store.com).
    handle = match.group(1)
    for sufix in (".js", ".json"):
        if handle.endswith(sufix):
            handle = handle[: -len(sufix)]
            break
    if not handle:
        raise ProductExtractionError(
            "no_product_data", f"Handle Shopify gol: {(url or '')[:120]}")

    baza = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    corp = _fetch_text_guarded(f"{baza}/products/{handle}.js")
    try:
        payload = json.loads(corp)
    except Exception:
        raise ProductExtractionError(
            "no_product_data", f"Payload Ajax neparsabil pentru handle '{handle[:60]}'")
    if not isinstance(payload, dict):
        raise ProductExtractionError(
            "no_product_data", f"Payload Ajax neasteptat pentru handle '{handle[:60]}'")

    name = _clean_text(payload.get("title"))
    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Produs Shopify fara titlu: {(url or '')[:120]}")

    # --- variantele: pret + disponibilitate ---
    variante_brute = payload.get("variants") or []
    variante, disponibile, toate = [], [], []
    pret_vazut = False
    for v in variante_brute:
        if not isinstance(v, dict):
            continue
        if v.get("price") is not None:
            pret_vazut = True
        price = _shopify_variant_price(v.get("price"))
        if price is None or price <= 0:
            continue
        in_stock = v.get("available") if isinstance(v.get("available"), bool) else None
        toate.append(price)
        if in_stock:
            disponibile.append(price)
        # Titlul variantei concateneaza optiunile ("42 / Black / Piele"), deci e mai
        # informativ decat option1 singur.
        variante.append({
            "variant": _clean_text(v.get("title")) or _clean_text(v.get("option1")),
            "price": price,
            "in_stock": in_stock,
        })

    # --- FASHION-2: minimul marimilor DISPONIBILE ---
    if disponibile:
        price, in_stock = min(disponibile), True
    elif toate:
        price, in_stock = min(toate), False
    else:
        # Aceeasi distinctie ca in parse_product_html: daca pagina CHIAR poarta
        # preturi dar niciunul nu e citibil, e invalid_price (specific); daca nu
        # poarta niciunul, n-avem date de produs.
        raise ProductExtractionError(
            "invalid_price" if pret_vazut else "no_product_data",
            f"Niciun pret valid pentru '{name[:60]}' ({len(variante_brute)} variante)")

    # Un singur variant "Default Title" = produs FARA optiuni, deci simplu.
    if len(variante) == 1 and variante[0]["variant"] == _SHOPIFY_FARA_VARIANTE:
        variante = None

    image_url = payload.get("featured_image")
    if isinstance(image_url, str) and image_url.startswith("//"):
        image_url = "https:" + image_url

    cale = payload.get("url") if isinstance(payload.get("url"), str) else None
    canonical_url = baza + (cale or f"/products/{handle}")

    return {
        "name": name,
        "price": price,
        "currency": (SHOP_REGISTRY.get(match_shop_domain(_domain_of(url), _SHOPIFY_DOMAINS))
                     or {}).get("currency"),
        "in_stock": in_stock,
        "is_aggregate": False,
        "variants": variante or None,
        "image_url": image_url or None,
        "canonical_url": canonical_url,
        "domain": match_shop_domain(_domain_of(url), _SHOPIFY_DOMAINS),
        "method": "shopify",
        "override_applied": False,
    }


def _browser_domain_for(url: str):
    """Domeniul din registru daca URL-ul se serveste prin harness-ul de browser."""
    return match_shop_domain(_domain_of(url), browser_domains())


def _extract_via_browser(url: str) -> dict:
    """A TREIA cale de fetch (BR-1): pagina se cere printr-un browser real, apoi se
    parseaza cu ACELASI parse_product_html ca oricare alta.

    Grupul 4 nu e o problema de parsare, ci de acces: pe orange.ro datele apar abia
    dupa randare, iar makeup/hhv/sephora resping cererea fara browser. Restul
    catalogului ramane pe curl — harness-ul e scump (un Chromium per pagina) si se
    foloseste doar unde sonda a dovedit ca nu exista alta cale.

    Import LENES, deliberat: browser_fetch importa patchright, care n-are ce cauta
    in graful de import al extractorului — modulul asta se incarca la fiecare
    pornire, harness-ul doar pe cele cateva domenii care-l cer.
    """
    from app.services import browser_fetch as bf

    domain = _browser_domain_for(url)
    try:
        # Validarea continutului e chiar parsarea: harness-ul iese din poll la
        # prima varianta de HTML din care iese un produs, deci nu asteapta degeaba.
        html = bf.fetch_browser_html(url, domain, lambda h: parse_product_html(h, url))
    except bf.BrowserFetchBlocked as exc:
        raise ProductExtractionError("challenge", str(exc)[:200]) from exc
    except bf.BrowserFetchTooSoon as exc:
        # fetch_failed, ca orice "n-am ajuns la continut": refresh_source pastreaza
        # pretul anterior, iar sanatatea catalogului vede incercarea nereusita.
        raise ProductExtractionError("fetch_failed", str(exc)[:200]) from exc
    except bf.BrowserFetchUnavailable as exc:
        raise ProductExtractionError("fetch_failed", str(exc)[:200]) from exc

    return parse_product_html(html, url)


def _shopify_extractor_for(url: str):
    """True daca domeniul e servit de extractorul generic Shopify.

    De ce NU prin CUSTOM_EXTRACTORS: acela mapeaza domenii la cod BESPOKE, cate o
    functie per magazin (asos). Aici domeniile `shopify` impart UN singur extractor condus
    de registru, iar apartenenta se decide din campul `method`, nu dintr-o lista
    paralela care ar putea diverge de el.
    """
    return match_shop_domain(_domain_of(url), _SHOPIFY_DOMAINS) is not None


# Domenii unde datele NU stau in HTML-ul paginii, deci fluxul generic n-are ce citi.
# Cheia e domeniul de baza; potrivirea e suffix-safe, ca la allow-list-ul C-14.
# ── powerup.ro (G2A-1/G2A-2) ─────────────────────────────────────────────────

# Blocul de pret al PDP-ului, VERBATIM din `dumps_g2a/powerup.ro_prod_red1.html`:
#
#   <div class="product-price clearfix">
#     <span class="full-price">26.900<sup>,00</sup> LEI</span><br/>
#     <span class="discount-price"><i>19.990<sup>,00</sup> LEI</i>
#       <span class="price-unit">/ buc.</span></span>
#   </div>
#
# Zecimalele stau in `<sup>`, deci textul se ia cu separator GOL: `get_text(" ")`
# ar da "19.990 ,00 LEI", cu un spatiu intre intreg si zecimale.
_POWERUP_PRET_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*lei$", re.I)


def _parse_pret_powerup(text) -> float | None:
    """Pretul dintr-un nod de pret powerup, parsare STRICTA.

    Ca la elefant, NU trece prin `_parse_price_any`: acela e permisiv prin design
    si ar transforma un text corupt intr-un numar plauzibil. Sursa are UN singur
    format masurat ("19.990,00LEI"), iar abaterea de la el inseamna ca pagina s-a
    schimbat — semnal pe care il vrem ca esec curat.
    """
    if not isinstance(text, str):
        return None
    curat = re.sub(r"\s+", "", text.replace("\xa0", "")).strip()
    potrivire = _POWERUP_PRET_RE.match(curat)
    if potrivire is None:
        return None
    try:
        return float(f"{potrivire.group(1).replace('.', '')}.{potrivire.group(2)}")
    except ValueError:
        return None


def _extract_powerup(url: str) -> dict:
    """powerup.ro — OpenCart cu tema proprie, zero date structurate in pagina.

    Masurat la G2A-1 (2026-08-17) pe doua PDP-uri cu reducere reala: domeniul
    n-are ld+json, n-are microdata si n-are OG de pret, deci fluxul generic ridica
    `no_product_data` pe orice pagina de produs (pinuit de testul-garda).

    UN singur fetch, prin poarta guarded C-14.
    """
    html = _fetch_text_guarded(url)
    soup = BeautifulSoup(html, "html.parser")

    # `<h1>` e GOL pe domeniu (masurat), deci numele vine din `<title>`.
    titlu = soup.find("title")
    name = _clean_text(titlu.get_text(" ", strip=True)) if titlu is not None else None

    # --- Pretul platit -------------------------------------------------------
    # Ancorarea in `.product-price` e OBLIGATORIE, nu cosmetica: `.discount-price`
    # apare de DOUA ori pe pagina, iar al doilea nod e `.discount-price.nav-price`
    # din bara de sus. Un selector neancorat ar putea citi bara in loc de produs.
    #
    # `.price-unit` ("/ buc.") se scoate INAINTE de parsare: apare doar la unele
    # produse, iar parserul strict ar respinge textul cu sufix — adica pretul s-ar
    # pierde exact pe produsele vandute la bucata.
    price = None
    nod = soup.select_one(".product-price .discount-price")
    if nod is not None:
        bloc = BeautifulSoup(str(nod), "html.parser")
        for unitate in bloc.select(".price-unit"):
            unitate.decompose()
        price = _parse_pret_powerup(bloc.get_text("", strip=True))

    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Pagina powerup fara <title>: {(url or '')[:120]}")
    if price is None:
        raise ProductExtractionError(
            "no_product_data",
            f"Pagina powerup fara pret citibil in .product-price .discount-price: "
            f"{(url or '')[:120]}")
    if price <= 0:
        raise ProductExtractionError(
            "invalid_price", f"Pret invalid ({price!r}) la '{name[:60]}'")

    return {
        "name": name,
        "price": price,
        # MONEDA din COD, si e singura intrare unde se intampla asta. Pagina n-o
        # poarta nicaieri ca data structurata: fara ld+json, fara microdata, fara
        # OG — masurat pe ambele PDP-uri. Singurul indiciu e sufixul "LEI" din
        # textul vizibil, pe care parserul strict deja il cere ca sa accepte
        # valoarea, deci constanta nu presupune nimic ce nu s-a verificat.
        #
        # A NU se generaliza tiparul: pe domeniile unde moneda E masurabila
        # (ld+json, microdata, atribut) ea se citeste din pagina, fiindca o
        # constanta ar ascunde exact momentul in care magazinul si-o schimba.
        "currency": "RON",
        # STOC: None NECONDITIONAT, si e o lipsa ONESTA, nu o decizie masurata ca
        # la elefant. G2A-1 n-a sondat nicio pagina de produs EPUIZAT, deci nu
        # exista ramura negativa cu care sa se compare semnalele. Pe /refurbished-sh
        # produsele sunt bucati unice, deci stocul chiar conteaza — tiparul
        # foto-erhardt. O micro-sonda viitoare pe un produs epuizat poate ridica
        # asta la True/False; pana atunci avalul e tri-state si afiseaza
        # "Stoc necunoscut", ceea ce e informatie corecta.
        "in_stock": None,
        "is_aggregate": False,
        "variants": None,
        "image_url": _meta(soup, "og:image"),
        "canonical_url": _canonical_url(soup, url),
        "domain": _domain_of(url),
        "method": "powerup_opencart",
        "override_applied": False,
    }


# ── intersport.ro (G2F-1b / G2F-2) ───────────────────────────────────────────

# Pretul sta in ATRIBUT, cu virgula zecimala: `data-current-price="305,99"`.
_INTERSPORT_PRET_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})$")


def _parse_pret_intersport(text) -> float | None:
    """Pretul dintr-un atribut `data-current-price`, parsare STRICTA.

    Ca la elefant si powerup, NU trece prin `_parse_price_any`: acela e permisiv
    prin design si ar transforma un text corupt intr-un numar plauzibil. Sursa are
    UN singur format masurat, iar abaterea de la el inseamna ca pagina s-a schimbat
    — semnal pe care il vrem ca esec curat, nu ca reparatie tacuta.
    """
    if not isinstance(text, str):
        return None
    curat = re.sub(r"\s+", "", text.replace("\xa0", "")).strip()
    potrivire = _INTERSPORT_PRET_RE.match(curat)
    if potrivire is None:
        return None
    try:
        return float(f"{potrivire.group(1).replace('.', '')}.{potrivire.group(2)}")
    except ValueError:
        return None


def _extract_intersport(url: str) -> dict:
    """intersport.ro — zero date structurate de produs.

    Masurat la G2F-1b (2026-08-18) pe doua PDP-uri cu preturi distincte: ld+json are
    doar `Organization` si `BreadcrumbList`, iar `[itemtype*="Product"]` lipseste cu
    totul. Exista un `itemprop="price"` pe nodul de pret, dar e ORFAN — fara
    `itemscope` de `Product` in jur — deci fluxul de microdata al extractorului
    generic nu-l vede, si genericul ridica `no_product_data` (pinuit de test).

    UN singur fetch, prin poarta guarded C-14.
    """
    html = _fetch_text_guarded(url)
    soup = BeautifulSoup(html, "html.parser")

    titlu = soup.find("h1")
    name = _clean_text(titlu.get_text(" ", strip=True)) if titlu is not None else None
    if not name:
        titlu = soup.find("title")
        name = _clean_text(titlu.get_text(" ", strip=True)) if titlu is not None else None

    # --- Pretul platit ------------------------------------------------------
    # ANCORAREA in `.current-price` e obligatorie, si nu din eleganta: pagina mai
    # contine `span.points-gain` cu EXACT aceeasi valoare, dar alt inteles —
    # „305,99 puncte" de fidelitate, in `div.points-gain-container.hidden`. O
    # selectie libera pe cifra sau pe atribut ar putea citi punctele in loc de pret.
    price = None
    nod = soup.select_one(".current-price[data-current-price]")
    if nod is not None:
        price = _parse_pret_intersport(nod.get("data-current-price"))
    if price is None:
        # Rezerva pe TEXTUL aceluiasi nod ancorat, nu pe alt selector: daca
        # atributul dispare, textul „305,99 LEI" ramane in acelasi loc.
        nod = soup.select_one(".current-price")
        if nod is not None:
            brut = re.sub(r"(?i)\s*lei\s*$", "", nod.get_text(" ", strip=True))
            price = _parse_pret_intersport(brut)

    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Pagina intersport fara titlu: {(url or '')[:120]}")
    if price is None:
        raise ProductExtractionError(
            "no_product_data",
            f"Pagina intersport fara pret citibil in .current-price: "
            f"{(url or '')[:120]}")
    if price <= 0:
        raise ProductExtractionError(
            "invalid_price", f"Pret invalid ({price!r}) la '{name[:60]}'")

    return {
        "name": name,
        "price": price,
        # MONEDA din COD. Pagina scrie „LEI" doar in textul de langa pret, in niciun
        # atribut si in nicio data structurata — la fel ca powerup. A NU se
        # generaliza tiparul: unde moneda E masurabila, se citeste din pagina,
        # fiindca o constanta ar ascunde exact momentul in care magazinul o schimba.
        "currency": "RON",
        # STOC: None NECONDITIONAT, si e o lipsa ONESTA, nu o decizie masurata.
        # Semnalele se contrazic pe ACEEASI pagina — „Adauga in cos" x2, „stoc" x10,
        # „Indisponibil" x3 — plauzibil fiindca stocul e PER MARIME, iar pagina nu
        # spune nimic despre produs ca intreg.
        #
        # NU „repara" asta cu `div.out-of-stock`: el apare pe TOATE cele 30 de
        # carduri ale listarii /sale/, langa butonul de cos, si nu are `display:none`
        # inline — e sablon ascuns prin CSS extern, exact tiparul `data-sold-out-text`
        # de la elefant (ELF-1b). Ca semnal de stoc ar da False pe tot catalogul.
        #
        # Nicio pagina de produs complet epuizat n-a fost sondata, deci ramura
        # negativa e NEMASURATA. Avalul e tri-state si afiseaza „Stoc necunoscut".
        "in_stock": None,
        "is_aggregate": False,
        "variants": None,
        "image_url": _meta(soup, "og:image"),
        "canonical_url": _canonical_url(soup, url),
        "domain": _domain_of(url),
        "method": "intersport_custom",
        "override_applied": False,
    }


def _obiect_json_incadrator(text: str, poz: int) -> str | None:
    """Obiectul JSON complet care CONTINE pozitia `poz`, prin potrivire de acolade.

    Starea cellini nu e un `<script type="application/json">` pe care sa-l putem
    incarca intreg: e cod JS cu obiecte inserate. Se decupeaza deci obiectul din
    jurul unei potriviri si se parseaza doar el.
    """
    i, adanc = poz, 0
    while i >= 0:
        c = text[i]
        if c == "}":
            adanc += 1
        elif c == "{":
            if adanc == 0:
                break
            adanc -= 1
        i -= 1
    if i < 0:
        return None
    j, adanc = poz, 0
    n = len(text)
    while j < n:
        c = text[j]
        if c == "{":
            adanc += 1
        elif c == "}":
            if adanc == 0:
                break
            adanc -= 1
        j += 1
    if j >= n:
        return None
    return text[i:j + 1]


def _cellini_obiect_propriu(html: str, url: str) -> dict | None:
    """Obiectul de produs AL PAGINII din starea cellini, sau None.

    De ce nu „primul obiect cu pret": pagina poarta 48 de obiecte cu `price` (48 pe
    fiecare din cele doua PDP-uri masurate la G2F-7) — restul sunt carusele de
    recomandari. Si de ce nu DOM-ul: textul vizibil are ~70 de preturi distincte,
    dintre care 8 IDENTICE intre cele doua pagini de produse diferite; o extractie
    pe text ar da, sistematic, pretul altui produs.

    Legarea de pagina se face pe cheia `url` a obiectului, care poarta EXACT numele
    de fisier al PDP-ului (masurat pe ambele dump-uri:
    `cercei-...-au-yk18ce26286.html` si `colier-...-ad-yk18co26296.html`), si se
    incruciseaza cu `code` (`AU_YK18CE26286` / `AD_YK18CO26296`). Pe ambele pagini
    EXACT UNUL dintre cele 48 de obiecte poarta codul paginii — identificarea e
    neambigua, nu o alegere din 48.
    """
    fisier = urllib.parse.urlparse(url or "").path.rsplit("/", 1)[-1]
    if not fisier:
        return None
    gasite, vazute = [], set()
    # `\/` apare cand starea e serializata cu slash-uri escapate; ambele forme se cauta.
    for varianta in {fisier, fisier.replace("/", r"\/")}:
        for m in re.finditer(re.escape(varianta), html or ""):
            brut = _obiect_json_incadrator(html, m.start())
            if not brut or len(brut) > 200_000:
                continue
            cheie = (brut[:80], len(brut))
            if cheie in vazute:
                continue
            vazute.add(cheie)
            try:
                obiect = json.loads(brut)
            except Exception:                                   # noqa: BLE001
                continue
            if not isinstance(obiect, dict) or "price" not in obiect:
                continue
            if str(obiect.get("url") or "").rsplit("/", 1)[-1] != fisier:
                continue
            gasite.append(obiect)
    if not gasite:
        return None
    # Ambiguitatea nu se rezolva prin „ia-l pe primul": daca doua obiecte pretind
    # aceeasi pagina cu preturi DIFERITE, nu stim care e produsul, deci nu ghicim.
    preturi = {repr(o.get("price")) for o in gasite}
    if len(preturi) > 1:
        return None
    return gasite[0]


def _cellini_pret(obiect: dict):
    """Pretul in lei din obiectul de stare, fara nicio parsare de text vizibil.

    `price` e INTREGUL de lei (masurat: 6930 si 27990, int), iar banii stau separat
    in `decimalprice` ("00" pe ambele masuratori), cu `beautifulprice` = "6.930,00"
    ca forma afisata. Le combinam DELIBERAT: daca `price` ar fi luat singur, un
    produs de 6930,50 lei ar fi raportat 6930 — o pierdere tacuta de bani, si exact
    genul de eroare pe care n-o prinde niciun test scris pe preturi rotunde.
    Combinatia e corecta si daca `price` s-ar dovedi cindva a purta deja zecimalele:
    partea intreaga plus banii da acelasi numar.

    Tipul e verificat STRICT: `price` trebuie sa fie int/float real (nu bool, nu
    sir). Un sir ar insemna ca magazinul a schimbat forma starii, si atunci vrem sa
    cada zgomotos, nu sa ghicim printr-un parser de text.
    """
    brut = obiect.get("price")
    if isinstance(brut, bool) or not isinstance(brut, (int, float)):
        return None
    lei = int(brut)
    bani = obiect.get("decimalprice")
    if isinstance(bani, str) and re.fullmatch(r"\d{2}", bani.strip()):
        return round(lei + int(bani) / 100.0, 2)
    return float(brut)


def _extract_cellini(url: str) -> dict:
    """cellini.ro — datele de produs traiesc DOAR in starea paginii (G2F-7/G2F-8).

    Masurat pe doua PDP-uri reale (sonda G2F-7, pasa de corectie): ld+json are doar
    `Organization`, `WebSite` si `BreadcrumbList` — niciun `Product` —, microdata
    lipseste, iar genericul ridica `no_product_data` (pinuit de test). Tot ce
    descrie produsul sta in obiectele de stare ale paginii: `price`, `oldprice`,
    `vat`, `stock`, `code`, `url`.

    UN singur fetch, prin poarta guarded C-14.
    """
    html = _fetch_text_guarded(url)
    obiect = _cellini_obiect_propriu(html, url)
    if obiect is None:
        raise ProductExtractionError(
            "no_product_data",
            f"Pagina cellini fara obiect de produs propriu in stare: "
            f"{(url or '')[:120]}")

    # NUMELE sta in cheia `product`, nu in `name`: masurat pe ambele PDP-uri,
    # `name` e None, iar `metatitle` si `subtitle` sunt siruri goale.
    # NU exista rezerva pe DOM, si asta e deliberat: `<h1>`-ul paginii scrie
    # „Bijuterii" — titlul CATEGORIEI, nu al produsului — deci o rezerva pe el ar
    # produce un nume gresit-dar-plauzibil pe TOT magazinul (prins la verificarea
    # live a G2F-8, unde exact asta s-a intamplat). Mai bine cade zgomotos.
    name = (_clean_text(obiect.get("product"))
            or _clean_text(obiect.get("name"))
            or _clean_text(obiect.get("metatitle")))
    price = _cellini_pret(obiect)

    if not name:
        raise ProductExtractionError(
            "no_product_data", f"Produs cellini fara nume: {(url or '')[:120]}")
    if price is None:
        raise ProductExtractionError(
            "no_product_data",
            f"Produs cellini fara `price` numeric in stare: {(url or '')[:120]}")
    if price <= 0:
        raise ProductExtractionError(
            "invalid_price", f"Pret invalid ({price!r}) la '{name[:60]}'")

    # MONEDA se CITESTE, nu se pune din cod: obiectul poarta `currencyname` ("Lei"
    # pe ambele masuratori), plus `currencyid: "1"` si `ronvalue: "1.0000"`. Unde
    # moneda e masurabila o citim, fiindca o constanta ar ascunde exact momentul in
    # care magazinul ar incepe sa afiseze alta. `RON` ramane doar plasa de siguranta.
    currency = _normalize_currency(obiect.get("currencyname")) or "RON"

    # STOC: `stock` e un sir in limba romana — masurat „in stoc" pe AMBELE PDP-uri.
    # Forma NEGATIVA n-a fost masurata (n-am intalnit niciun produs epuizat), deci
    # afirmam DOAR pozitivul: orice altceva ramane None (necunoscut), niciodata
    # False. A inventa un vocabular de epuizare nemasurat ar ascunde produse
    # cumparabile — exact greseala pe care flagul de la vivre a corectat-o.
    stoc_brut = obiect.get("stock")
    in_stock = True if (isinstance(stoc_brut, str)
                        and "in stoc" in stoc_brut.strip().lower()) else None

    soup = BeautifulSoup(html, "html.parser")
    # CANONICUL nu se ia din pagina, si nici din `obiect["canonical"]` (masurat gol
    # pe ambele PDP-uri): `<link rel=canonical>` al paginii arata spre CATEGORIE
    # (`/bijuterii`), identic pe produse diferite. Folosit ca atare, ar da tuturor
    # produselor cellini aceeasi identitate — adica orice deduplicare pe canonic
    # le-ar contopi intr-unul singur. Se reconstruieste din `obiect["url"]`, care e
    # numele de fisier al PDP-ului, rezolvat fata de URL-ul cerut.
    tinta = _clean_text(obiect.get("url"))
    canonical = (urllib.parse.urljoin(url, tinta) if tinta
                 else urllib.parse.urldefrag(url or "")[0] or (url or ""))
    return {
        "name": name,
        "price": price,
        "currency": currency,
        "in_stock": in_stock,
        "is_aggregate": False,
        # `oldprice` ("9240.00" / "37320.00") si `save_percent` EXISTA in stare, dar
        # NU intra in contractul de rezultat: referinta se documenteaza pentru axa D
        # (listarea promo poarta price+oldprice per card) — vezi docs.
        "variants": None,
        "image_url": _meta(soup, "og:image"),
        "canonical_url": canonical,
        "domain": _domain_of(url),
        "method": "cellini_datalayer",
        "override_applied": False,
    }


CUSTOM_EXTRACTORS: dict[str, callable] = {
    "asos.com": _extract_asos,
    "elefant.ro": _extract_elefant,
    "powerup.ro": _extract_powerup,
    "intersport.ro": _extract_intersport,
    "cellini.ro": _extract_cellini,
}


def _custom_extractor_for(url: str):
    """Extractorul dedicat al domeniului, sau None pentru fluxul generic."""
    try:
        hostname = (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return None
    if not hostname:
        return None
    for domain, extractor in CUSTOM_EXTRACTORS.items():
        if hostname == domain or hostname.endswith("." + domain):
            return extractor
    return None


def extract_product(url: str, max_retries: int = 3) -> dict:
    """Fetch + parse pentru pagina de produs de la `url`.

    Ridica ProductExtractionError cu reason-ul potrivit; nu logheaza (apelantul
    decide ce si unde emite).
    """
    if not url or not str(url).strip():
        raise ProductExtractionError("domain_not_allowed", "URL gol")

    # DISCOVERY-2: domeniile din CUSTOM_EXTRACTORS nu trec prin fluxul generic —
    # pe ele pagina pur si simplu nu poarta datele, deci n-ar avea ce parsa.
    # Extractorul custom ridica aceleasi ProductExtractionError si foloseste aceeasi
    # poarta guarded, deci apelantii nu vad nicio diferenta.
    custom = _custom_extractor_for(url)
    if custom is not None:
        return custom(url)

    # SHOP-1, simetric cu blocul de mai sus: magazinele Shopify au datele in
    # endpoint-ul Ajax, nu in HTML. Acelasi contract de rezultat si aceleasi
    # ProductExtractionError, deci apelantii nu vad nicio diferenta.
    if _shopify_extractor_for(url):
        return _extract_shopify(url)

    # BR-1, al treilea bloc simetric: Grupul 4 — magazine unde datele EXISTA in
    # pagina, dar numai dupa randare, sau unde cererea fara browser real e respinsa.
    # Acolo fetch-ul se face cu un browser; parsarea de dupa e identica.
    if _browser_domain_for(url):
        return _extract_via_browser(url)

    # Import lenes, in corpul functiei: evita ciclul de import de cand, in
    # RETAIL-3, scraper_service va importa acest modul. Allow-list-ul SSRF C-14
    # din scraper_service ramane SINGURA poarta de fetch — nu o dublam aici.
    from app.services.scraper_service import _fetch_shop_url_guarded, _is_allowed_shop_url

    last_status = None
    saw_challenge = False
    last_parse_exc = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            time.sleep(random.uniform(1, 3))

        response = _fetch_shop_url_guarded(url, headers=_HEADERS, timeout=_TIMEOUT)
        if response is None:
            # None = URL neautorizat (SSRF blocat) SAU eroare de retea / redirect invalid.
            if not _is_allowed_shop_url(url):
                # Fail-fast: un domeniu interzis nu devine permis daca mai asteptam.
                raise ProductExtractionError(
                    "domain_not_allowed", f"Domeniu neautorizat (allow-list C-14): {url[:120]}")
            continue  # eroare tranzitorie -> mai incercam

        last_status = response.status_code
        # Cloudflare Managed Challenge, ca la fetch_pcgarage_price_from_url.
        if (response.status_code == 403
                or response.headers.get("cf-mitigated") == "challenge"
                or "just a moment" in response.text[:2000].lower()):
            saw_challenge = True
            continue
        if response.status_code != 200:
            continue

        # Retry pe no_product_data — ASIGURARE DEFENSIVA, nu curativa. Sonda
        # FASHION-4 (2026-07-28) NU a reprodus servirea inconsistenta observata la
        # 2026-07-26: 48/48 extractii OK pe aboutyou.ro + trendyol.com, cu ld+json
        # prezent pe fiecare raspuns si HTML identic la octet intre incercari.
        # Adaugam totusi calea fiindca are cost ZERO — se executa doar acolo unde
        # azi se esua imediat — si absoarbe o eventuala recidiva SPORADICA.
        # O recidiva LIPITA (3/3 esec) iese la suprafata identic cu comportamentul
        # de azi: aceeasi exceptie no_product_data, doar dupa mai multe incercari.
        #
        # DOAR acest reason reintra in bucla. Restul (invalid_price etc.) propaga
        # imediat: acolo pagina CHIAR poarta date de produs, deci un re-fetch nu
        # schimba raspunsul, iar retry-ul ar fi trafic inutil.
        try:
            return parse_product_html(response.text, url)
        except ProductExtractionError as exc:
            if exc.reason != "no_product_data":
                raise
            last_parse_exc = exc
            continue  # sleep-ul vine de la inceputul iteratiei urmatoare

    # Precedenta erorilor: parse > challenge > fetch_failed. Un esec de parsare e
    # informatia cea mai specifica — dovedeste ca am primit un 200 pe care chiar
    # l-am citit, spre deosebire de "n-am ajuns la continut".
    if last_parse_exc is not None:
        raise last_parse_exc
    if saw_challenge:
        raise ProductExtractionError(
            "challenge", f"Blocat de challenge anti-bot dupa {max_retries} incercari: {url[:120]}")
    raise ProductExtractionError(
        "fetch_failed",
        f"Fetch esuat dupa {max_retries} incercari (ultimul status: {last_status}): {url[:120]}")
