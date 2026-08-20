"""Scraper Facebook Marketplace — curl_cffi (profil de impersonare centralizat in
app/utils/http_profile.py), FĂRĂ Playwright.

Rescris Faza 1 (2026-07-04). Diagnosticul live a arătat că un GET cu curl_cffi +
cookie-urile din storage_state-ul salvat (sesiunea Playwright de la login-ul manual)
trece de anti-bot fără login-wall și primește pagina server-rendered cu tot feed-ul
în blocuri <script type="application/json">. Playwright NU se mai importă aici —
rămâne doar la login-ul manual (services/radar/facebook_auth.py). Re-autentificarea
automată headless a fost ELIMINATĂ la R5 (risc de checkpoint pe cont) — când sesiunea
moare doar semnalizăm; vezi services/facebook_auth.py.

Cardurile de listare sunt obiecte JSON care au SIMULTAN cheile
"marketplace_listing_title" și "id" (typename observat GroupCommerceProductItem, dar
căutăm STRUCTURAL după cele două chei ca să prindem și alte typename-uri). Câmpurile
disponibile direct pe pagina de search (fără fetch de detaliu): id,
marketplace_listing_title, listing_price.amount/formatted_amount, creation_time (în
if_gk_just_listed_tag_on_search_feed), primary_listing_photo.image.uri,
location.reverse_geocode.city / city_page.display_name,
marketplace_listing_seller.name/.id, marketplace_listing_category_id, is_sold/is_live/
is_pending/is_hidden.

LOCAȚIE (judet/oras): testat live pe 2026-07-04 — filtrarea prin path de oraș NU
funcționează. /marketplace/{slug}/search/ fie e redirecționat spre
/marketplace/category/search/ (slug RO nerecunoscut: cluj-napoca, timisoara, iasi,
constanta, bucuresti), fie păstrat dar întoarce EXACT același set de anunțuri
(Jaccard 1.00 între toate orașele testate). Locația pe FB Marketplace e legată de
lat/long-ul CONTULUI (buyLocation în GraphQL, ex. Bucureşti 44.43/26.10) + rază, nu
de URL. Deci judet/oras rămân NEFOLOSITE (nu inventăm o filtrare falsă); URL-ul e
/marketplace/search/ care respectă automat locația contului din sesiune.
"""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import (
    build_headers, rate_limit_backoff, is_excluded, get_proxy_config,
    report_outcome, Outcome,
)
# FBS-8 — helper PUR (fara DB, fara mediu); sta langa celelalte reguli de potrivire
# pe titlu, nu in scraper, ca sa fie testabil table-driven ca restul motorului.
from app.services.radar.exclusion_engine import keyword_digits_match
# Helper pur (fara dependinte) — nu poate crea ciclu de import. Vezi R1 in _parse_price.
from app.utils.number_format import parse_number
from app.utils.http_profile import DEFAULT_IMPERSONATE
# FB-5: nucleul logat-out (FB-1) + registrul de ancore (FB-2). Aliasurile exista ca
# testele sa inlocuiasca o singura tinta pe modulul asta, fara sa atinga nucleul.
# Calea de sesiune (A4) NU le foloseste — ea ramane pe functiile de mai jos.
from app.scrapers.facebook import search as nucleu_search
from app.scrapers.facebook import fetch_detail as nucleu_fetch_detail
from app.scrapers.facebook.anchors import dupa_slug

_IMPERSONATE = DEFAULT_IMPERSONATE   # profil unic, vezi app/utils/http_profile.py
_BASE = "https://www.facebook.com"
_SCRIPT_JSON_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.DOTALL
)


def _session_max_age_days() -> int:
    return 30


def is_facebook_session_valid(session_path: Optional[str]) -> bool:
    """True daca fisierul exista, contine cookies si nu e mai vechi de 30 zile.

    NESCHIMBATA fata de varianta Playwright — verifica doar fisierul de sesiune
    (existenta + cookie c_user + varsta), nu depinde de Playwright.
    """
    if not session_path:
        return False
    if not os.path.isfile(session_path):
        return False
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not cookies:
            return False
        has_cuser = any(c.get("name") == "c_user" for c in cookies)
        if not has_cuser:
            return False
        # Check timestamp
        mtime = os.path.getmtime(session_path)
        age_days = (time.time() - mtime) / 86400
        return age_days < _session_max_age_days()
    except Exception as exc:
        print(f"[FacebookScraper] Eroare la validarea sesiunii: {exc}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Helpers curl_cffi
# ──────────────────────────────────────────────────────────────────────────────

def _load_cookies(session_path: str) -> dict:
    """storage_state Playwright -> dict {name: value} pentru curl_cffi."""
    with open(session_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("cookies") if isinstance(data, dict) else data
    return {
        c["name"]: ("" if c.get("value") is None else c["value"])
        for c in (raw or []) if c.get("name")
    }


def _build_search_url(keyword: str, min_price: Optional[float],
                      max_price: Optional[float]) -> str:
    """/marketplace/search/?query=&minPrice=&maxPrice= — FĂRĂ &category= (filtrarea
    de categorie se face client-side, vezi mai jos) și FĂRĂ path de oraș (vezi nota
    despre locație din docstring-ul modulului)."""
    q = urllib.parse.quote(keyword)
    min_p = int(min_price) if (min_price and min_price > 0) else 0
    url = f"{_BASE}/marketplace/search/?query={q}&minPrice={min_p}"
    if max_price and max_price > 0:
        url += f"&maxPrice={int(max_price)}"
    return url


def _fetch(url: str, cookies: dict) -> tuple[Optional[str], Optional[str]]:
    """GET cu curl_cffi + retry/backoff la 429 și erori de rețea (3 încercări, ca la
    Okazii). Întoarce (html, final_url) sau (None, final_url_or_None)."""
    headers = build_headers()
    proxy_cfg = get_proxy_config()
    kwargs = {
        "headers": headers, "cookies": cookies, "impersonate": _IMPERSONATE,
        "timeout": 30, "allow_redirects": True,
    }
    if proxy_cfg:
        kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}

    for attempt in range(3):
        try:
            resp = curl_requests.get(url, **kwargs)
            if resp.status_code == 200:
                return (resp.text or ""), str(resp.url)
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt)
                log_manager.emit("radar", "WARN",
                    f"Facebook: 429 rate-limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            log_manager.emit("radar", "WARN", f"Facebook: HTTP {resp.status_code}")
            return None, str(resp.url)
        except Exception as exc:
            log_manager.emit("radar", "WARN",
                f"Facebook: eroare fetch ({attempt+1}/3): {str(exc)[:100]}")
            time.sleep(rate_limit_backoff(attempt))
    return None, None


# ──────────────────────────────────────────────────────────────────────────────
# Parser JSON
# ──────────────────────────────────────────────────────────────────────────────

def _iter_listing_objects(html: str) -> list[dict]:
    """Extrage toate <script type=application/json>, json.loads pe fiecare (skip la
    eroare) și walk recursiv după orice dict cu AMBELE chei
    'marketplace_listing_title' și 'id'."""
    found: list[dict] = []

    def walk(obj):
        if isinstance(obj, dict):
            if "marketplace_listing_title" in obj and "id" in obj:
                found.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for block in _SCRIPT_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        walk(data)
    return found


# R3 / FBM-1e — markerii formularului de login servit IN pagina. Facebook raspunde
# frecvent 200 pe URL-ul ORIGINAL, cu formularul de login in corp si FARA redirect,
# deci verificarea pe final_url nu-l prinde: iese "0 rezultate OK", iar plasa
# session_probably_expired cere fisier de sesiune mai vechi de 23h — o sesiune
# invalidata la 2h dupa login producea zile de zero-uri tacute.
# Detectorul a fost scris intai in scrapers/real_estate/facebook_real_estate (FBM-1f,
# cu teste); aici e casa lui canonica — modulul FB din care importa deja
# facebook_auto_scraper si, de la R3, si facebook_real_estate.
_LOGIN_EMAIL_RE = re.compile(r"""name\s*=\s*(?:"email"|'email'|email\b)""", re.IGNORECASE)
_LOGIN_PASS_RE = re.compile(r"""name\s*=\s*(?:"pass"|'pass'|pass\b)""", re.IGNORECASE)
_LOGIN_ACTION_RE = re.compile(r"""<form[^>]*\baction\s*=\s*['"]?[^'">\s]*/login""",
                              re.IGNORECASE)


def _looks_like_login_wall(html) -> bool:
    """True daca html-ul poarta markerii formularului de login Facebook.

    Cel putin unul: id-ul `royal_login_form`, perechea name="email" + name="pass" pe
    acelasi document, sau un <form> al carui action contine "/login". Tolerant la
    ghilimele simple/duble si la majuscule. Pe o pagina normala de marketplace: False.
    """
    if not html:
        return False
    low = str(html).lower()
    if "royal_login_form" in low:
        return True
    if _LOGIN_EMAIL_RE.search(low) and _LOGIN_PASS_RE.search(low):
        return True
    return bool(_LOGIN_ACTION_RE.search(low))


def _deep_first(obj, key: str, _depth: int = 0):
    """Prima valoare scalară pentru `key` oriunde în obiect (creation_time e imbricat
    în if_gk_just_listed_tag_on_search_feed, nu la nivelul de sus)."""
    if _depth > 6:
        return None
    if isinstance(obj, dict):
        if key in obj and not isinstance(obj[key], (dict, list)):
            return obj[key]
        for v in obj.values():
            r = _deep_first(v, key, _depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_first(v, key, _depth + 1)
            if r is not None:
                return r
    return None


def _parse_price(obj: dict) -> tuple[Optional[float], str]:
    """Prioritate listing_price.amount (float); fallback regex pe formatted_amount
    ('RON800' -> 800.0/RON, '€800' -> 800.0/EUR).

    R1 (audit FB): fallback-ul facea un replace orb `.replace(".","").replace(",",".")`,
    deci "RON1,500" -> 1.5 si "€1,234.56" -> 1.23 — de 1000x mai mic, TACUT si in gama
    care trece de filtrele de pret. Formatul EN cu virgula de mii e frecvent pe
    Marketplace. Regula corecta e in app/utils/number_format.parse_number (aceeasi
    deja dovedita pe Imobiliare). Modulul Auto primeste fixul automat: facebook_auto_scraper
    importa _parse_price de aici.
    """
    lp = obj.get("listing_price") or {}
    fmt = lp.get("formatted_amount") or ""
    currency = "RON"
    if fmt:
        up = fmt.upper()
        if "€" in fmt or "EUR" in up:
            currency = "EUR"
        elif "$" in fmt or "USD" in up:
            currency = "USD"

    price = None
    amount = lp.get("amount")
    if amount not in (None, ""):
        try:
            price = float(amount)
        except (ValueError, TypeError):
            price = None
    if price is None and fmt:
        m = re.search(r"[\d.,]+", fmt)
        if m:
            price = parse_number(m.group(0))
    return price, currency


def _parse_location(obj: dict) -> Optional[str]:
    rg = (obj.get("location") or {}).get("reverse_geocode") or {}
    city = rg.get("city")
    if city:
        return city
    return (rg.get("city_page") or {}).get("display_name")


def _is_active(obj: dict) -> bool:
    """Exclude sold/not-live/pending/hidden — DOAR daca cheia e prezenta (lipsa cheii
    NU inseamna exclus)."""
    if obj.get("is_sold") is True:
        return False
    if obj.get("is_live") is False:
        return False
    if obj.get("is_pending") is True:
        return False
    if obj.get("is_hidden") is True:
        return False
    return True


def _known_facebook_category_ids() -> set:
    """Toate id-urile de categorie din PLATFORM_CATEGORIES['facebook'] (top-level +
    subcategorii), ca sa putem loga category_id-uri necunoscute."""
    from app.services.radar.categories import PLATFORM_CATEGORIES
    ids = set()
    for cat in PLATFORM_CATEGORIES.get("facebook", []):
        if cat.get("value"):
            ids.add(str(cat["value"]))
        for sub in cat.get("subcategories") or []:
            if sub.get("value"):
                ids.add(str(sub["value"]))
    return ids


# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────

_ANCORA_IMPLICITA = "bucuresti"


def _ancora_configurata(env_var: str, modul_log: str):
    """Ancora geografica interim a unui apel (slug din registrul FB-2).

    O SINGURA ancora per apel: scanner-ul de azi nu stie de ancore, iar acoperirea pe
    toate cele 51 vine cu planificatorul la FB-6. Slug necunoscut = WARN + Bucuresti.
    """
    slug = (os.getenv(env_var) or _ANCORA_IMPLICITA).strip().lower()
    ancora = dupa_slug(slug)
    if ancora is None:
        log_manager.emit(modul_log, "WARN",
            f"Facebook: ancora '{slug}' nu exista in registru — folosesc "
            f"'{_ANCORA_IMPLICITA}'.")
        ancora = dupa_slug(_ANCORA_IMPLICITA)
    return ancora


def _naiv_local(dt):
    """UTC aware (conventia nucleului) -> naiv local (conventia Radar/Auto).

    `_too_old` din radar_scanner compara `datetime.now()` naiv cu `listed_at`, deci un
    datetime aware ar arunca TypeError acolo. Imobiliare a mers pe alt drum (string
    ISO) fiindca scanner-ul lui face `fromisoformat` — conventii diferite per
    consumator, fiecare respectata.
    """
    return dt.astimezone().replace(tzinfo=None) if dt else None


def _search_logout(keyword: str, max_price, exclude_words, min_price, category) -> list[dict]:
    """Calea LOGAT-OUT (FB_MOD=logout): search prin nucleul FB-1, fara sesiune.

    Filtrele sunt aceleasi ca pe sesiune, aplicate pe dicturile canonice si prin
    ACELEASI functii de modul (`is_excluded`, `_known_facebook_category_ids`), ca sa
    nu divergem. `seller_name`/`seller_id` sunt None: vanzatorul NU exista logat-out
    (masurat) — nu e o pierdere de parsare, ci o lipsa la sursa.
    """
    ancora = _ancora_configurata("FB_RADAR_ANCORA", "radar")
    log_manager.emit("radar", "SCAN", f'Facebook nucleu "{keyword}"')

    # FBS-6 — pragul pleaca SERVER-SIDE pe treapta 1 (SSR), unde e MASURAT ca
    # respectat (FBS-V1b). Normalizarea e EXACT cea din `_build_search_url`: strict
    # pozitiv inseamna prag, orice altceva inseamna „fara prag" — doua semantici ale
    # aceleiasi valori pe cai diferite ar fi o divergenta tacuta.
    # Filtrul local din `_din_canonice` ramane NEATINS, deliberat (D1): el e plasa
    # care prinde si treapta 2 (GraphQL nu poarta filtrul) si orice degradare.
    pret_min = int(min_price) if (min_price and min_price > 0) else None
    canonice = nucleu_search(keyword, ancora.lat, ancora.lon, raza_km=65.0,
                             city_page_id=ancora.city_page_id,
                             pret_min=pret_min) or []
    return _din_canonice(canonice, keyword, max_price, exclude_words,
                         min_price, category)


def _din_canonice(canonice, keyword, max_price, exclude_words, min_price,
                  category) -> list[dict]:
    """Dicturi CANONICE -> forma pe care o asteapta Radar.

    Extras din `_search_logout` la FBS-5 si folosit IDENTIC de calea de bazin. Asta e
    ce garanteaza ca forma intoarsa e aceeasi indiferent de unde vin datele: nu prin
    doua implementari tinute sincronizate cu atentie, ci prin una singura.
    """
    known_ids = _known_facebook_category_ids() if category else None
    results: list[dict] = []
    vazute = set()
    fara_categorie = 0
    cifre_lipsa = 0
    for c in canonice:
        title = (c.get("title") or "").strip()
        if not title:
            continue
        if is_excluded(title, exclude_words):
            continue
        # FBS-8 — a doua poarta pe titlu: cifrele keyword-ului trebuie sa apara in el.
        # Cautarea Facebook e fuzzy pe model (masurat la FBS-V2: „iphone 15 pro max"
        # intoarce 14 si 17 Pro Max, relevanta 0%), iar pragul de pret taie gunoiul
        # grosier dar NU separa modelele. Pe keyword-uri fara cifre regula e no-op.
        if not keyword_digits_match(keyword, title):
            cifre_lipsa += 1
            continue

        price = c.get("price")
        if price is None or price <= 0:
            continue
        if max_price and max_price > 0 and price is not None and price > max_price:
            continue
        if min_price and min_price > 0 and price is not None and price < min_price:
            continue

        cat_id = c.get("category_id")
        cat_id = str(cat_id) if cat_id is not None else None
        if category:
            if cat_id and known_ids is not None and cat_id not in known_ids:
                log_manager.emit("radar", "INFO",
                    f"Facebook: category_id necunoscut {cat_id} ('{title[:40]}')")
            # A6/A7 — aceeasi regula fail-open ca pe sesiune: se exclude DOAR cand
            # cardul poarta o categorie care difera. Vezi comentariul lung din
            # _search_sesiune; NU transforma in comparatie stricta.
            if cat_id is None:
                fara_categorie += 1
            elif cat_id != str(category):
                continue

        ext = str(c.get("external_id") or "")
        if not ext or ext in vazute:
            continue
        vazute.add(ext)

        image_url = c.get("image_url")
        results.append({
            # canonic-ul da id-ul BRUT (prefixarea e treaba consumatorului) — Radar
            # isi pune prefixul aici, ca pe sesiune.
            "external_id": f"fb_{ext}",
            "platform": "facebook",
            "title": title,
            "price": price,
            "currency": c.get("currency"),
            "condition": None,
            "location": c.get("location"),
            "url": c.get("source_url"),
            "images": [image_url] if image_url else [],
            "description": None,
            "seller_name": None,
            "seller_id": None,
            "listed_at": _naiv_local(c.get("listed_at")),
        })

    if cifre_lipsa:
        log_manager.emit("radar", "INFO",
            f"Facebook: {cifre_lipsa} anunturi sarite — cifrele din "
            f'"{keyword}" nu apar in titlu (model gresit)')
    if fara_categorie:
        log_manager.emit("radar", "INFO",
            f"Facebook: {fara_categorie} anunturi pastrate fara categorie pe card "
            f"(nu se poate verifica filtrul de categorie)")
    log_manager.emit("radar", "OK",
        f'Facebook nucleu/bazin: {len(results)} rezultate pentru "{keyword}"')
    return results


def search_facebook(
    keyword: str,
    max_price: float,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    exclude_words: Optional[list[str]] = None,
    session_path: Optional[str] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    page: int = 1,
    max_scrolls: int = 10,
    keyword_id: Optional[int] = None,
) -> list[dict]:
    """Caută pe Facebook Marketplace cu o sesiune pre-logată, prin curl_cffi.

    Semnătura e păstrată identică cu apelurile existente (radar_scanner, radar router).

    `max_scrolls` — NO-OP (păstrat pentru compatibilitate). Nu se mai face scroll:
        pagina server-rendered conține deja tot feed-ul inițial în JSON.
    `page` — NO-OP efectiv (FB nu paginează prin URL, e un singur fetch); pentru page>1
        întoarcem [] ca semnal „gata" (scanner-ul oricum se oprește după prima pagină
        la facebook). `judet`/`oras` — NEFOLOSITE (vezi docstring modul: locația nu se
        poate filtra prin URL).
    `category` — dacă e setat, se filtrează CLIENT-SIDE pe
        marketplace_listing_category_id == category.

    FB-5 (A4): dispecer pe `FB_MOD`. `logout` = nucleul logat-out (fără sesiune);
    ORICE altceva, inclusiv variabila absentă, = calea de sesiune de până acum,
    neschimbată. Implicitul rămâne `sesiune` DELIBERAT: calea logat-out scanează
    deocamdată o singură ancoră per apel, deci ar îngusta geografic feed-ul;
    comutarea se face la FB-6, cu planificatorul. Fără fallback automat între căi.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    # FB nu pagineaza prin URL — un singur fetch aduce tot; page>1 nu mai aduce nimic.
    # Garda sta in dispecer, INAINTE de orice cale: semantica e a platformei, nu a caii.
    if page and page > 1:
        return []

    from app.scrapers.facebook.mod import mod_fb
    mod = mod_fb("radar")
    if mod == "nucleu":
        return _search_logout(keyword_clean, max_price, exclude_words, min_price, category)
    if mod == "bazin":
        return _search_bazin(keyword_clean, keyword_id, max_price, exclude_words,
                             min_price, category)
    if mod != "sesiune":
        log_manager.emit("radar", "WARN",
            f"Facebook: FB_MOD='{mod}' necunoscut — folosesc calea de sesiune.")
    return _search_sesiune(keyword, max_price, judet, oras, exclude_words,
                           session_path, min_price, category, page, max_scrolls)


def _scutire_manuala(modul_log: str, termen: str, cale_nucleu, *args):
    """SCUTIREA CAUTARILOR MANUALE de `FB_MOD=bazin` (FBS-5b, varianta 1).

    Cele doua cautari manuale — `routers/radar.py` si `routers/auto.py` — n-au rand de
    keyword, deci n-au `keyword_id`, deci n-au cu ce interoga bazinul. Sub
    `FB_MOD=bazin` ar fi intors lista goala: pentru omul care tocmai a apasat „cauta
    acum", asta inseamna ZERO rezultate Facebook fara nicio explicatie — exact clasa
    de defect pe care seria o tot prinde.

    Alegerea: cad pe NUCLEU, nu pe gol. O cautare manuala e o cerere initiata de un
    om, adica exact traficul care seamana cel mai bine cu trafic uman; volumul e
    marginit de cat apasa omul, iar clientul are deja pauze si zavor de blocaj.
    Contra-argumentul, lasat explicit pe masa: apasari repetate produc trafic pe care
    `FB_MOD=bazin` tocmai incerca sa-l elimine — marginirea vine din pauze si zavor,
    NU dintr-un buget.

    Semnalul e chiar ABSENTA lui `keyword_id`: dupa FBS-5b toti cei trei scanneri il
    paseaza, deci un apel fara el e manual. Daca un apelant viitor uita sa-l paseze,
    linia de mai jos apare oricum si e greppabila — nu se pierde in tacere.
    """
    log_manager.emit(modul_log, "INFO",
        f"FBMANUAL FB_MOD=bazin dar cererea n-are `keyword_id` (cautare manuala) "
        f"pentru {termen!r} — se foloseste NUCLEUL, nu bazinul")
    return cale_nucleu(*args)


def _search_bazin(keyword: str, keyword_id, max_price, exclude_words,
                  min_price, category) -> list[dict]:
    """Citire din `fb_pool`, ZERO retea. Filtrele se aplica CLIENT-SIDE, prin exact
    acelasi `_din_canonice` pe care il foloseste calea vie."""
    if not keyword_id:
        return _scutire_manuala("radar", keyword, _search_logout,
                                keyword, max_price, exclude_words, min_price, category)
    from app.database import SessionLocal
    from app.scrapers.facebook.bazin import citeste
    db = SessionLocal()
    try:
        canonice = citeste(db, "radar", keyword_id)
    finally:
        db.close()
    log_manager.emit("radar", "SCAN",
        f'Facebook bazin "{keyword}": {len(canonice)} anunturi in bazin')
    return _din_canonice(canonice, keyword, max_price, exclude_words,
                         min_price, category)


def _search_sesiune(
    keyword: str,
    max_price: float,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    exclude_words: Optional[list[str]] = None,
    session_path: Optional[str] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    page: int = 1,
    max_scrolls: int = 10,
) -> list[dict]:
    """Calea de sesiune, FB_MOD=sesiune — mutata verbatim din search_facebook la FB-5."""
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    # FB nu paginează prin URL — un singur fetch aduce tot; page>1 nu mai aduce nimic.
    if page and page > 1:
        return []
    if not is_facebook_session_valid(session_path):
        # R5 — aici se incerca un login automat headless. A fost ELIMINAT: chromium
        # fara masca + parola din .env = profil de checkpoint, iar un checkpoint
        # declansat automat poate bloca si sesiunile MANUALE ale contului. Acum doar
        # semnalizam: WARN pentru user + BLOCKED la watchdog (alerta dupa prag).
        log_manager.emit("radar", "WARN",
            "Facebook: sesiune invalida/expirata — reconecteaza din Setari Radar → Facebook")
        report_outcome("facebook", Outcome.BLOCKED)
        return []

    cookies = _load_cookies(session_path)
    url = _build_search_url(keyword_clean, min_price, max_price)
    log_manager.emit("radar", "SCAN", f'Facebook "{keyword_clean}"')

    html, final_url = _fetch(url, cookies)

    results: list[dict] = []
    if html is not None:
        low = (final_url or "").lower()
        if "login" in low or "checkpoint" in low:
            # 4.6 — redirect spre login/checkpoint => sesiune expirata (results ramane gol)
            log_manager.emit("radar", "WARN",
                "Facebook: redirect spre login/checkpoint — sesiune posibil expirata")
        else:
            raw = _iter_listing_objects(html)
            by_id: dict[str, dict] = {}
            for o in raw:
                oid = str(o.get("id"))
                if oid and oid not in by_id:
                    by_id[oid] = o

            # R3 — login-wall servit pe 200, fara redirect: SINGURUL semn e HTML-ul.
            # Verificam doar cand nu exista NICIUN obiect de listare (cand exista,
            # pagina e clar cea buna si scanarea HTML-ului ar fi cost inutil).
            # Comportamentul e identic cu ramura de redirect de mai sus: WARN si
            # `results` gol, deci semnalul de sesiune moarta de la final se judeca la
            # fel — nu exista cale noua. In plus raportam BLOCKED la watchdog, ca sa
            # existe si o alerta de platforma, nu doar badge-ul de sesiune din UI.
            if not by_id and _looks_like_login_wall(html):
                log_manager.emit("radar", "WARN",
                    "Facebook: pagina de login servita fara redirect — sesiune posibil invalida")
                report_outcome("facebook", Outcome.BLOCKED)

            known_ids = _known_facebook_category_ids() if category else None
            excluded_sold = 0
            fara_categorie = 0      # A6/A7 — pastrate desi cardul nu poarta categorie
            for oid, o in by_id.items():
                if not _is_active(o):
                    excluded_sold += 1
                    continue
                title = (o.get("marketplace_listing_title") or "").strip()
                if not title:
                    continue
                if is_excluded(title, exclude_words):
                    continue

                price, currency = _parse_price(o)
                # SCRAPE-AUDIT: pretul neparsat trecea mai departe si devenea 0 in
                # scanner -> marja 100% -> grad A fals + notificari. OLX si Vinted
                # sar deja listingurile fara pret; Facebook era singurul care nu.
                if price is None or price <= 0:
                    continue
                if max_price and max_price > 0 and price is not None and price > max_price:
                    continue
                if min_price and min_price > 0 and price is not None and price < min_price:
                    continue

                cat_id = o.get("marketplace_listing_category_id")
                cat_id = str(cat_id) if cat_id is not None else None
                if category:
                    # category_id necunoscut in tabel -> logam, dar NU excludem pe acest motiv
                    if cat_id and known_ids is not None and cat_id not in known_ids:
                        log_manager.emit("radar", "INFO",
                            f"Facebook: category_id necunoscut {cat_id} ('{title[:40]}')")
                    # A6/A7 — excluderea se aplica DOAR cand userul a ales o categorie SI
                    # cardul chiar poarta una care difera. Facebook nu pune
                    # marketplace_listing_category_id pe toate cardurile, iar comparatia
                    # stricta de dinainte (`cat_id != str(category)`, adevarata si pentru
                    # None) stergea TACUT anunturi reale de indata ce userul alegea o
                    # categorie. Conventia proiectului e fail-open: un criteriu care nu se
                    # poate verifica NU respinge — vezi _matches_re_keyword (Imobiliare),
                    # plasa year/km din Auto, _is_active de mai sus si filtrul identic din
                    # facebook_auto_scraper, cu care ne aliniem aici. NU transforma inapoi
                    # in comparatie stricta.
                    if cat_id is None:
                        fara_categorie += 1
                    elif cat_id != str(category):
                        continue

                ct = _deep_first(o, "creation_time")
                listed_at = None
                if isinstance(ct, (int, float)) and ct > 1_000_000_000:
                    try:
                        listed_at = datetime.fromtimestamp(ct)
                    except (OverflowError, OSError, ValueError):
                        listed_at = None

                image_url = ((o.get("primary_listing_photo") or {}).get("image") or {}).get("uri")
                images = [image_url] if image_url else []
                seller = o.get("marketplace_listing_seller") or {}

                results.append({
                    "external_id": f"fb_{oid}",
                    "platform": "facebook",
                    "title": title,
                    "price": price,
                    "currency": currency,
                    "condition": None,
                    "location": _parse_location(o),
                    "url": f"{_BASE}/marketplace/item/{oid}/",
                    "images": images,
                    "description": None,
                    "seller_name": seller.get("name"),
                    "seller_id": seller.get("id"),
                    # creation_time daca exista; altfel None (mai bine null decat now() fals)
                    "listed_at": listed_at,
                })

            if excluded_sold:
                log_manager.emit("radar", "INFO",
                    f"Facebook: {excluded_sold} anunturi excluse (sold/not-live/pending/hidden)")
            if fara_categorie:
                # Vizibilitate pentru user: de ce vede si anunturi in afara categoriei alese.
                log_manager.emit("radar", "INFO",
                    f"Facebook: {fara_categorie} anunturi pastrate fara categorie pe card "
                    f"(nu se poate verifica filtrul de categorie)")

    log_manager.emit("radar", "OK",
        f'Facebook: {len(results)} rezultate pentru "{keyword_clean}"')

    # R5 — semnalizare in loc de re-autentificare automata. Detectia ramane aceeasi
    # (0 rezultate + storage_state real mai vechi de 23h, deci conservatoare), dar
    # actiunea nu mai e un login headless, ci un semnal: WARN pentru user si BLOCKED
    # la health_watchdog, care alerteaza dupa pragul lui. Vezi facebook_auth.py.
    from app.services.facebook_auth import session_probably_expired
    if session_probably_expired(results, session_path):
        log_manager.emit("radar", "WARN",
            "Facebook: 0 rezultate si sesiune veche (>23h) — pare expirata, "
            "reconecteaza din Setari Radar → Facebook")
        report_outcome("facebook", Outcome.BLOCKED)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Enrichment on-demand (descriere + galerie din pagina de detaliu)
# ──────────────────────────────────────────────────────────────────────────────

def _collect_key(root, key: str) -> list:
    """Toate valorile pentru cheia `key` oriunde in structura JSON (recursiv)."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key:
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(root)
    return found


def fetch_facebook_listing_detail(url: str, session_path: Optional[str]) -> dict:
    """Enrichment on-demand: descriere + galerie, din pagina de detaliu.

    FB-5 (A4): dispecer pe `FB_MOD`, ca `search_facebook`. Pe `logout` cererea pleaca
    prin nucleu si `session_path` e IGNORAT (calea logat-out nu are sesiune); pe orice
    altceva ruleaza corpul de pana acum, neschimbat. Semnatura publica ramane aceeasi,
    deci consumatorii care o imbraca — inclusiv auto/listings/detail.py — mostenesc
    dispecerul automat, fara sa fie atinsi.
    """
    mod = (os.getenv("FB_MOD") or "sesiune").strip().lower()
    if mod == "logout":
        return nucleu_fetch_detail(url)
    return _detail_sesiune(url, session_path)


def _detail_sesiune(url: str, session_path: Optional[str]) -> dict:
    """Calea de sesiune, FB_MOD=sesiune — mutata verbatim din
    fetch_facebook_listing_detail la FB-5.

    Enrichment on-demand pentru un anunt Facebook — descriere completa + toata
    galeria de poze, din pagina de detaliu, prin curl_cffi (FARA Playwright).

    Mirror pe stilul fetch_okazii_listing_details / get_vinted_item_detail. Cheile
    exacte au fost confirmate live pe pagina de detaliu (diagnostic Partea A):
      - descriere: cheia 'redacted_description' -> {"text": "<descrierea vanzatorului>"}
      - galerie:   cheia 'listing_photos' -> [{"image": {"uri": "<...fbcdn...>"}}, ...]
    Cautam STRUCTURAL dupa aceste doua chei (nu presupunem calea completa din JSON).

    Returneaza {"description": str|None, "images": [urls]|None}. La orice eroare /
    fetch esuat / login-wall -> {"description": None, "images": None} (fara exceptie).
    """
    if not url or not is_facebook_session_valid(session_path):
        return {"description": None, "images": None}
    try:
        html, final_url = _fetch(url, _load_cookies(session_path))
        if not html:
            return {"description": None, "images": None}
        low = (final_url or "").lower()
        if "login" in low or "checkpoint" in low:
            log_manager.emit("radar", "WARN",
                "Facebook detail: redirect login/checkpoint — sesiune posibil expirata")
            return {"description": None, "images": None}

        description = None
        images: list[str] = []
        for block in _SCRIPT_JSON_RE.findall(html):
            try:
                data = json.loads(block)
            except Exception:
                continue
            # descriere — pastram cea mai lunga valoare redacted_description.text
            for rd in _collect_key(data, "redacted_description"):
                txt = rd.get("text") if isinstance(rd, dict) else rd
                if isinstance(txt, str) and txt.strip():
                    txt = txt.strip()
                    if description is None or len(txt) > len(description):
                        description = txt
            # galerie — pastram cea mai mare lista listing_photos (uri per element)
            for lst in _collect_key(data, "listing_photos"):
                if not isinstance(lst, list):
                    continue
                uris = []
                for el in lst:
                    if isinstance(el, dict):
                        uri = (el.get("image") or {}).get("uri")
                        if isinstance(uri, str) and uri:
                            uris.append(uri)
                if len(uris) > len(images):
                    images = uris

        return {"description": description, "images": images or None}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Facebook detail esuat: {str(exc)[:100]}")
        return {"description": None, "images": None}
