"""Scraper LaJumate.ro — anunturi clasificate (aplicatie Next.js).

Rescris complet de la zero (Faza 0 — diagnostic live, fara Playwright/cookie).
LaJumate e o aplicatie Next.js: fiecare pagina SSR contine
`<script id="__NEXT_DATA__">` cu datele complete in JSON (ca `__PRERENDERED_STATE__`
la OLX). Parsam acel JSON — robust, fara selectoare CSS fragile. Filozofia e ca
la Vinted: consumam raspunsul JSON al serverului, nu HTML.

Structura confirmata prin fetch-uri reale:
- Cautare full-text (canal principal):  https://lajumate.ro/anunturi/c/{kw}
  (relevanta reala pentru orice keyword; /anunturi/t/{kw} redirect -> /anunturi/c/{kw})
- Pagina categorie (fallback pe 0 rezultate): https://lajumate.ro/anunturi/{cat-slug}
- Pret:      ?price_min={int}&price_max={int}
- Stare:     ?condition=nou | ?condition=utilizat
- Judet:     ?county={slug}   (slug din countiesServer)
- Paginare:  ?page={N}   (28 anunturi/pagina)
- Ad -> props.pageProps.adsServer[] (id, title, slug, price(str), currency, city,
  user, images[].path, listed_at). URL anunt = /ad/{slug}-{id}.
- Imagini:   https://api-preprod.lajumate.ro/opt-image/{image.path}
"""
import random
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config


_IMPERSONATE = "chrome110"
_BASE = "https://lajumate.ro"
_IMG_BASE = "https://api-preprod.lajumate.ro/opt-image/"

_LAJUMATE_MAX_PAGES = 20


def _strip_accents(s: Optional[str]) -> str:
    return (s or "").lower().replace("ă", "a").replace("â", "a").replace("î", "i") \
        .replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")


def _clean_text(s) -> Optional[str]:
    """Descrierile LaJumate pot veni cu markup HTML (<p>...</p>) in JSON — il
    curatam la text simplu (cu newline-uri pe blocuri)."""
    if not s:
        return None
    txt = str(s)
    if "<" in txt and ">" in txt:
        txt = BeautifulSoup(txt, "html.parser").get_text("\n", strip=True)
    txt = txt.strip()
    return txt or None


def _county_slug(judet: Optional[str]) -> Optional[str]:
    if not judet:
        return None
    s = _strip_accents(judet).strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s or None


def _condition_param(condition: str) -> Optional[str]:
    if condition == "new":
        return "nou"
    if condition == "used":
        return "utilizat"
    return None


def _parse_price(price, currency) -> tuple[Optional[float], str]:
    cur = "EUR" if str(currency or "").strip().lower() in ("euro", "eur", "€") else "RON"
    if price is None:
        return None, cur
    digits = re.sub(r"[^\d]", "", str(price))
    if not digits:
        return None, cur
    try:
        return float(digits), cur
    except ValueError:
        return None, cur


def _parse_dt(s) -> Optional[datetime]:
    """listed_at: '2026-07-03 21:07:12' sau ISO '2026-07-03T21:07:12.000000Z'."""
    if not s:
        return None
    t = str(s).strip().replace("T", " ").replace("Z", "").split(".")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def _image_urls(ad: dict) -> list[str]:
    out: list[str] = []
    seen = set()
    for img in (ad.get("images") or []):
        path = (img or {}).get("path") if isinstance(img, dict) else None
        if path and path not in seen:
            seen.add(path)
            out.append(_IMG_BASE + path)
    if not out:
        main = ad.get("mainImage") or {}
        path = main.get("path") if isinstance(main, dict) else None
        if path:
            out.append(_IMG_BASE + path)
    return out


def _map_ad(ad: dict) -> Optional[dict]:
    if not isinstance(ad, dict):
        return None
    ad_id = ad.get("id")
    if not ad_id:
        return None
    title = (ad.get("title") or "").strip()
    if not title:
        return None

    slug = ad.get("slug") or ""
    url = f"{_BASE}/ad/{slug}-{ad_id}" if slug else f"{_BASE}/ad/{ad_id}"
    price, currency = _parse_price(ad.get("price"), ad.get("currency"))

    city = ad.get("city") or {}
    location = None
    if isinstance(city, dict):
        name = city.get("name")
        county = (city.get("county") or {}).get("name") if isinstance(city.get("county"), dict) else None
        location = ", ".join([p for p in (name, county) if p]) or None

    user = ad.get("user") or {}
    seller_name = user.get("name") if isinstance(user, dict) else None
    seller_id = str(user["id"]) if isinstance(user, dict) and user.get("id") else None

    return {
        "external_id": f"lajumate_{ad_id}",
        "platform": "lajumate",
        "title": title,
        "price": price,
        "currency": currency,
        "condition": None,  # nu e expus per-anunt in lista (doar filtru URL)
        "location": location,
        "url": url,
        "images": _image_urls(ad),
        "description": _clean_text(ad.get("description")),
        "seller_name": seller_name,
        "seller_id": seller_id,
        "listed_at": _parse_dt(ad.get("listed_at")),
    }


def _extract_page_props(html: str) -> dict:
    """Extrage props.pageProps din <script id="__NEXT_DATA__">. {} la orice esec."""
    if not html:
        return {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            raw = m.group(1) if m else None
        else:
            raw = tag.string
        if not raw:
            return {}
        import json
        data = json.loads(raw)
        return (data.get("props") or {}).get("pageProps") or {}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"LaJumate: __NEXT_DATA__ parse esuat: {str(exc)[:100]}")
        return {}


def _request(url: str) -> Optional[str]:
    headers = build_headers({"Referer": _BASE + "/"})
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
    for attempt in range(3):
        try:
            resp = curl_requests.get(url, **req_kwargs)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt)
                log_manager.emit("radar", "WARN", f"LaJumate: 429 rate-limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            if resp.status_code == 404:
                return None
            log_manager.emit("radar", "WARN", f"LaJumate: HTTP {resp.status_code} pentru {url}")
            return None
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"LaJumate: eroare fetch ({attempt+1}/3): {str(exc)[:100]}")
            time.sleep(rate_limit_backoff(attempt))
    return None


def _build_query(max_price, min_price, condition, judet, page) -> str:
    params = {}
    if max_price and max_price > 0:
        params["price_max"] = int(max_price)
    if min_price and min_price > 0:
        params["price_min"] = int(min_price)
    cond = _condition_param(condition)
    if cond:
        params["condition"] = cond
    county = _county_slug(judet)
    if county:
        params["county"] = county
    if page and page > 1:
        params["page"] = int(page)
    return urllib.parse.urlencode(params)


def _fetch_ads(url: str, channel: str) -> list[dict]:
    html = _request(url)
    if not html:
        return []
    pp = _extract_page_props(html)
    ads = pp.get("adsServer") or []
    mapped = []
    for ad in ads:
        try:
            m = _map_ad(ad)
            if m:
                mapped.append(m)
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"LaJumate: ad invalid ignorat ({channel}): {str(exc)[:80]}")
    return mapped


def _post_filter(results: list[dict], max_price, min_price, exclude_words: list) -> list[dict]:
    out = []
    for r in results:
        if is_excluded(r["title"], exclude_words):
            continue
        p = r["price"]
        if p is None:
            continue
        if max_price and max_price > 0 and p > max_price:
            continue
        if min_price and min_price > 0 and p < min_price:
            continue
        out.append(r)
    return out


def _apply_keyword_filter(results: list[dict], keyword: str) -> list[dict]:
    """Filtru local pe keyword (canal categorie), aceeasi logica ca Vinted:
    substring accent-insensitive pe titlu/descriere + stem pe primul cuvant.
    Non-destructiv: daca 0 potriviri, pastreaza rezultatele brute din categorie."""
    full = _strip_accents(keyword)
    if not full:
        return results
    first = full.split()[0] if full.split() else full
    stem = first[:5] if len(first) >= 5 else first

    def _matches(r: dict) -> bool:
        hay = _strip_accents(r.get("title")) + " " + _strip_accents(r.get("description"))
        return (full in hay) or (len(stem) >= 4 and stem in hay)

    filtered = [r for r in results if _matches(r)]
    if not filtered and results:
        log_manager.emit("radar", "WARN",
                         f"LaJumate categorie: 0 potriviri pe '{keyword}' — pastrez rezultatele brute din categorie")
        return results
    return filtered


def fetch_lajumate_listing_details(url: str) -> dict:
    """Pagina individuala anunt -> descriere completa + toate imaginile, din
    props.pageProps.adData (__NEXT_DATA__). {"images": [...], "description": str|None}.
    Oferita pentru vizualizarea detaliata din app (paritate cu fetch_olx_listing_details).
    """
    if not url:
        return {"images": [], "description": None}
    html = _request(url)
    if not html:
        return {"images": [], "description": None}
    pp = _extract_page_props(html)
    ad = pp.get("adData") or {}
    if not isinstance(ad, dict):
        return {"images": [], "description": None}
    return {
        "images": _image_urls(ad),
        "description": _clean_text(ad.get("description")),
    }


def _enrich_details(results: list[dict]) -> None:
    """Imbogateste fiecare rezultat cu toate imaginile + descrierea completa din
    pagina individuala a anuntului (adData), secvential cu delay aleator — la fel ca
    OLX/Publi24/Okazii. Modifica lista pe loc; esecul unui anunt nu opreste restul."""
    for idx, item in enumerate(results):
        if idx > 0:
            time.sleep(random.uniform(0.4, 0.8))
        try:
            details = fetch_lajumate_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"LaJumate details {item['external_id']}: {str(exc)[:100]}")
            continue


def search_lajumate(
    keyword: str,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    exclude_words: Optional[list] = None,
    category: Optional[str] = None,
    condition: str = "all",
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    page: int = 1,
) -> list[dict]:
    """Cauta pe LaJumate; returneaza listinguri in format standard.

    Canal principal: cautare full-text `/anunturi/c/{keyword}` (relevanta reala,
    confirmata pentru orice keyword). Fallback (doar pe pagina 1, cand full-text da
    0 rezultate) si daca exista categorie: pagina de categorie filtrata local pe
    keyword (stil Vinted). Fara categorie + full-text gol -> [] cu WARN.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if page > _LAJUMATE_MAX_PAGES:
        return []

    query = _build_query(max_price, min_price, condition, judet, page)
    ft_url = f"{_BASE}/anunturi/c/{urllib.parse.quote(keyword_clean)}"
    if query:
        ft_url += "?" + query
    log_manager.emit("radar", "SCAN", f'LaJumate "{keyword_clean}" (pag {page})')

    results = _fetch_ads(ft_url, "full-text")
    results = _post_filter(results, max_price, min_price, exclude_words)

    if results:
        _enrich_details(results)
        log_manager.emit("radar", "OK", f'LaJumate: {len(results)} rezultate pentru "{keyword_clean}" (pag {page})')
        return results

    # Fallback (doar pagina 1): pagina de categorie + filtru local pe keyword.
    if page == 1 and category:
        cat_slug = category.strip("/")
        cat_url = f"{_BASE}/anunturi/{cat_slug}"
        if query:
            cat_url += "?" + query
        cat_results = _fetch_ads(cat_url, "categorie")
        cat_results = _post_filter(cat_results, max_price, min_price, exclude_words)
        cat_results = _apply_keyword_filter(cat_results, keyword_clean)
        _enrich_details(cat_results)
        log_manager.emit("radar", "OK",
                         f'LaJumate (categorie {cat_slug}): {len(cat_results)} rezultate pentru "{keyword_clean}"')
        return cat_results

    if page == 1 and not category:
        log_manager.emit("radar", "WARN",
                         f'LaJumate: 0 rezultate full-text pentru "{keyword_clean}" si fara categorie de fallback')
    return []
