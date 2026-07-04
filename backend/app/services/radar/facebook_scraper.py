"""Scraper Facebook Marketplace — curl_cffi (impersonate=chrome110), FĂRĂ Playwright.

Rescris Faza 1 (2026-07-04). Diagnosticul live a arătat că un GET cu curl_cffi +
cookie-urile din storage_state-ul salvat (sesiunea Playwright de la login-ul manual)
trece de anti-bot fără login-wall și primește pagina server-rendered cu tot feed-ul
în blocuri <script type="application/json">. Playwright NU se mai importă aici —
rămâne doar la login-ul manual (services/radar/facebook_auth.py) și la
re-autentificarea automată headless (services/facebook_auth.py).

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
)

_IMPERSONATE = "chrome110"
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
    ('RON800' -> 800.0/RON, '€800' -> 800.0/EUR)."""
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
            cleaned = m.group(0).replace(".", "").replace(",", ".")
            try:
                price = float(cleaned)
            except ValueError:
                price = None
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
    _retry: bool = False,
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
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    # FB nu paginează prin URL — un singur fetch aduce tot; page>1 nu mai aduce nimic.
    if page and page > 1:
        return []
    if not is_facebook_session_valid(session_path):
        log_manager.emit("radar", "WARN",
            "Facebook: sesiune invalida/expirata — reconectare necesara")
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

            known_ids = _known_facebook_category_ids() if category else None
            excluded_sold = 0
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
                    # excluderea de categorie se aplica DOAR cand userul a ales o categorie
                    if cat_id != str(category):
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

    log_manager.emit("radar", "OK",
        f'Facebook: {len(results)} rezultate pentru "{keyword_clean}"')

    # 4.6 + PAS 3 — re-autentificare automata (o singura data). needs_reauth e conservator
    # (doar 0 rezultate + storage_state real mai vechi de 23h). session_path e pasat EXPLICIT
    # (fix-ul de cale din facebook_auth) atat la citire cat si la scriere.
    if not _retry:
        from app.services.facebook_auth import needs_reauth, re_authenticate
        if needs_reauth(results, session_path) and re_authenticate(session_path):
            return search_facebook(
                keyword=keyword, max_price=max_price, judet=judet, oras=oras,
                exclude_words=exclude_words, session_path=session_path,
                min_price=min_price, category=category, page=page,
                max_scrolls=max_scrolls, _retry=True,
            )
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
    """Enrichment on-demand pentru un anunt Facebook — descriere completa + toata
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
