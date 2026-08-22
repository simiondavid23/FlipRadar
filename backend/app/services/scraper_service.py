import asyncio
import json
import random
import re
import threading
import time
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.utils.category_mapper import infer_category_from_name
from app.services.log_manager import log_manager
from app.services.shop_registry import (
    SHOP_REGISTRY, impersonate_overrides, option_map, overrides_option_map,
)
# AMZ-1a: base_scraper e FRUNZA (importa doar stdlib: os, random, enum, typing), deci
# importul asta top-level nu poate inchide un ciclu — verificat la PASUL 0.3.
# `classify` si `Outcome` se CONSUM, nu se adapteaza: ordinea lor de decizie e
# contract testat pe calea Radar.
from app.services.radar.base_scraper import (
    INTERSTITIAL_MAX_BYTES, Outcome, classify,
)
# Directia importurilor e sigura in acest sens: extractorul importa scraper_service
# DOAR lenes (in corpul lui extract_product, pentru allow-list-ul SSRF), tocmai ca
# importul asta top-level sa nu inchida un ciclu.
from app.services.product_page_extractor import (
    match_shop_domain,
    extract_product,
    ProductExtractionError,
    VALIDATED_DOMAINS,
)


_ALTEX_HEADERS = {
    "Origin": "https://altex.ro",
    "Referer": "https://altex.ro/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

_SOLE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://sole.ro",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}

_FARMACIATEI_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://comenzi.farmaciatei.ro/",
    "Upgrade-Insecure-Requests": "1",
}

_EMAG_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.emag.ro/",
    "Upgrade-Insecure-Requests": "1",
}

_PCGARAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.pcgarage.ro/",
    "Upgrade-Insecure-Requests": "1",
}

# IMP-2: profilul implicit vine din sursa centralizata (IMP-1), nu dintr-o
# versiune fixa care imbatraneste tacut. Per domeniu se poate forta alt profil
# prin cheia `impersonate` din registru (vezi _impersonate_for).
from app.utils.http_profile import DEFAULT_IMPERSONATE as _IMPERSONATE  # noqa: E402

# Amprenta TLS/HTTP2 per domeniu, pentru magazinele pe care default-ul nu le
# deschide. Cheia e domeniul de baza; rezolvarea trece prin _impersonate_for,
# cu matching suffix-safe identic cu allow-list-ul C-14.
_IMPERSONATE_OVERRIDES: dict[str, str] = impersonate_overrides()

# ── RATE-1: interval minim intre cereri, per domeniu ─────────────────────────
#
# Masuratoarea-sursa (G2F-5, pasa de corectie, pe action.com): a PATRA cerere
# intr-un minut a primit 403 cu interstitiul Cloudflare „Just a moment...", iar
# ACELASI URL pe ACELASI profil a trecut cu 200 dupa o pauza de 95s. Ordinea
# cererilor a exclus celelalte doua explicatii: nu era ruta (aceeasi ruta trecuse)
# si nu era profilul (acelasi profil a trecut imediat dupa). Deci limitarea e pe
# RATA, iar raspunsul corect nu e alta amprenta, ci mai putine cereri pe minut.
#
# De ce AICI, pe poarta: `_fetch_shop_url_guarded` e punctul UNIC prin care trece
# tot traficul HTTP catre magazine — deal_scanner, listing_scanner, ambele cai din
# product_page_extractor (fluxul generic si extractoarele custom) si cele doua
# apeluri din acest modul. Pus in poarta, mecanismul acopera si scannerele viitoare
# fara ca cineva sa-si aminteasca sa-l cableze.
#
# Harta se deriva o SINGURA data, la import, exact ca `_IMPERSONATE_OVERRIDES`:
# registrul e un literal Python, deci oricum cere repornire ca sa se schimbe.
# Domeniile fara camp nu platesc nimic — pe registrul de azi harta are o singura
# intrare, iar cand e goala verificarea iese la prima linie, fara sa atinga lacatul.
_MIN_FETCH_INTERVALE: dict[str, int] = {
    domain: meta["min_fetch_interval_s"]
    for domain, meta in SHOP_REGISTRY.items()
    if meta.get("min_fetch_interval_s")
}

# Ultima cerere pe domeniu, in ceas MONOTON (nu wall-clock: o ajustare de ceas de
# sistem ar putea altfel sa para ca au trecut ore, sau sa blocheze o ora).
_ULTIMA_CERERE_PE_DOMENIU: dict[str, float] = {}
_LOCK_INTERVAL = threading.Lock()

# ── AMZ-1a: clasificarea blocajelor in poarta de fetch retail ────────────────
#
# Pana aici calea retail n-avea NICIO notiune de „blocat": `_fetch_shop_url_guarded`
# intorcea raspunsul brut, iar un interstitiu anti-bot servit cu 200 ajungea la
# extractor ca HTML valid si iesea ca `no_product_data` — adica „markup schimbat",
# nu „blocat". Diferenta se vede pana in UI: `no_product_data` da 422 („n-am putut
# extrage datele", care acuza parserul nostru), pe cand un blocaj da 502 („magazinul
# a blocat cererea"), care e adevarul.
#
# Sonda AMZ-0 a dovedit ca unghiul mort e real in modul cel mai direct cu putinta:
# propria ei masuratoare a fost citita gresit exact asa.
#
# Cele doua harti se deriva o SINGURA data, la import, exact ca `_IMPERSONATE_OVERRIDES`
# si `_MIN_FETCH_INTERVALE` — registrul e un literal Python, deci oricum cere repornire.
_MARKERI_BLOCAJ_DOMENIU: dict[str, tuple] = overrides_option_map("block_markers")
_PRAG_INTERSTITIU_DOMENIU: dict[str, int] = overrides_option_map("interstitial_max_bytes")

# AWS WAF serveste provocarea JS cu status 202, iar `classify()` verifica markerii de
# body NUMAI pe 200 — deci fara ramura proprie provocarea ar iesi `OK` si pagina de
# 2 008 octeti ar ajunge la extractor. Masurat in AMZ-0 pe amazon.de (2 008 octeti,
# identic pe toate cele 5 amprente TLS incercate), dar tinut GENERIC: AWS WAF nu e
# specific Amazon, iar `classify` nu se modifica fiindca ordinea lui e contract.
_MARKERI_WAF: tuple[str, ...] = ("awswafcookiedomainlist", "token.awswaf.com")


# ── AMZ-1: cookie jar + bootstrap de sesiune, per domeniu ────────────────────
#
# Unele magazine nu servesc nimic unei sesiuni RECI. Masurat pe amazon.de
# (AMZ-0/0c): primele 20 de cereri fara cookie-uri au fost blocate 20/20, pe patru
# rute si cu trei mecanisme diferite. Ruta `glow` raspunde insa 200 pe aceeasi
# sesiune rece si emite cookie-urile; dupa ele, 90/90 de cereri OK la 5-20 s.
#
# Mecanismul e OPT-IN prin registru: domeniile fara `cookie_jar` nu vad nicio
# diferenta — nu li se trimite `cookies=`, nu se atinge discul, nu se ia lacatul.
_COOKIE_JAR_DOMENIU: dict[str, str] = option_map("cookie_jar")
_BOOTSTRAP_URL_DOMENIU: dict[str, str] = option_map("bootstrap_url")

# Racire: cel mult UN bootstrap per jar la 10 minute, la nivel de PROCES. Fara ea,
# un tick cu 20 de produse urmarite pe acelasi magazin ar declansa 20 de bootstrap-uri
# — adica exact tiparul de trafic pe care incercam sa-l evitam.
_RACIRE_BOOTSTRAP_S = 600

_JARURI: dict[str, dict] = {}                 # nume jar -> {cookie: valoare}
_JARURI_INCARCATE: set[str] = set()           # jar-uri citite deja de pe disc
_ULTIMUL_BOOTSTRAP: dict[str, float] = {}     # nume jar -> ceas MONOTON
# Reentrant: `_salveaza_jar` e chemat din interiorul sectiunii critice a fetch-ului.
_LOCK_JAR = threading.RLock()

# Bootstrap-ul se face printr-un apel RECURSIV la poarta (ca sa mosteneasca
# allow-list, interval si clasificare). Fara steag, cererea de bootstrap ar vedea si
# ea jar-ul gol si ar cere alt bootstrap, la infinit. Steagul e per FIR, nu global:
# doua fire pe domenii diferite nu trebuie sa se blocheze reciproc.
_local_bootstrap = threading.local()


def _in_bootstrap() -> bool:
    return getattr(_local_bootstrap, "activ", False)


def _cale_jar(nume: str):
    """`<DATA_DIR>/data/cookies_<nume>.json` — acelasi director cu sesiunea Facebook,
    deci sub aceeasi regula `.gitignore` (`backend/data/`)."""
    from app.config import DATA_DIR      # import local, ca la _default_facebook_session_path
    director = DATA_DIR / "data"
    director.mkdir(parents=True, exist_ok=True)
    return director / f"cookies_{nume}.json"


def _incarca_jar(nume: str) -> dict:
    """Jar-ul, citit de pe disc o SINGURA data per proces. Niciodata None."""
    with _LOCK_JAR:
        if nume in _JARURI_INCARCATE:
            return dict(_JARURI.get(nume) or {})
        jar = {}
        try:
            cale = _cale_jar(nume)
            if cale.is_file():
                brut = json.loads(cale.read_text(encoding="utf-8"))
                if isinstance(brut, dict):
                    jar = {str(k): str(v) for k, v in brut.items()}
        except Exception:                                       # noqa: BLE001
            jar = {}      # un jar corupt nu trebuie sa rupa fetch-ul; se re-creeaza
        _JARURI[nume] = jar
        _JARURI_INCARCATE.add(nume)
        return dict(jar)


def _salveaza_jar(nume: str, jar: dict) -> bool:
    """Persista DOAR daca s-a schimbat ceva. Intoarce True daca a scris pe disc.

    Comparatia pe continut, nu pe „am primit un raspuns": Amazon retrimite aceleasi
    cookie-uri la fiecare cerere, deci o scriere neconditionata ar insemna un write
    de disc pe fiecare produs urmarit, la fiecare tick.
    """
    with _LOCK_JAR:
        if _JARURI.get(nume) == jar:
            return False
        _JARURI[nume] = dict(jar)
        _JARURI_INCARCATE.add(nume)
        try:
            _cale_jar(nume).write_text(
                json.dumps(jar, indent=2, sort_keys=True), encoding="utf-8")
            return True
        except Exception:                                       # noqa: BLE001
            return False   # disc plin / drepturi: mergem mai departe cu jar-ul din RAM


def _goleste_jar(nume: str) -> None:
    with _LOCK_JAR:
        _JARURI[nume] = {}
        _JARURI_INCARCATE.add(nume)
        try:
            cale = _cale_jar(nume)
            if cale.is_file():
                cale.unlink()
        except Exception:                                       # noqa: BLE001
            pass


def _cookies_din_raspuns(response) -> dict:
    """Cookie-urile emise de raspuns, ca dict nume->valoare. Tolerant la forma."""
    out = {}
    try:
        for c in response.cookies.jar:
            out[c.name] = c.value
    except Exception:                                           # noqa: BLE001
        try:
            out = {str(k): str(v) for k, v in dict(response.cookies).items()}
        except Exception:                                       # noqa: BLE001
            out = {}
    return out


def _cheie_pe_domeniu(hostname: str, harta: dict):
    """Cheia din `harta` care acopera hostname-ul, cu GRANITA PE PUNCT.

    Aceeasi regula ca `_impersonate_for` si allow-list-ul C-14 (`m.emag.ro` ->
    `emag.ro`, dar `evil-emag.ro.attacker.com` -> None). Cele doua bucle mai vechi
    isi pastreaza deliberat varianta inline: refactorizarea lor n-are legatura cu
    AMZ-1a si ar largi diff-ul peste fisierele permise.
    """
    if not harta or not hostname:
        return None
    for domeniu in harta:
        if hostname == domeniu or hostname.endswith("." + domeniu):
            return domeniu
    return None


def _domeniu_din_url(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:                                           # noqa: BLE001
        return ""


def markeri_blocaj(domeniu: str) -> tuple:
    """Markerii SUPLIMENTARI de blocaj ai domeniului (peste BLOCK_MARKERS generici)."""
    cheie = _cheie_pe_domeniu(domeniu, _MARKERI_BLOCAJ_DOMENIU)
    return tuple(_MARKERI_BLOCAJ_DOMENIU.get(cheie) or ()) if cheie else ()


def prag_interstitiu(domeniu: str) -> int:
    """Pragul de octeti sub care markerii mai sunt concludenti, pentru domeniu."""
    cheie = _cheie_pe_domeniu(domeniu, _PRAG_INTERSTITIU_DOMENIU)
    if cheie is None:
        return INTERSTITIAL_MAX_BYTES
    return int(_PRAG_INTERSTITIU_DOMENIU.get(cheie) or INTERSTITIAL_MAX_BYTES)


def jar_pentru(url: str):
    """Numele jar-ului domeniului, sau None daca domeniul nu cere sesiune."""
    cheie = _cheie_pe_domeniu(_domeniu_din_url(url), _COOKIE_JAR_DOMENIU)
    return _COOKIE_JAR_DOMENIU.get(cheie) if cheie else None


def bootstrap_pentru(url: str):
    """URL-ul care emite cookie-urile de sesiune pentru domeniu, sau None."""
    cheie = _cheie_pe_domeniu(_domeniu_din_url(url), _BOOTSTRAP_URL_DOMENIU)
    return _BOOTSTRAP_URL_DOMENIU.get(cheie) if cheie else None


# Pagination safety caps (per-site) so a runaway query can't hammer a shop.
_MAX_PAGES_EMAG = 10         # eMAG serves ~72-78 cards per page
_MAX_PAGES_PCGARAGE = 15     # PCGarage serves ~20 cards per page
_MAX_PAGES_FARMACIATEI = 10  # Farmacia Tei serves ~60 cards per page
_MAX_ALTEX_SIZE = 100        # Fenrir API accepts size up to 100 in one call


def _altex_image_url(thumbnail: Optional[str]) -> str:
    if not thumbnail:
        return ""
    if thumbnail.startswith("http"):
        return thumbnail
    return f"https://s13emagst.akamaized.net/products/altex/media/catalog/product{thumbnail}"


def _altex_product_url(url_key: Optional[str], sku: Optional[str]) -> str:
    if not url_key or not sku:
        return "https://altex.ro/"
    return f"https://altex.ro/{url_key}/cpd/{sku}/"


_ALTEX_BAD_PATH_CHARS = re.compile(r'[/\\"\'<>{}|`]')


def _sanitize_altex_query(query: str) -> str:
    cleaned = _ALTEX_BAD_PATH_CHARS.sub(" ", query or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


_ALTEX_SKU_FROM_URL_RE = re.compile(r"/cpd/([^/?#]+)/?", re.IGNORECASE)


def _altex_sku_from_url(source_url: Optional[str]) -> Optional[str]:
    if not source_url:
        return None
    match = _ALTEX_SKU_FROM_URL_RE.search(source_url)
    return match.group(1) if match else None


def _sync_scrape_altex(query: str, max_results: int) -> list:
    """Apelează API-ul intern Fenrir al Altex (folosit de propriul frontend React).

    API-ul acceptă `size` până la ~100 într-un singur apel, deci nu e nevoie de
    buclă de paginare: cerem min(max_results, 100) dintr-o singură lovitură.
    """
    safe_query = _sanitize_altex_query(query)
    if not safe_query:
        return [{"error": "Query gol pentru Altex dupa sanitizare."}]
    encoded = urllib.parse.quote(safe_query)
    size = min(max(max_results, 1), _MAX_ALTEX_SIZE)
    url = f"https://fenrir.altex.ro/v2/catalog/search/{encoded}?size={size}"
    try:
        response = curl_requests.get(
            url,
            headers=_ALTEX_HEADERS,
            impersonate=_IMPERSONATE,
            timeout=20,
        )
    except Exception as exc:
        return [{"error": f"Eroare conexiune Altex: {exc}"}]

    if response.status_code != 200:
        return [{"error": f"Altex a returnat status {response.status_code}"}]

    try:
        data = response.json()
    except Exception as exc:
        return [{"error": f"Raspuns invalid de la Altex: {exc}"}]

    raw_products = data.get("products") or []
    products = []
    for item in raw_products[:max_results]:
        try:
            name = item.get("name") or ""
            if not name:
                continue
            price = float(item.get("price") or 0)
            url_key = item.get("url_key")
            sku = item.get("sku")
            in_stock = bool(item.get("stock_status")) and not item.get("is_eol")
            ean = item.get("ean_codes") or ""
            # RETAIL-AUDIT (5.3e): numele campului e la plural — daca API-ul intoarce
            # o LISTA, .strip() pe ea ar da AttributeError in filter_by_code si ar
            # omori tacut task-ul de cross-shop. Luam primul cod, ca string.
            if isinstance(ean, (list, tuple)):
                ean = ean[0] if ean else ""
            ean = str(ean)

            # --- Detectare reducere ---
            # Altex expune:
            #   price         -> prețul curent (posibil redus)
            #   regular_price -> prețul de listă (egal cu `price` când nu e în promoție)
            #   discount_type -> "none" când nu există reducere activă,
            #                    altfel ex: "percentage"
            original_price: Optional[float] = None
            is_on_sale = False
            try:
                regular_price = float(item.get("regular_price") or 0)
            except (TypeError, ValueError):
                regular_price = 0.0
            discount_type = (item.get("discount_type") or "none").lower()
            if (
                regular_price > 0
                and price > 0
                and regular_price > price
                and discount_type != "none"
            ):
                is_on_sale = True
                original_price = regular_price

            # FlipRadar — categorie: preferam categoria din raspunsul Fenrir,
            # cu inferenta din nume (KEYWORD_MAP) ca fallback.
            main_cat, sub_cat = infer_category_from_name(name, "altex")
            fenrir_cat = item.get("category_name")
            if not fenrir_cat:
                raw_cats = item.get("categories")
                if isinstance(raw_cats, str):
                    fenrir_cat = raw_cats
                elif isinstance(raw_cats, list) and raw_cats:
                    c0 = raw_cats[0]
                    fenrir_cat = c0.get("name") if isinstance(c0, dict) else (c0 if isinstance(c0, str) else None)
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "altex.ro",
                "source_url": _altex_product_url(url_key, sku),
                "image_url": _altex_image_url(item.get("image") or item.get("thumbnail")),
                "in_stock": in_stock,
                "ean": ean if ean else None,
                "sku": sku or None,
                "category": fenrir_cat or main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "altex.ro"}]
    return products


def _parse_sole_price(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sole_product_url(item: dict) -> str:
    rel = item.get("url") or ""
    if rel.startswith("http"):
        return rel
    return f"https://sole.ro/{rel.lstrip('/')}"


def _sole_image_url(item: dict) -> str:
    image = item.get("image") or item.get("photo") or ""
    if not image:
        return ""
    if image.startswith("http"):
        return image
    return f"https://static.sole.ro/{image.lstrip('/')}"


def _sync_scrape_sole(query: str, max_results: int) -> list:
    """POST la sole.ro/cauta/<query> care returnează JSON consumat de frontend-ul lor Vue.

    Notă: sole.ro limitează `perpage` pe server — valori mari (60, 100, 200) returnează
    0 produse. Trimitem maxim-ul cerut de utilizator, dar ne bazăm pe răspunsul
    unei singure pagini; potrivirea reală e limitată de ce returnează sole.
    """
    encoded = urllib.parse.quote(query.strip())
    url = f"https://sole.ro/cauta/{encoded}"
    headers = dict(_SOLE_HEADERS)
    headers["Referer"] = url
    try:
        response = curl_requests.post(
            url,
            headers=headers,
            data={"filterstring": "", "perpage": max_results, "order": 3},
            impersonate=_IMPERSONATE,
            timeout=20,
        )
    except Exception as exc:
        return [{"error": f"Eroare conexiune Sole.ro: {exc}"}]

    if response.status_code != 200:
        return [{"error": f"Sole.ro a returnat status {response.status_code}"}]

    try:
        data = response.json()
    except Exception as exc:
        return [{"error": f"Raspuns invalid de la Sole.ro: {exc}"}]

    raw_products = data.get("products") or []
    products = []
    for item in raw_products[:max_results]:
        try:
            name = item.get("product") or item.get("productoverwrite") or ""
            if not name:
                continue
            in_stock = bool(item.get("instock")) and not item.get("sold_out")
            sole_code = item.get("code") or None

            price = _parse_sole_price(item.get("price"))

            # --- Detectare reducere ---
            # sole.ro expune pentru fiecare produs:
            #   price        -> prețul curent (posibil redus)
            #   oldprice     -> prețul de listă (0 sau == price când nu e promoție)
            #   ispromo      -> 1 când produsul e marcat ca promoție
            #   save_percent -> procent economisit ca întreg (0 când nu e promoție)
            original_price: Optional[float] = None
            is_on_sale = False
            old_price = _parse_sole_price(item.get("oldprice"))
            is_promo_flag = bool(item.get("ispromo")) or str(item.get("ispromo") or "").strip() == "1"
            try:
                save_pct = int(item.get("save_percent") or 0)
            except (TypeError, ValueError):
                save_pct = 0

            if (
                old_price > 0
                and price > 0
                and old_price > price
                and (is_promo_flag or save_pct > 0)
            ):
                is_on_sale = True
                original_price = old_price

            main_cat, sub_cat = infer_category_from_name(name, "sole")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "sole.ro",
                "source_url": _sole_product_url(item),
                "image_url": _sole_image_url(item),
                "in_stock": in_stock,
                "ean": None,
                "sku": sole_code,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "sole.ro"}]
    return products


def _parse_farmaciatei_price(price_text: str) -> float:
    """Parsează prețuri de forma '29,00 LEI' sau '1.299,00 LEI' -> 29.0 / 1299.0.

    RETAIL-AUDIT (5.3e): replace-ul simplu al virgulei producea '1.299.00' ->
    ValueError -> 0.0 TACUT pe ORICE pret >= 1000 RON — punctul e separator de MII
    in formatul RO, deci se elimina inaintea virgulei zecimale."""
    if not price_text:
        return 0.0
    cleaned = re.sub(r"[^0-9,\.]", "", price_text)
    if "," in cleaned:
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _farmaciatei_page_url(encoded_query: str, page: int) -> str:
    """Paginarea Farmacia Tei folosește un path cu virgulă: `/cauti/q/p,2`."""
    base = f"https://comenzi.farmaciatei.ro/cauti/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p,{page}"


def _parse_farmaciatei_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate Farmacia Tei."""
    products = []
    for item in soup.select("div.product-item.product-details"):
        try:
            title_a = item.select_one("a.item-title")
            if not title_a:
                continue
            name = title_a.get_text(strip=True)
            if not name:
                continue
            source_url = title_a.get("href", "") or ""

            img = item.select_one("a.product-image-listing img")
            image_url = img.get("src", "") if img else ""

            btn = item.select_one("button.cd-add-to-cart")
            oos_span = item.select_one("span.product-block-out-of-stock")
            in_stock = oos_span is None and btn is not None

            # --- Extragere preț cu detectare reducere ---
            # Pe pagina farmaciatei.ro:
            #   span.old-price      -> prețul original (prezent doar când e în promoție)
            #   span.regular-price  -> prețul afișat curent (redus dacă e promoție)
            #   button[data-price]  -> istoric prețul de catalog/original,
            #                          deci preferăm regular-price când e disponibil.
            price = 0.0
            original_price: Optional[float] = None
            is_on_sale = False

            regular_el = item.select_one("span.regular-price")
            old_el = item.select_one("span.old-price")

            if regular_el:
                price = _parse_farmaciatei_price(regular_el.get_text())
            if old_el:
                original_price = _parse_farmaciatei_price(old_el.get_text())

            if price <= 0:
                # Fallback-uri când noul markup nu este prezent
                if btn and btn.get("data-price"):
                    try:
                        price = float(btn.get("data-price"))
                    except (TypeError, ValueError):
                        price = 0.0
                if price <= 0:
                    price_span = item.select_one("span.price:not(.text-muted)") or item.select_one("span.price")
                    if price_span:
                        price = _parse_farmaciatei_price(price_span.get_text())

            if (
                original_price is not None
                and price > 0
                and original_price > price
            ):
                is_on_sale = True
            else:
                # Fără reducere reală -> nu expunem un original_price egal cu cel curent
                original_price = None

            pid = btn.get("data-pid") if btn else None
            main_cat, sub_cat = infer_category_from_name(name, "farmaciatei")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "farmaciatei.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": pid,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_farmaciatei(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe farmaciatei.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_FARMACIATEI + 1):
        url = _farmaciatei_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_FARMACIATEI_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune Farmacia Tei: {exc}"}]
            break

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"Farmacia Tei a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare Farmacia Tei: {exc}"}]
            break

        page_products = _parse_farmaciatei_page(soup)
        if not page_products:
            break

        new_this_page = 0
        for p in page_products:
            # Deduplicare după sku; fallback pe source_url când lipsește.
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            # Pagina a returnat doar duplicate -> am ajuns la sfârșitul rezultatelor utile.
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "farmaciatei.ro"}]
    return products


def _parse_emag_price(text: str) -> float:
    """Parsează prețuri în format românesc de tip '1.299,99 Lei' sau '12999' -> float.

    Gestionează separatorul de mii '.' și separatorul zecimal ',' de la eMAG.
    Unele elemente de preț separă partea întreagă de cea zecimală în span-uri diferite;
    funcția operează pe textul combinat după get_text() din BeautifulSoup.
    """
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d,\.]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned:
        # Format românesc: "1.299,99" -> parte întreagă "1299", zecimale "99"
        last_comma = cleaned.rfind(",")
        integer_part = cleaned[:last_comma].replace(".", "")
        decimal_part = cleaned[last_comma + 1:]
        normalized = f"{integer_part}.{decimal_part}" if decimal_part else integer_part
    else:
        # Fără virgulă: punctele sunt probabil separatori de mii ("1.299" -> "1299")
        normalized = cleaned.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def _emag_page_url(encoded_query: str, page: int) -> str:
    """Paginarea eMAG: /search/<q>/p2/, /search/<q>/p3/, etc."""
    base = f"https://www.emag.ro/search/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_emag_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate eMAG."""
    products = []
    # Markup-ul cardurilor eMAG este destul de stabil, dar folosește clase generice;
    # încercăm cei mai specifici selectori mai întâi, cu fallback pe cei mai generali.
    cards = (
        soup.select("div.card-item.js-product-data")
        or soup.select("div.card-item")
        or soup.select("[data-product-id]")
    )

    for item in cards:
        try:
            title_a = (
                item.select_one("a.card-v2-title")
                or item.select_one(".card-v2-title-wrapper a")
                or item.select_one("h2 a")
                or item.select_one("a[href*='/pd/']")
            )
            name = ""
            if title_a:
                name = title_a.get_text(strip=True)
            if not name:
                name = (item.get("data-name") or "").strip()
            if not name:
                continue

            source_url = title_a.get("href", "") if title_a else ""
            if source_url and not source_url.startswith("http"):
                source_url = f"https://www.emag.ro{source_url}"

            img = item.select_one("img.card-v2-thumbnail-image") or item.select_one("img")
            image_url = ""
            if img:
                image_url = img.get("src") or img.get("data-src") or img.get("data-original") or ""

            # --- Extragere preț ---
            # eMAG randează noul preț în `.product-new-price` și prețul vechi
            # (tăiat) în `.product-old-price` când e în promoție.
            price = 0.0
            new_price_el = item.select_one(".product-new-price")
            if new_price_el:
                price = _parse_emag_price(new_price_el.get_text(separator="", strip=True))
            if price <= 0 and item.get("data-price"):
                try:
                    price = float(item.get("data-price"))
                except (TypeError, ValueError):
                    price = 0.0

            original_price: Optional[float] = None
            is_on_sale = False
            old_price_el = item.select_one(".product-old-price")
            if old_price_el:
                old_price = _parse_emag_price(old_price_el.get_text(separator="", strip=True))
                if old_price > 0 and price > 0 and old_price > price:
                    original_price = old_price
                    is_on_sale = True

            # eMAG marchează produsele indisponibile cu un badge de stoc pe card
            in_stock = item.select_one(".badge-no-stock") is None and item.select_one(".product-stock-status-out") is None

            product_id = item.get("data-product-id") or item.get("data-offer-id") or None

            main_cat, sub_cat = infer_category_from_name(name, "emag")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "emag.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": product_id,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_emag(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe eMAG.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_EMAG + 1):
        url = _emag_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_EMAG_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune eMAG: {exc}"}]
            break

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"eMAG a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare eMAG: {exc}"}]
            break

        page_products = _parse_emag_page(soup)
        if not page_products:
            break

        new_this_page = 0
        for p in page_products:
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "emag.ro"}]
    return products


def _pcgarage_page_url(encoded_query: str, page: int) -> str:
    """Paginarea PCGarage: /cauta/<q>/p2/, /cauta/<q>/p3/, etc."""
    base = f"https://www.pcgarage.ro/cauta/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_pcgarage_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate PCGarage."""
    products = []
    for card in soup.select("div.product_box"):
        try:
            name_a = card.select_one(".product_box_name a") or card.select_one("h2 a")
            if not name_a:
                continue
            # Textul titlului cardului conține evidențieri <b> pentru termenul căutat;
            # atributul title conține numele curat al produsului.
            name = (name_a.get("title") or name_a.get_text(" ", strip=True)).strip()
            if not name:
                continue
            source_url = name_a.get("href", "") or ""
            if source_url and not source_url.startswith("http"):
                source_url = f"https://www.pcgarage.ro{source_url}"

            # Imagine: preferăm <picture><source srcset> când e prezent, fallback pe <img>.
            image_url = ""
            src_el = card.select_one(".product_box_image picture source")
            if src_el:
                srcset = src_el.get("srcset") or ""
                image_url = srcset.split(",")[0].strip().split(" ")[0]
            if not image_url:
                img = card.select_one(".product_box_image img")
                if img:
                    image_url = img.get("src") or img.get("data-src") or ""

            # Preț: ".pb-price p.price" -> "7.799,98 RON" (format românesc).
            price = 0.0
            price_el = card.select_one(".pb-price p.price") or card.select_one(".pb-price")
            if price_el:
                price = _parse_emag_price(price_el.get_text(strip=True))

            # Prețul vechi (când e promoție) — verificăm mai mulți selectori ca măsură
            # de precauție, deoarece PCGarage uneori livrează markup promo cu preț tăiat.
            original_price: Optional[float] = None
            is_on_sale = False
            old_el = (
                card.select_one(".pb-old-price")
                or card.select_one(".old_price")
                or card.select_one(".pb-price del")
                or card.select_one(".pb-price s")
            )
            if old_el:
                old_price = _parse_emag_price(old_el.get_text(strip=True))
                if old_price > 0 and price > 0 and old_price > price:
                    original_price = old_price
                    is_on_sale = True

            # Disponibilitate: "instock" / "insupplierstock" -> disponibil; "outofstock" -> indisponibil.
            in_stock = True
            avail_el = card.select_one(".product_box_availability")
            if avail_el and "outofstock" in " ".join(avail_el.get("class", [])):
                in_stock = False

            sku: Optional[str] = None
            rates = card.select_one("a.rates_installments[href*='pid=']")
            if rates:
                m = re.search(r"pid=(\d+)", rates.get("href", ""))
                if m:
                    sku = m.group(1)

            main_cat, sub_cat = infer_category_from_name(name, "pcgarage")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "pcgarage.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": sku,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_pcgarage(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe PCGarage.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_PCGARAGE + 1):
        url = _pcgarage_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_PCGARAGE_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune PCGarage: {exc}"}]
            break

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"PCGarage a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare PCGarage: {exc}"}]
            break

        page_products = _parse_pcgarage_page(soup)
        if not page_products:
            break

        new_this_page = 0
        for p in page_products:
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "pcgarage.ro"}]
    return products


def _is_allowed_shop_url(url: str) -> bool:
    """C-14 (anti-SSRF): `source_url` vine liber din formularul userului si e cerut
    server-side (backfill EAN, refresh pret). Fara allow-list, un URL intern
    (169.254.169.254, localhost) ar transforma backend-ul in proxy de scanare
    interna. Permitem DOAR domeniile magazinelor pe care le stim citi.

    Allow-list-ul e UNIUNEA a doua multimi: scraperele de cautare
    (_SCRAPERS_BY_SOURCE) si domeniile validate pentru monitorizare prin link
    (VALIDATED_DOMAINS, RETAIL-3a) — al doilea grup poate contine magazine pentru
    care avem doar extractie de pagina de produs, fara scraper de cautare.
    Citirea e la apel, nu la import, fiindca dict-ul e definit mai jos in fisier
    decat functia asta — o constanta la nivel de modul ar da NameError.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        # Doar http/https: taie file://, gopher://, ftp:// etc.
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        for domain in set(_SCRAPERS_BY_SOURCE) | VALIDATED_DOMAINS:
            # Egalitatea acopera domeniul gol de subdomeniu; endswith pe "."+domain
            # accepta subdomenii legitime (comenzi.farmaciatei.ro) dar respinge
            # sufixele inselatoare (evil-altex.ro.attacker.com).
            if hostname == domain or hostname.endswith("." + domain):
                return True
        return False
    except Exception:
        return False  # fail-closed: orice URL neparsabil e respins


def _impersonate_for(url: str) -> str:
    """Amprenta curl_cffi pentru `url`: override-ul domeniului, altfel _IMPERSONATE.

    Matching-ul e IDENTIC cu cel din _is_allowed_shop_url (egalitate sau sufix
    "."+domeniu), ca un subdomeniu legitim (shop.43einhalb.com) sa primeasca
    aceeasi amprenta ca domeniul de baza, dar un sufix inselator
    (evil-43einhalb.com.attacker.com) sa NU o primeasca — altfel un atacator si-ar
    alege singur amprenta cu care backend-ul iese pe retea.

    Fail-safe pe DEFAULT, nu fail-closed ca allow-list-ul: aici nu se decide DACA
    se cere URL-ul (poarta a decis deja), ci doar cum arata clientul, deci un URL
    neparsabil primeste _IMPERSONATE, nu o eroare.
    """
    try:
        hostname = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return _IMPERSONATE
    if not hostname:
        return _IMPERSONATE
    for domain, tier in _IMPERSONATE_OVERRIDES.items():
        if hostname == domain or hostname.endswith("." + domain):
            return tier
    return _IMPERSONATE


def _asteapta_intervalul(url: str) -> float:
    """Doarme diferenta pana la intervalul minim al domeniului. Intoarce secundele.

    Zero cost pe domeniile fara camp: harta e goala sau nu contine domeniul, si se
    iese inainte de lacat. Matching-ul e suffix-safe, IDENTIC cu `_impersonate_for`
    si cu allow-list-ul C-14 — un subdomeniu legitim mosteneste intervalul
    domeniului de baza, dar `evil-action.com.attacker.com` nu.

    Asteptarea sta SUB lacat, nu inaintea lui, si nu din neglijenta: daca doua fire
    ar verifica in paralel, amandoua ar vedea „a trecut destul" si ar pleca
    spate-in-spate catre exact magazinul pe care incercam sa-l menajam. Sub lacat,
    firele se serializeaza si fiecare isi asteapta randul. Costul e ca un al doilea
    fir catre ACELASI domeniu sta blocat — dar asta E protectia, nu un efect
    secundar. Restul jobului nu sufera: alte domenii nu ating lacatul asta decat
    daca au si ele interval, iar pe registrul de azi doar unul are.

    Momentul se stampileaza la PLECAREA cererii, nu la intoarcerea ei: masuratoarea
    care a dat regula numara cereri pe minut, iar durata raspunsului nu e sub
    controlul nostru. Ar fi si nepractic — ar cere tinerea lacatului peste apelul
    de retea, adica serializarea completa a fetch-urilor.

    Se aplica o data pe FETCH LOGIC, nu pe fiecare hop de redirect: un lant de
    redirecturi e o singura vizita, iar o pauza de 90s intre hop-uri ar rupe
    fetch-ul in loc sa-l menajeze.
    """
    if not _MIN_FETCH_INTERVALE:
        return 0.0
    try:
        hostname = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:                                           # noqa: BLE001
        return 0.0
    if not hostname:
        return 0.0
    cheie = None
    for domain in _MIN_FETCH_INTERVALE:
        if hostname == domain or hostname.endswith("." + domain):
            cheie = domain
            break
    if cheie is None:
        return 0.0

    interval = _MIN_FETCH_INTERVALE[cheie]
    with _LOCK_INTERVAL:
        trecut = time.monotonic() - _ULTIMA_CERERE_PE_DOMENIU.get(cheie, float("-inf"))
        de_asteptat = interval - trecut
        if de_asteptat > 0:
            # AMZ-1 (0.3): modulul e "catalog", nu "retail" — "retail" NU e in
            # LogManager.MODULES, iar emit() remapeaza tacut orice modul necunoscut
            # pe "radar". Liniile de retail ajungeau deci in jurnalul Radar.
            log_manager.emit(
                "catalog", "INFO",
                f"Interval minim {cheie}: astept {de_asteptat:.0f}s "
                f"(minim {interval}s intre cereri)")
            time.sleep(de_asteptat)
        else:
            de_asteptat = 0.0
        _ULTIMA_CERERE_PE_DOMENIU[cheie] = time.monotonic()
    return de_asteptat


# Doar astea doua opresc fluxul. NOT_FOUND / TRANSIENT / OK / SITE_CHANGED se intorc
# la apelant exact ca pana acum: 404-ul, de pilda, e sfarsit de paginare pentru
# listing_scanner si trebuie sa ajunga la el ca raspuns, nu ca None.
_REZULTATE_ZID = (Outcome.BLOCKED, Outcome.RATE_LIMITED)


def _clasifica_raspuns(url: str, response) -> Outcome:
    """Diagnosticul raspunsului, INAINTE de orice parsare.

    AMZ-1a. Clasificarea se face INAINTE ca body-ul sa ajunga la orice parser: un
    interstitiu anti-bot servit cu 200 nu are voie sa intre in extractor ca HTML
    valid. `parsed=None` INTOTDEAUNA — n-am parsat inca, deci n-avem dreptul sa
    declansam `SITE_CHANGED`, care inseamna „markup schimbat".

    Intoarce Outcome-ul, nu un boolean, DELIBERAT: politica („ce opreste fluxul") sta
    in poarta, iar aici ramane doar diagnosticul. Diferenta e testabila — un control
    negativ care schimba `parsed=None` in `parsed=0` face ca un 200 curat sa iasa
    `SITE_CHANGED` in loc de `OK`, iar cu un boolean asta ar fi fost INVIZIBIL (niciuna
    din cele doua valori nu blocheaza). Sabotajul S2 chiar n-a fost prins pana la
    schimbarea asta.
    """
    status = getattr(response, "status_code", None)
    try:
        body = response.text
    except Exception:                                           # noqa: BLE001
        body = None
    domeniu = _domeniu_din_url(url)
    prag = prag_interstitiu(domeniu)

    # AWS WAF serveste provocarea cu 202, status pe care `classify()` nu-l verifica
    # pe markeri (doar 200). Verificarea proprie sta INAINTEA lui classify tocmai ca
    # sa nu cerem modificarea unui contract testat. Vezi `_MARKERI_WAF`.
    if (status == 202 and body and len(body) < prag
            and any(m in body.lower() for m in _MARKERI_WAF)):
        rezultat = Outcome.BLOCKED
    else:
        rezultat = classify(
            status=status, body=body, exc=None, parsed=None,
            extra_markers=markeri_blocaj(domeniu),
            interstitial_max_bytes=prag,
        )

    if rezultat in _REZULTATE_ZID:
        try:
            # FARA body in log: un interstitiu poate purta token-uri de sesiune, iar
            # jurnalul e vizibil in UI.
            log_manager.emit(
                "catalog", "WARN",
                f"retail fetch blocat: {domeniu} outcome={rezultat.value} "
                f"status={status} bytes={len(body or '')}")
        except Exception:                                       # noqa: BLE001
            pass  # logging-ul nu trebuie sa rupa fluxul
    return rezultat


def _fetch_shop_url_guarded(url: str, *, headers: dict, timeout: int, max_hops: int = 3):
    """C-14b/C-14c: fetch cu allow-list per-hop, partajat de toate fetch-urile pe
    URL-uri controlate de user.

    Allow-list-ul pe URL-ul initial nu e suficient: un open-redirect pe un magazin
    permis ar duce curl catre o tinta interna. De aceea allow_redirects=False si
    urmarim manual, validand FIECARE hop prin _is_allowed_shop_url inainte de a-l cere.

    Intoarce response-ul final (non-redirect) sau None daca: URL neautorizat pe orice
    hop, prea multe redirecturi, eroare de retea, SAU raspunsul e un zid anti-bot
    (AMZ-1a: `Outcome.BLOCKED` / `RATE_LIMITED` — vezi `_clasifica_raspuns`). NU verifica
    `url` gol si NU parseaza continutul — alea raman la apelanti.

    De ce blocajul intoarce None, adica EXACT forma de la eroarea de retea: valoarea
    de retur n-are camp de motiv, iar apelantii nu se rescriu in runda asta. Varianta
    cu cea mai mica atingere e deci sa refolosim forma existenta si sa lasam motivul
    distinct doar in linia de WARN. Consecinta masurata pe cele doua cai:
      * pagina de produs: un interstitiu de 200 iesea `no_product_data` -> 422
        („n-am putut extrage datele", care acuza parserul nostru); acum iese
        `fetch_failed` -> 502 („magazinul a blocat cererea"), care e adevarul;
      * un 403 iesea `challenge`, acum iese `fetch_failed` — dar AMBELE se mapeaza
        la acelasi 502 cu acelasi text (routers/products.py), deci degradarea nu e
        vizibila utilizatorului.
    Blocul `403 / cf-mitigated / just a moment` din product_page_extractor NU devine
    cod mort, desi asa pare la prima vedere. Doua ramuri ale lui sunt intr-adevar
    acoperite acum de poarta (403 -> BLOCKED; `<title>just a moment` -> BLOCK_MARKERS),
    dar a treia e STRICT MAI LARGA decat markerul generic: acolo testul e
    `"just a moment" in response.text[:2000].lower()`, fara ancora pe <title>, deci
    prinde si proza dintr-o descriere de produs. Masurat de testul
    `test_02b_just_a_moment_in_proza_NU_e_blocaj`: poarta lasa pagina sa treaca (corect,
    ancora pe titlu e deliberata — vezi base_scraper), iar extractorul o respinge totusi
    cu `challenge`. Diferenta e reala si e in AFARA fisierelor permise in AMZ-1a; se
    consemneaza aici ca sa nu fie descoperita din nou ca surpriza.

    Amprenta de impersonate se rezolva PER HOP, ca un redirect intre domenii sa
    plece cu amprenta TINTEI, nu a sursei — altfel un redirect catre 43einhalb.com
    ar cere pagina cu profilul implicit si ar lua 403, exact ce evita override-ul.
    """
    # RATE-1: menajarea domeniului se face INAINTE de primul hop, o data pe fetch.
    _asteapta_intervalul(url)

    nume_jar = jar_pentru(url)
    if nume_jar is None:
        # Calea celorlalte 88 de magazine: identica cu cea de dinainte de AMZ-1.
        raspuns, _ = _parcurge_hopuri(url, headers, timeout, max_hops, None, None)
        return raspuns

    jar = _incarca_jar(nume_jar)
    url_bootstrap = bootstrap_pentru(url)

    # (2) Jar lipsa/gol + bootstrap disponibil -> il facem INAINTE de cererea utila.
    if not jar and url_bootstrap and not _in_bootstrap():
        if _face_bootstrap(nume_jar, url, url_bootstrap, headers, timeout, "lipsa"):
            # Bootstrap-ul a consumat el insusi o cerere catre domeniu, iar cererea
            # utila vine imediat dupa. Fara asteptarea asta, cele doua ar pleca
            # spate-in-spate si ar incalca exact `min_fetch_interval_s` al domeniului
            # — pe amazon.de, 10s. `_asteapta_intervalul` de la intrarea in poarta
            # s-a consumat INAINTEA bootstrap-ului, deci nu acopera cazul.
            _asteapta_intervalul(url)
            jar = _incarca_jar(nume_jar)

    raspuns, rezultat = _parcurge_hopuri(url, headers, timeout, max_hops,
                                         jar, nume_jar)

    # (3) BLOCAT -> golim jar-ul, bootstrap O SINGURA data, cererea utila O SINGURA
    # data. Fara bucla: daca si a doua oara e zid, raspundem None ca pana acum.
    #
    # DOAR pe `BLOCKED`, nu pe orice zid: `RATE_LIMITED` (429) inseamna „prea multe
    # cereri", iar raspunsul la asta e mai PUTIN trafic, nu inca doua cereri si un
    # jar aruncat. Sesiunea nu e vinovata acolo, deci nici nu se reface.
    if (rezultat is Outcome.BLOCKED and url_bootstrap and not _in_bootstrap()):
        _goleste_jar(nume_jar)
        if _face_bootstrap(nume_jar, url, url_bootstrap, headers, timeout, "blocat"):
            _asteapta_intervalul(url)     # a doua cerere utila isi asteapta randul
            jar = _incarca_jar(nume_jar)
            raspuns, _ = _parcurge_hopuri(url, headers, timeout, max_hops,
                                          jar, nume_jar)
    return raspuns


def _parcurge_hopuri(url: str, headers: dict, timeout: int, max_hops: int,
                     jar, nume_jar):
    """Bucla de hop-uri. Intoarce (raspuns_sau_None, Outcome_sau_None).

    Corpul e cel dinainte de AMZ-1, mutat aici neschimbat in afara cookie-urilor.

    Al doilea element e OUTCOME-ul, nu un boolean: poarta trebuie sa deosebeasca
    `BLOCKED` (sesiune respinsa -> bootstrap-ul are sens) de `RATE_LIMITED` (prea
    multe cereri -> raspunsul corect e mai putin trafic, nu inca doua cereri). `None`
    inseamna „nu s-a ajuns la clasificare": URL neautorizat, eroare de retea, redirect
    fara Location, hop-uri epuizate. Valoarea de retur PUBLICA a portii ramane un
    simplu response-sau-None.
    """
    current_url = url
    for _hop in range(max_hops + 1):  # 1 request initial + max_hops redirecturi
        if not _is_allowed_shop_url(current_url):
            return None, None

        # Cookie-urile se trimit DOAR pe hop-urile care apartin ACELUIASI jar.
        # Un redirect intre domenii e legitim si allow-list-ul il permite, dar
        # sesiunea unui magazin n-are ce cauta la altul: ar fi o scurgere de date
        # de sesiune catre un tert. Simetric cu `_impersonate_for`, care se rezolva
        # tot per hop, si din acelasi motiv.
        jar_hop = jar_pentru(current_url) if nume_jar is not None else None
        acelasi_jar = jar_hop is not None and jar_hop == nume_jar
        kw = {"cookies": jar} if (acelasi_jar and jar) else {}
        try:
            response = curl_requests.get(
                current_url,
                headers=headers,
                impersonate=_impersonate_for(current_url),
                timeout=timeout,
                allow_redirects=False,
                **kw,
            )
        except Exception:
            # AMZ-1a, ramura de exceptie: in taxonomia din base_scraper o exceptie e
            # prin definitie TRANSIENT (`classify` intoarce TRANSIENT pe `exc` INAINTE
            # de a privi orice altceva), iar TRANSIENT nu e zid. Deci comportamentul
            # ramane identic — None, fara WARN — si un apel `classify` aici ar fi un
            # no-op al carui rezultat s-ar arunca. Pinuit de test_08.
            return None, None

        # Cookie-urile primite intra in jar INDIFERENT de clasificare (si un raspuns
        # de bootstrap, si unul util pot emite — pe amazon.de pagina de produs adauga
        # `session-token` si `sp-cdn` peste cele 6 de la glow), dar DOAR de pe
        # hop-urile aceluiasi jar: altfel un redirect catre alt magazin si-ar
        # strecura propriile cookie-uri in sesiunea noastra.
        if acelasi_jar:
            primite = _cookies_din_raspuns(response)
            if primite:
                jar = {**(jar or {}), **primite}
                _salveaza_jar(nume_jar, jar)

        if response.status_code in (301, 302, 303, 307, 308):
            loc = response.headers.get("location") or response.headers.get("Location")
            if not loc:
                return None, None
            # Location poate fi cale relativa -> rezolvam fata de URL-ul curent.
            current_url = urllib.parse.urljoin(current_url, loc)
            continue
        rezultat = _clasifica_raspuns(current_url, response)
        if rezultat in _REZULTATE_ZID:
            return None, rezultat
        return response, rezultat
    return None, None  # hop-uri epuizate fara raspuns final


def _face_bootstrap(nume_jar: str, url_util: str, url_bootstrap: str,
                    headers: dict, timeout: int, motiv: str) -> bool:
    """Cere `url_bootstrap` ca sa emita cookie-urile. True daca a plecat cererea.

    (4) Racire la nivel de proces: cel mult un bootstrap per jar la 10 minute. Peste
    prag intoarce False, iar apelantul raspunde cu ce avea — adica `None` pe calea
    de blocaj. Ceas MONOTON, ca la RATE-1: o ajustare de ceas de sistem n-are voie
    sa deschida sau sa inchida fereastra.
    """
    with _LOCK_JAR:
        acum = time.monotonic()
        trecut = acum - _ULTIMUL_BOOTSTRAP.get(nume_jar, float("-inf"))
        if trecut < _RACIRE_BOOTSTRAP_S:
            return False
        _ULTIMUL_BOOTSTRAP[nume_jar] = acum

    try:
        # (5) FARA cookie-uri in mesaj: jurnalul e vizibil in UI.
        log_manager.emit(
            "catalog", "WARN",
            f"retail bootstrap sesiune: {_domeniu_din_url(url_util)} motiv={motiv}")
    except Exception:                                           # noqa: BLE001
        pass

    _local_bootstrap.activ = True
    try:
        # Apel RECURSIV, deliberat: bootstrap-ul trebuie sa treaca prin exact aceleasi
        # porti ca orice alta cerere (allow-list C-14, interval RATE-1, clasificare
        # AMZ-1a). Steagul de fir opreste recursia la un nivel.
        _fetch_shop_url_guarded(url_bootstrap, headers=headers, timeout=timeout)
    except Exception:                                           # noqa: BLE001
        pass      # un bootstrap picat nu e fatal: cererea utila decide singura
    finally:
        _local_bootstrap.activ = False
    return True


def fetch_ean_from_url(source_url: str) -> Optional[str]:
    """Încearcă să preia EAN-ul/GTIN-ul din pagina de detalii a unui produs.

    Suportă: farmaciatei.ro (JSON-LD gtin13 / sku),
    sole.ro (text simplu "Cod EAN:"), altex.ro (JSON-LD gtin13).
    Returnează None dacă nu se găsește sau în caz de eroare.
    URL-urile din afara domeniilor magazin sunt respinse INAINTE de orice request
    (vezi _is_allowed_shop_url).
    """
    if not source_url:
        return None
    if not _is_allowed_shop_url(source_url):
        try:
            log_manager.emit("catalog", "WARN",
                             f"EAN skip URL neautorizat: {source_url[:80]}")
        except Exception:
            pass  # logging-ul nu trebuie sa rupa fluxul
        return None
    try:
        response = _fetch_shop_url_guarded(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ro-RO,ro;q=0.9",
            },
            timeout=15,
        )
        if response is None or response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "html.parser")

        # Încearcă date structurate JSON-LD
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                ld = json.loads(script.string or "")
                items = ld if isinstance(ld, list) else [ld]
                for obj in items:
                    if isinstance(obj, dict):
                        gtin = obj.get("gtin13") or obj.get("gtin") or obj.get("gtin12") or ""
                        if gtin and len(gtin) >= 8:
                            return gtin.strip()
                        sku = obj.get("sku") or ""
                        if sku and sku.isdigit() and len(sku) >= 8:
                            return sku.strip()
            except Exception:
                continue

        # Fallback: caută EAN în text simplu (acoperă sole.ro și farmaciatei.ro)
        text = soup.get_text()
        for pattern in (
            r"[Cc]od\s*EAN[:\s]+(\d{8,14})",      # sole.ro: "Cod EAN: 880973..."
            r"EAN[:\s]+(\d{8,14})",                 # generic "EAN: ..."
            r"[Cc]od\s+produs[:\s]+(\d{8,14})",     # farmaciatei.ro: "Cod produs: 500015..."
            r"GTIN[:\s]+(\d{8,14})",                 # generic GTIN
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)

    except Exception:
        pass
    return None


def _emit_catalog(shop_name: str, query: str, products: list) -> None:
    """Loghează în modulul `catalog` rezultatul unei scanări de magazin."""
    n = sum(1 for p in (products or []) if not (isinstance(p, dict) and p.get("message")))
    log_manager.emit("catalog", "SCAN", f"Scanare {shop_name} · {n} produse verificate pentru '{query}'")
    if n:
        log_manager.emit("catalog", "OK", f"{shop_name}: {n} produse găsite")


async def scrape_altex(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_altex, query, max_results)
    _emit_catalog("Altex", query, res)
    return res


async def scrape_sole(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_sole, query, max_results)
    _emit_catalog("Sole", query, res)
    return res


async def scrape_farmaciatei(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_farmaciatei, query, max_results)
    _emit_catalog("FarmaciaTei", query, res)
    return res


async def scrape_emag(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_emag, query, max_results)
    _emit_catalog("eMAG", query, res)
    return res


async def scrape_pcgarage(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_pcgarage, query, max_results)
    _emit_catalog("PCGarage", query, res)
    return res


_SCRAPERS_BY_SOURCE = {
    "altex.ro": _sync_scrape_altex,
    "sole.ro": _sync_scrape_sole,
    "farmaciatei.ro": _sync_scrape_farmaciatei,
    "emag.ro": _sync_scrape_emag,
    "pcgarage.ro": _sync_scrape_pcgarage,
}


def fetch_pcgarage_price_from_url(source_url: str, max_retries: int = 3) -> Optional[float]:
    """Re-fetch pretul PCGarage DIRECT de pe pagina de produs (source_url stocat),
    ocolind complet cautarea /cauta/ (challenge-uita agresiv de Cloudflare).

    Pagina de produs trece de Cloudflare Managed Challenge in ~90% din cazuri per
    incercare cu _IMPERSONATE-ul curent, deci reincercam pana la `max_retries` ori
    cand nimerim interstitiul. Selectorii de pret sunt cei ai paginii de DETALIU
    (.price_num / .ps_sell_price), diferiti de selectorii de lista din
    _sync_scrape_pcgarage.

    C-14c: `source_url` vine din produsul creat de user (via refresh_price_from_source,
    chemat si din scheduler), deci trece prin _fetch_shop_url_guarded — allow-list pe
    URL-ul initial si pe fiecare redirect.
    """
    if not source_url:
        return None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            time.sleep(random.uniform(1, 3))
        response = _fetch_shop_url_guarded(source_url, headers=_PCGARAGE_HEADERS, timeout=25)
        if response is None:
            # None = URL neautorizat (SSRF blocat) SAU eroare de retea / redirect invalid.
            if not _is_allowed_shop_url(source_url):
                # Fail-fast: pe un URL interzis nu are rost sa consumam retry-uri —
                # nu devine permis daca mai asteptam.
                return None
            continue  # eroare tranzitorie -> mai incercam (comportamentul vechi)

        # Cloudflare Managed Challenge: 403 si/sau header cf-mitigated=challenge si/sau
        # <title>Just a moment... -> nu e pagina reala, mai incercam.
        is_challenge = (
            response.status_code == 403
            or response.headers.get("cf-mitigated") == "challenge"
            or "just a moment" in response.text[:2000].lower()
        )
        if is_challenge or response.status_code != 200:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        # Selectorii de pret ai paginii de PRODUS, in ordine. NU adauga
        # meta[itemprop='price'] ca fallback: pe PCGarage atributul `content` e in
        # format international cu zgomot float (ex "7619.979961"), pe care
        # _parse_emag_price il interpreteaza gresit (punctul ca separator de mii) ->
        # valoare aberanta. Doar selectorii vizuali au format romanesc "7.619,98 RON".
        price_el = soup.select_one(".price_num") or soup.select_one(".ps_sell_price")
        price = _parse_emag_price(price_el.get_text(" ", strip=True)) if price_el is not None else 0.0
        if price and price > 0:
            return price
        # 200 real, dar niciun selector de pret potrivit / pret 0/invalid -> distinct
        # de blocajul Cloudflare (posibila schimbare de structura a site-ului).
        print(f"[AlertChecker] PCGarage: pagina incarcata (200) dar niciun selector de pret nu s-a potrivit — posibila schimbare de structura, verifica manual: {source_url}")
        return None

    # Toate incercarile au nimerit challenge-ul Cloudflare (sau eroare de retea).
    print(f"[AlertChecker] PCGarage: blocat de Cloudflare dupa {max_retries} incercari pentru {source_url}")
    return None


def refresh_source(
    source: Optional[str],
    source_url: Optional[str],
    product_name: Optional[str],
    sku: Optional[str] = None,
    variant: str = "",
) -> Optional[dict]:
    """Re-citeste pretul (si, unde se poate, stocul) pentru o sursa de produs.

    Intoarce {"price": float, "in_stock": bool|None, "method": str} sau None cand
    nu s-a putut afla nimic. Un dict intors are MEREU un pret valid (> 0).
    `method` spune pe ce cale a venit rezultatul:
      "url"      — fetch direct al paginii de produs prin extractorul generic;
                   singura cale care aduce si stocul (doar VALIDATED_DOMAINS)
      "pcgarage" — fetch direct pe pagina de produs cu parserul dedicat (Cloudflare)
      "search"   — calea istorica: re-cautare in magazin + potrivire pe URL/nume

    `variant` (FASHION-1c) restrange citirea la o MARIME anume: se accepta doar
    intrarea ei din `variants`, iar daca lipseste se intoarce None. Cu variant=""
    (tot restul catalogului) comportamentul e neschimbat.
    """
    if not source or not source_url:
        return None
    domain = source.lower()
    # RETAIL-AUDIT (5.3e): sursa poate fi salvata cu subdomeniu (m.emag.ro,
    # comenzi.farmaciatei.ro) — lookup-urile pe egalitate exacta o lasau permanent
    # stale (nevalidata + fara scraper), tacut. Granita pe punct, ca in allow-list.
    vdomain = match_shop_domain(domain, VALIDATED_DOMAINS)
    sdomain = match_shop_domain(domain, _SCRAPERS_BY_SOURCE)

    # (a) Domenii validate: pagina de produs e sursa de adevar. Un pret citit direct
    # de acolo bate potrivirea fuzzy din lista de cautare (care poate nimeri alt
    # produs) si e singurul mod in care aflam si disponibilitatea.
    if vdomain is not None:
        try:
            extracted = extract_product(source_url)
            if variant:
                # Potrivire EXACTA pe eticheta marimii; nimic altceva nu e acceptabil.
                entry = next((v for v in (extracted.get("variants") or [])
                              if v.get("variant") == variant), None)
                price = float((entry or {}).get("price") or 0)
                if entry is not None and price > 0:
                    return {"price": price, "in_stock": entry.get("in_stock"), "method": "url"}
            else:
                price = float(extracted.get("price") or 0)
                if price > 0:
                    return {"price": price, "in_stock": extracted.get("in_stock"), "method": "url"}
        except ProductExtractionError as exc:
            # Nu e final: magazinul poate raspunde la cautare chiar daca pagina de
            # produs a fost blocata sau si-a schimbat structura -> cadem mai jos.
            print(f"[Refresh] Extractie esuata ({exc.reason}) pe {domain}: {source_url[:80]}")

    # FASHION-1c — un rand pe MARIME se opreste aici. Caile de mai jos (re-cautare,
    # parser PCGarage) nu stiu de marimi: ar intoarce pretul PRODUSULUI si l-ar
    # scrie peste pretul marimii, falsificand istoricul si alertele. Mai bine un
    # pret vechi (stale) decat pretul altei marimi sau agregatul "de la".
    if variant:
        print(f"[Refresh] Marimea {variant!r} nu a putut fi citita pe {domain}: "
              f"pastram pretul anterior ({source_url[:80]})")
        return None

    # (b) PCGarage: refresh direct de pe pagina de produs (source_url stocat), ocolind
    # complet cautarea /cauta/ care e challenge-uita agresiv de Cloudflare. Restul
    # aplicatiei (cautare, cross-shop) continua sa foloseasca _sync_scrape_pcgarage.
    #
    # LOT1: de cand pcgarage.ro e in VALIDATED_DOMAINS (sonda 2026-08-13 + scoparea
    # nested din _collect_microdata, care i-a deblocat numele), calea (a) de mai sus
    # intercepteaza PRIMA si citeste pretul din microdata paginii — masurat identic
    # cu ce da parserul dedicat. Ramura asta ramane deci FALLBACK istoric: se atinge
    # doar cand extractia esueaza, sau daca domeniul ar iesi vreodata din
    # VALIDATED_DOMAINS. Se pastreaza tocmai fiindca e plasa care a facut refresh-ul
    # pcgarage sa mearga prin Cloudflare ani la rand.
    if sdomain == "pcgarage.ro" or domain == "pcgarage.ro":
        price = fetch_pcgarage_price_from_url(source_url)
        return {"price": price, "in_stock": None, "method": "pcgarage"} if price else None

    # (c) Calea istorica: lansam o cautare cu SKU (mai precisa) sau cu numele si
    # gasim rezultatul cu acelasi source_url.
    scraper = _SCRAPERS_BY_SOURCE.get(sdomain) if sdomain else None
    if not scraper:
        return None
    # IMPORTANT: `sku` e cautabil DOAR pentru altex.ro, unde e un cod real de produs
    # extras din URL (/cpd/<sku>/). Pentru celelalte surse (emag.ro, pcgarage.ro,
    # sole.ro, farmaciatei.ro) `Product.sku` e ID-ul intern al magazinului (ex: eMAG
    # data-product-id) — NECAUTABIL: search-ul cade pe potrivire fuzzy pe cifre si
    # intoarce produse nelegate. De aceea acolo cautam MEREU dupa nume. (Nu reintroduce
    # `sku or product_name` pentru non-altex — sparge refresh-ul pe eMAG/PCGarage.)
    if sdomain == "altex.ro":
        if not sku:
            sku = _altex_sku_from_url(source_url)
        query = (sku or product_name or "").strip()
    else:
        query = (product_name or "").strip()
    if not query:
        return None
    try:
        # 20 rezultate sunt suficiente: produsul cautat ar trebui in primele
        # cateva, mai ales cand cautam dupa SKU sau dupa nume specific.
        results = scraper(query[:80], 20)
    except Exception:
        return None
    if not results:
        return None
    # Strategia 1: potrivire exactă pe source_url (cea mai precisă când URL-urile
    # rămân stabile pe site).
    norm_url = source_url.rstrip("/")
    for r in results:
        if not isinstance(r, dict):
            continue
        r_url = (r.get("source_url") or "").rstrip("/")
        if r_url and r_url == norm_url:
            price = r.get("price")
            try:
                price = float(price)
                # Ca inainte: URL-ul potrivit dar pretul invalid inseamna None, NU
                # trecerea la strategia 2 (am gasit exact produsul, n-are rost sa
                # cautam altul dupa nume).
                return {"price": price, "in_stock": None, "method": "search"} if price > 0 else None
            except (TypeError, ValueError):
                continue
    # Strategia 2 (fallback): potrivire după primele 40 de caractere din nume,
    # case-insensitive. Acoperă cazurile în care site-ul și-a schimbat
    # structura URL-urilor sau când source-ul și source_url-ul stocate au
    # mici inconsistențe (ex: salvare manuală cu URL trunchiat).
    if product_name:
        prefix = product_name.strip()[:40].lower()
        if prefix:
            for r in results:
                if not isinstance(r, dict):
                    continue
                r_name = (r.get("name") or "").strip().lower()
                if r_name and r_name.startswith(prefix):
                    price = r.get("price")
                    try:
                        price = float(price)
                        if price > 0:
                            return {"price": price, "in_stock": None, "method": "search"}
                    except (TypeError, ValueError):
                        continue
    return None


def refresh_price_from_source(
    source: Optional[str],
    source_url: Optional[str],
    product_name: Optional[str],
    sku: Optional[str] = None,
) -> Optional[float]:
    """Wrapper back-compat peste refresh_source: DOAR pretul, exact ca inainte.

    Pastrat pentru apelantii care nu au nevoie de stoc sau de calea folosita
    (semnatura si semantica identice cu versiunea dinaintea RETAIL-3a).
    """
    result = refresh_source(source, source_url, product_name, sku)
    return result["price"] if result else None


def find_cross_shop_matches(
    name: str,
    ean: Optional[str],
    exclude_source: Optional[str],
    max_results: int = 20,
) -> dict:
    """Caută același produs pe celelalte magazine (toate din _SCRAPERS_BY_SOURCE
    minus sursa de origine). Returnează:
        {"ean_matches": [...], "name_candidates": [...]}

    Strategie (adaptată la realitatea scraperelor): căutăm pe NUME pe fiecare
    magazin — singura interogare fiabilă, fiindcă doar Altex expune `ean` în
    rezultatele de căutare. Apoi:
      - dacă un rezultat are EAN-ul identic cu al produsului  -> ean_matches
        (potrivire sigură -> se atașează automat ca sursă);
      - altfel, dacă există EXACT un candidat relevant pe nume -> name_candidates
        (sugestie ce așteaptă confirmarea userului). 0 sau 2+ = prea ambiguu, sărim.

    Secvențial, cu delay aleator între magazine (același pattern anti-blocare ca
    refresh_price_from_source). Nu paralelizează.
    """
    ean_matches: list = []
    name_candidates: list = []
    query = (name or "").strip()
    if not query:
        return {"ean_matches": ean_matches, "name_candidates": name_candidates}

    ean_norm = (ean or "").strip().lstrip("0")
    exclude = (exclude_source or "").strip().lower()

    for source, scraper in _SCRAPERS_BY_SOURCE.items():
        if source == exclude:
            continue
        time.sleep(random.uniform(0.6, 1.4))  # anti-blocare, ca la refresh_price_from_source
        try:
            raw = scraper(query[:80], max_results)
        except Exception as exc:
            log_manager.emit("catalog", "WARN",
                             f"Cross-shop {source}: eroare scraper ({str(exc)[:60]})")
            continue
        _emit_catalog(source, query, raw)

        real = [r for r in raw
                if isinstance(r, dict) and "error" not in r and "message" not in r]
        if not real:
            continue

        # 1) Potrivire confirmată prin EAN (doar magazinele care expun `ean` în
        #    rezultate, ex. Altex). Re-verificăm egalitatea strict, ca să nu
        #    atașăm din greșeală rezultate cu EAN gol.
        if ean_norm:
            confirmed = [r for r in real
                         if (r.get("ean") or "").strip().lstrip("0") == ean_norm]
            if confirmed:
                ean_matches.append({**confirmed[0], "source": source})
                continue

        # 2) Candidat unic pe nume -> sugestie. filter_by_relevance păstrează doar
        #    produsele al căror nume conține toți tokenii semnificativi din query.
        relevant = filter_by_relevance(real, query)
        clear = [r for r in relevant
                 if isinstance(r, dict) and "error" not in r and "message" not in r]
        if len(clear) == 1:  # un singur candidat clar; 0 sau 2+ = prea ambiguu, sărim
            name_candidates.append({**clear[0], "source": source})

    return {"ean_matches": ean_matches, "name_candidates": name_candidates}


# RETAIL-AUDIT (5.3e): fara plierea diacriticelor, "căști" nu gasea "Casti ..."
# (fals negative directe in cautare si in sugestiile cross-shop). Se pliaza AMBELE
# parti — query-ul si numele — deci merge in orice combinatie.
_ACCENT_MAP = str.maketrans("ăâîșşțţ", "aaisstt")


def _fold(text: str) -> str:
    """Minuscule + diacritice romanesti pliate (inclusiv variantele cu sedila)."""
    return (text or "").lower().translate(_ACCENT_MAP)


def _tokenize_query(query: str) -> list:
    """Extrage tokenii semnificativi (minuscule, fara diacritice, lungime >= 3).

    Tokenii scurți ("de", "la", "it") sunt eliminați pentru ca cuvintele de umplutură
    să nu strice potrivirea de relevanță.
    """
    return [t for t in re.findall(r"\w+", _fold(query)) if len(t) >= 3]


def filter_by_relevance(products: list, query: str) -> list:
    """Elimină produsele al căror nume nu conține toți tokenii semnificativi din query.

    Multe motoare de căutare din magazine românești cad silențios pe rezultate
    "înrudite" fuzzy când query-ul exact nu are potriviri (ex: căutând "purito
    sleeping pack" pe eMAG returnează creme Vichy fără legătură). Acest filtru
    păstrează doar produsele al căror nume conține TOȚI tokenii semnificativi ca
    substring (case-insensitive), potrivind intenția utilizatorului pentru query-uri
    specifice brand+produs fără a tăia prea mult query-urile cu un singur cuvânt.

    Intrările sentinel de eroare/mesaj trec nefiltrate. Dacă toate produsele reale
    sunt filtrate, emitem un mesaj sintetic "fără rezultate relevante" pentru ca UI-ul
    să aibă totuși ceva de randat.
    """
    tokens = _tokenize_query(query)
    if not tokens:
        return products

    sentinels = [p for p in products if "error" in p or "message" in p]
    real = [p for p in products if "error" not in p and "message" not in p]

    filtered = [
        p for p in real
        if all(tok in _fold(p.get("name")) for tok in tokens)
    ]

    if filtered:
        return filtered
    if sentinels:
        return sentinels
    if real:
        # Am avut rezultate reale dar niciuna nu a potrivit toți tokenii → fim expliciți.
        return [{"message": "Nu s-au gasit rezultate relevante pentru aceasta cautare."}]
    return []


_FUZZY_FALLBACK_THRESHOLD = 5


def filter_by_code(products: list, code: str, field: str) -> list:
    """Păstrează produsele al căror `field` (ean sau sku) se potrivește cu `code`.

    Trei categorii per rezultat:
      - câmpul populat și se potrivește  -> potrivire exactă de încredere
      - câmpul populat dar diferit        -> eliminat (semn de fallback fuzzy, ex:
        eMAG returnând SKU-uri fără legătură pentru un SKU necunoscut)
      - câmpul este None                  -> avem încredere în scraper, DAR doar când
        sunt puține astfel de rezultate. Multe rezultate cu câmpul None la rând indică
        că magazinul a căzut pe potrivire keyword-fuzzy pentru un query numeric (eMAG
        returnează ~50 produse aleatorii când un EAN nu e în catalogul său).
    """
    code_norm = (code or "").strip().lstrip("0")
    if not code_norm:
        return products

    sentinels = [p for p in products if isinstance(p, dict) and ("error" in p or "message" in p)]
    real = [p for p in products if isinstance(p, dict) and "error" not in p and "message" not in p]

    matched_with_field = []
    matched_without_field = []
    for p in real:
        raw = p.get(field)
        # RETAIL-AUDIT (5.3e): campul poate veni lista (ean_codes la Altex) — fara
        # coercitie, .strip() pe lista arunca si omoara cautarea dupa cod.
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        v = (str(raw) if raw is not None else "").strip().lstrip("0")
        if not v:
            matched_without_field.append(p)
        elif v == code_norm:
            matched_with_field.append(p)

    if matched_with_field:
        return matched_with_field

    if matched_without_field and len(matched_without_field) <= _FUZZY_FALLBACK_THRESHOLD:
        return matched_without_field

    if sentinels:
        return sentinels
    return [{"message": f"Nu s-au gasit produse cu {field.upper()}={code} pe aceasta sursa."}]
