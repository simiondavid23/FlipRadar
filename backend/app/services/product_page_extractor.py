"""RETAIL-1 — extractor generic de pagina de produs (nume, pret, moneda, stoc).

Fundatia monitorizarii de pret prin link: primeste URL-ul unei pagini de produs
si intoarce un dict normalizat. Parsarea (`parse_product_html`) e PURA — fara
retea, fara DB — ca sa fie testabila offline pe HTML capturat; fetch-ul live
(`extract_product`) refoloseste infrastructura existenta din scraper_service.

Ordinea surselor, per camp: override pe domeniu > JSON-LD > OpenGraph.
JSON-LD (schema.org/Product) e sursa principala fiindca e stabila intre magazine
si nu depinde de clase CSS; OG e plasa de siguranta; DOMAIN_OVERRIDES ramane
supapa pentru magazinele care nu publica date structurate corecte.

Modulul nu logheaza nimic (log_manager ramane la apelanti) si nu importa
scraper_service la nivel de modul — vezi comentariul din extract_product.
"""
import json
import random
import re
import time
import urllib.parse

from bs4 import BeautifulSoup


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
#   price_selector / name_selector / image_selector — selectori CSS
#   out_of_stock_text — substring case-insensitive in pagina => in_stock False
#   currency — moneda fixa a magazinului
DOMAIN_OVERRIDES: dict[str, dict] = {
    # eMAG — sonda RETAIL-5b (2026-07-26): 5/5 egalitate cu pretul din lista de
    # cautare, inclusiv pe o pagina multi-oferta unde JSON-LD dadea 5689.42 iar
    # afisat era "de la 3.459,99" (selectorul a reparat divergenta).
    #
    # DE CE selector si nu price_regex: cauza divergentei NU e Genius (ipoteza de
    # la RETAIL-3a, infirmata), ci paginile cu mai multe oferte — eMAG afiseaza
    # "de la <minim>", pe cand JSON-LD si starea JS `EM.product` poarta oferta
    # PRINCIPALA. Regexurile pe starea incorporata esueaza fiecare pe cate un tip
    # de pagina (masurat in RETAIL-5); doar elementul afisat e corect pe ambele.
    # Textul vine spart in span-uri ("3.459 , 99 Lei"), pe care _parse_price_any
    # il recompune corect.
    #
    # NUANTA ACCEPTATA: pe paginile multi-oferta pretul devine cel afisat, dar
    # `in_stock` ramane cel din JSON-LD, adica al ofertei PRINCIPALE, nu al
    # ofertei minime. Stocul e tri-state si informativ; pretul e cel care intra
    # in istoric si in alerte, deci prioritatea e corectitudinea lui.
    "emag.ro": {"price_selector": ".product-new-price"},
}

# Domeniile pe care extractorul a fost validat pe pagini de produs REALE (sonda
# RETAIL-3a, 2026-07-26). refresh_source le reimprospateaza citind direct pagina de
# produs; celelalte raman pe re-cautare. Un domeniu se adauga aici DOAR dupa o sonda
# live, niciodata pe presupunere: o extractie gresita ar scrie preturi false in istoric.
VALIDATED_DOMAINS: set[str] = {
    # 3/3 pagini extrase prin JSON-LD, pret identic cu cel din lista de cautare.
    "altex.ro",
    # 5/5 pagini extrase prin JSON-LD.
    #
    # LIMITARE CUNOSCUTA (sonda RETAIL-5, 2026-07-26) — NU e legata de Genius, cum
    # se banuia la RETAIL-3a: pe paginile cu MAI MULTE oferte eMAG afiseaza
    # "de la <cel mai mic pret>", in timp ce JSON-LD poarta oferta principala.
    # Exemplu masurat (Lenovo IdeaPad Slim 3, 2 oferte): afisat 3.459,99 lei,
    # JSON-LD 5689.42. Pe paginile cu o singura oferta relevanta, JSON-LD = afisat.
    # Niciun regex pe starea JS incorporata nu acopera ambele cazuri: EM.product
    # da oferta principala (gresit pe multi-oferta), iar EM.multiple_min_price si
    # datalayer-ul dau minimul altor oferte (gresit pe restul). Ce a mers 5/5 pe
    # ambele tipuri de pagina e selectorul pretului afisat, ".product-new-price"
    # — candidatul pentru un price_selector, intr-un task dedicat.
    "emag.ro",
}
# NU sunt validate: sole.ro si farmaciatei.ro (degradate la sonda RETAIL-1 — 502 pe
# pagina de produs, respectiv cautare goala) si pcgarage.ro (n-a avut URL-uri de
# produs la sonda RETAIL-3a; refresh-ul lui ramane pe fetch_pcgarage_price_from_url,
# care trece de Cloudflare cu retry).


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
    template-uri cu variabile neinlocuite) nu trebuie sa arunce restul paginii.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        yield from _flatten_jsonld(data)


def _is_product(obj: dict) -> bool:
    """@type "Product", inclusiv cand @type e lista (["Product", "Thing"])."""
    node_type = obj.get("@type")
    if isinstance(node_type, str):
        return node_type.strip().lower() == "product"
    if isinstance(node_type, list):
        return any(isinstance(t, str) and t.strip().lower() == "product" for t in node_type)
    return False


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

    `offers` poate fi dict sau lista — pe lista castiga primul cu pret. In cadrul
    unei oferte ordinea e price > lowPrice (AggregateOffer => is_aggregate) >
    priceSpecification.price. Flag-ul de candidat separa "nu exista pret in
    pagina" (no_product_data) de "exista dar e invalid" (invalid_price).
    """
    saw_candidate = False
    first_offer = None
    for offer in (offers if isinstance(offers, list) else [offers]):
        if not isinstance(offer, dict):
            continue
        if first_offer is None:
            first_offer = offer
        for key, is_aggregate in (("price", False), ("lowPrice", True)):
            if offer.get(key) is not None:
                saw_candidate = True
                price = _parse_price_any(offer.get(key))
                if price is not None:
                    return price, is_aggregate, offer, saw_candidate
        spec = offer.get("priceSpecification")
        for node in (spec if isinstance(spec, list) else [spec]):
            if isinstance(node, dict) and node.get("price") is not None:
                saw_candidate = True
                price = _parse_price_any(node.get("price"))
                if price is not None:
                    return price, False, offer, saw_candidate
    return None, False, first_offer, saw_candidate


def _collect_jsonld(soup):
    """(rezultat_complet | None, primul_candidat | None).

    Castiga primul Product cu nume SI pret rezolvabil; primul Product intalnit se
    pastreaza oricum ca `partial`, ca sa putem clasifica eroarea (un Product cu
    pret "0" e invalid_price, nu no_product_data).
    """
    partial = None
    for obj in _iter_jsonld_objects(soup):
        if not _is_product(obj):
            continue
        price, is_aggregate, offer, saw_candidate = _price_from_offers(obj.get("offers"))
        offer = offer or {}
        candidate = {
            "name": _clean_text(obj.get("name")),
            "price": price,
            "currency": _normalize_currency(offer.get("priceCurrency") or obj.get("priceCurrency")),
            "in_stock": _normalize_availability(offer.get("availability")),
            "is_aggregate": is_aggregate,
            "image_url": _first_image(obj.get("image")),
            "price_seen": saw_candidate,
        }
        if partial is None:
            partial = candidate
        if candidate["name"] and price is not None and price > 0:
            return candidate, partial
    return None, partial


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
    }


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
    override_applied = _apply_override(soup, html or "", result, DOMAIN_OVERRIDES.get(domain) or {})

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


def extract_product(url: str, max_retries: int = 3) -> dict:
    """Fetch + parse pentru pagina de produs de la `url`.

    Ridica ProductExtractionError cu reason-ul potrivit; nu logheaza (apelantul
    decide ce si unde emite).
    """
    if not url or not str(url).strip():
        raise ProductExtractionError("domain_not_allowed", "URL gol")

    # Import lenes, in corpul functiei: evita ciclul de import de cand, in
    # RETAIL-3, scraper_service va importa acest modul. Allow-list-ul SSRF C-14
    # din scraper_service ramane SINGURA poarta de fetch — nu o dublam aici.
    from app.services.scraper_service import _fetch_shop_url_guarded, _is_allowed_shop_url

    last_status = None
    saw_challenge = False
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

        return parse_product_html(response.text, url)

    if saw_challenge:
        raise ProductExtractionError(
            "challenge", f"Blocat de challenge anti-bot dupa {max_retries} incercari: {url[:120]}")
    raise ProductExtractionError(
        "fetch_failed",
        f"Fetch esuat dupa {max_retries} incercari (ultimul status: {last_status}): {url[:120]}")
