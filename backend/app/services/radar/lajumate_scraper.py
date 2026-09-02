"""Scraper LaJumate.ro — anunturi clasificate (aplicatie Next.js).

Rescris complet de la zero (Faza 0 — diagnostic live, fara Playwright/cookie).
LaJumate e o aplicatie Next.js: fiecare pagina SSR contine
`<script id="__NEXT_DATA__">` cu datele complete in JSON (ca `__PRERENDERED_STATE__`
la OLX). Parsam acel JSON — robust, fara selectoare CSS fragile. Filozofia e ca
la Vinted: consumam raspunsul JSON al serverului, nu HTML.

CAUTAREA merge pe API-ul JSON public (LJ-1, masurat 2026-09-03). Pagina SSR
`/anunturi/c/{kw}` NU MAI FILTREAZA prin parametrii de URL: `?price_min`, `?price_max`,
`?condition` si `?county` sunt IGNORATI, iar raspunsul e mereu aceleasi ~28 de anunturi
nefiltrate. Cu filtrarea facuta local doar pe prima pagina, un keyword cu prag de pret
strans nu gasea niciodata nimic (masurat: "iphone" 700-2000 RON, zero randuri in
productie, ciclu de ciclu). API-ul face filtrarea server-side si intoarce si `total`.

Structura confirmata prin fetch-uri reale (2026-09-03):
- Cautare (canal UNIC):  https://api-preprod.lajumate.ro/api/listing/{pagina}
  Public: fara cookie, fara cheie, insensibil la amprenta TLS (raspuns identic
  octet cu octet cu si fara profil de impersonare).
- Pret:      ?filters[price_min][0]={int}&filters[price_max][0]={int}&currency=lei
             (`currency` spune in ce moneda se CITESC pragurile; preturile din raspuns
              raman mereu in lei)
- Categorie: ?parent_id={principala}&category_id={subcategorie}   (slug-uri)
- Stare:     ?filters[condition][0]=nou | utilizat
- Judet:     ?filters[county][0]={slug}
- Sortare:   ?sort=date_desc
- Paginare:  pagina e in PATH (/listing/2), nu in query. Raspunsul are
  `current_page`, `last_page`, `per_page` (28) si `total`.
- Ad -> data[] (id, title, slug, price(str "800.00"), currency("lei"), city, user,
  images[].path, mainImage.path, description, listed_at "2026-08-29 06:34:45").
  URL anunt = /ad/{slug}-{id}.
- Imagini:   https://api-preprod.lajumate.ro/opt-image/{image.path}

DETALIILE raman pe HTML: pagina individuala a anuntului, `<script id="__NEXT_DATA__">`
-> props.pageProps.adData (ca `__PRERENDERED_STATE__` la OLX).
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
from app.services.network import binding
from app.services.radar.base_scraper import (
    build_headers, rate_limit_backoff, is_excluded, get_proxy_config,
    classify, report_outcome, Outcome,
)
from app.utils.http_profile import DEFAULT_IMPERSONATE


_IMPERSONATE = DEFAULT_IMPERSONATE   # profil unic, vezi app/utils/http_profile.py
_BASE = "https://lajumate.ro"
_IMG_BASE = "https://api-preprod.lajumate.ro/opt-image/"
_API_BASE = "https://api-preprod.lajumate.ro/api"
# Headerele pe care le trimite si browserul catre API (fara ele merge, cu ele suntem
# identici cu clientul real). `Referer` il pune _request, comun cu calea de detalii.
_API_HEADERS = {"Accept": "application/json", "Origin": _BASE}

# Garda: API-ul are `last_page`, deci paginarea se opreste singura. Plafonul ramane
# ca plasa impotriva unui `last_page` absurd sau lipsa.
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
    """Pretul ca float + moneda normalizata ("lei" -> RON).

    LJ-1: API-ul coteaza preturile cu doua zecimale, ca string ("800.00"). Varianta
    veche stergea TOT ce nu era cifra, deci "800.00" devenea 80000 — de o suta de ori
    prea mult, iar `_post_filter` arunca apoi fiecare anunt. Aici separatorul zecimal
    (`.` sau `,` urmat de 1-2 cifre la final) se pastreaza, iar separatorul de mii
    ("1.300") ramane tratat ca inainte, fiindca are trei cifre dupa el.
    """
    cur = "EUR" if str(currency or "").strip().lower() in ("euro", "eur", "€") else "RON"
    if price is None:
        return None, cur
    brut = re.sub(r"[^\d.,]", "", str(price))
    if not brut:
        return None, cur
    zecimal = re.search(r"[.,](\d{1,2})$", brut)
    if zecimal:
        intreg = re.sub(r"[^\d]", "", brut[:zecimal.start()]) or "0"
        text = f"{intreg}.{zecimal.group(1)}"
    else:
        text = re.sub(r"[^\d]", "", brut)
    if not text:
        return None, cur
    try:
        return float(text), cur
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
            # Tacut pana la LJ-1: cand site-ul schimba forma paginii de anunt,
            # enrichment-ul returna {"images": [], "description": None} fara niciun
            # semnal, deci degradarea era invizibila in jurnal.
            log_manager.emit("radar", "WARN",
                             "LaJumate: __NEXT_DATA__ lipseste din pagina (site schimbat?)")
            return {}
        import json
        data = json.loads(raw)
        return (data.get("props") or {}).get("pageProps") or {}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"LaJumate: __NEXT_DATA__ parse esuat: {str(exc)[:100]}")
        return {}


def _request(url: str, retry_blocked: bool = True,
             extra_headers: Optional[dict] = None) -> Optional[str]:
    """Poarta UNICA de retea a scraperului: si cautarea pe API, si detaliile pe HTML.

    `extra_headers` doar se adauga peste setul comun (LJ-1: `Accept`/`Origin` pentru
    API). Restul — bucla de retry, clasificarea, `report_outcome`, `retry_blocked`,
    backoff-urile — ramane neschimbat, ca toata cablarea NET-5 sa treaca prin acelasi
    loc indiferent de canal.
    """
    headers = build_headers({"Referer": _BASE + "/", **(extra_headers or {})})
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
    req_kwargs.update(binding.curl_kwargs("lajumate"))
    for attempt in range(3):
        try:
            resp = curl_requests.get(url, **req_kwargs)
            body = resp.text or ""
            # NET-5.3b — clasificam O SINGURA DATA, inaintea ramurilor pe status, si
            # tratam BLOCKED uniform indiferent care status l-a produs: 401, 403 SI
            # 200-cu-marker. Prin _request trece si cautarea, si enrichment-ul.
            outcome = classify(status=resp.status_code, body=body)
            if outcome is Outcome.BLOCKED:
                if report_outcome("lajumate", outcome):
                    # IP nou: reincearca IMEDIAT, fara backoff. `continue` CONSUMA
                    # incercarea — fara asta bucla ar putea deveni infinita cand
                    # rotatia reuseste de fiecare data.
                    log_manager.emit("radar", "WARN", f"LaJumate: blocat (HTTP {resp.status_code}) - IP nou, reiau {attempt+1}/3")
                    continue
                if not retry_blocked:
                    # Calea de detalii e single-shot pe blocaj (oglinda cu
                    # fetch_mobilede_listing_details): un blocaj e persistent, iar
                    # backoff-ul l-ar plati FIECARE item din enrichment — minute de
                    # sleep si WARN-uri triple per pagina (audit NET-5.3c).
                    log_manager.emit("radar", "WARN", f"LaJumate: blocat (HTTP {resp.status_code}) - fara reincercare pe calea de detalii")
                    return None
                delay = rate_limit_backoff(attempt)
                log_manager.emit("radar", "WARN", f"LaJumate: blocat (HTTP {resp.status_code}) retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            report_outcome("lajumate", outcome)
            if resp.status_code == 200:
                return body
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt)
                log_manager.emit("radar", "WARN", f"LaJumate: 429 rate-limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            # NOT_FOUND si statusurile necunoscute: comportamentul actual, nu-l largi.
            if resp.status_code == 404:
                return None
            log_manager.emit("radar", "WARN", f"LaJumate: HTTP {resp.status_code} pentru {url}")
            return None
        except Exception as exc:
            report_outcome("lajumate", classify(exc=exc))
            log_manager.emit("radar", "WARN", f"LaJumate: eroare fetch ({attempt+1}/3): {str(exc)[:100]}")
            time.sleep(rate_limit_backoff(attempt))
    return None


def _build_query(keyword, max_price, min_price, condition, judet, category) -> str:
    """Query-ul API-ului. Pagina NU intra aici — ea sta in path (/listing/{N}).

    Ordinea cheilor e cea din captura browserului. Parantezele se encodeaza
    (`filters%5Bname%5D%5B0%5D`); API-ul le accepta asa, browserul le trimite la fel.
    `oras` ramane nefolosit — API-ul filtreaza pe judet, nu pe localitate.
    """
    params = {"filters[name][0]": keyword}
    if min_price and min_price > 0:
        params["filters[price_min][0]"] = int(min_price)
    if max_price and max_price > 0:
        params["filters[price_max][0]"] = int(max_price)
    cond = _condition_param(condition)
    if cond:
        params["filters[condition][0]"] = cond
    county = _county_slug(judet)
    if county:
        params["filters[county][0]"] = county
    # Categoria noastra e slug-ul `principala/subcategorie`. API-ul o cere despartita:
    # subcategoria e optionala, `parent_id` singur filtreaza pe intreaga categorie mare.
    parti = [p for p in (category or "").strip("/").split("/") if p]
    if parti:
        params["parent_id"] = parti[0]
        if len(parti) > 1:
            params["category_id"] = parti[1]
    params["sort"] = "date_desc"
    # `currency` spune in ce moneda se citesc pragurile de pret, NU in ce moneda vin
    # preturile inapoi (raspunsul e mereu in lei). Pragurile noastre sunt in RON.
    params["currency"] = "lei"
    return urllib.parse.urlencode(params)


def _fetch_page(url: str) -> tuple[list[dict], dict]:
    """(anunturi mapate, metadate de paginare) de pe o pagina de API.

    Metadatele sunt `current_page`/`last_page`/`total`, tolerant cu `.get`. Orice
    esec (retea, corp non-JSON, `data` care nu e lista) da ([], {}) — apelantul
    trateaza lipsa la fel ca sfarsitul paginarii.
    """
    body = _request(url, extra_headers=_API_HEADERS)
    if not body:
        return [], {}
    import json
    try:
        payload = json.loads(body)
    except Exception:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        log_manager.emit("radar", "WARN", "LaJumate: raspuns API neasteptat (fara 'data')")
        return [], {}
    mapped = []
    for ad in payload["data"]:
        try:
            m = _map_ad(ad)
            if m:
                mapped.append(m)
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"LaJumate: ad invalid ignorat: {str(exc)[:80]}")
    meta = {
        "current_page": payload.get("current_page"),
        "last_page": payload.get("last_page"),
        "total": payload.get("total"),
    }
    return mapped, meta


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


def fetch_lajumate_listing_details(url: str) -> dict:
    """Pagina individuala anunt -> descriere completa + toate imaginile, din
    props.pageProps.adData (__NEXT_DATA__). {"images": [...], "description": str|None}.
    Oferita pentru vizualizarea detaliata din app (paritate cu fetch_olx_listing_details).
    """
    if not url:
        return {"images": [], "description": None}
    html = _request(url, retry_blocked=False)
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


def _enrich_details(results: list[dict], skip_external_ids: Optional[set] = None) -> tuple[int, int]:
    """Imbogateste fiecare rezultat cu toate imaginile + descrierea completa din
    pagina individuala a anuntului (adData), secvential cu delay aleator — la fel ca
    OLX/Publi24/Okazii. Modifica lista pe loc; esecul unui anunt nu opreste restul.
    RP-3: imbogateste DOAR itemele care nu sunt in skip_external_ids (anunturi deja
    vazute de scanner). Returneaza (fetched, skipped)."""
    fetched = 0
    skipped = 0
    for item in results:
        if skip_external_ids and item.get("external_id") in skip_external_ids:
            skipped += 1
            continue
        if fetched > 0:
            time.sleep(random.uniform(0.4, 0.8))
        fetched += 1
        try:
            details = fetch_lajumate_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"LaJumate details {item['external_id']}: {str(exc)[:100]}")
            continue
    if skipped > 0:
        log_manager.emit("radar", "INFO", f"LaJumate: enrichment {fetched} noi · {skipped} sărite (deja văzute)")
    return fetched, skipped


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
    skip_enrich_ids: Optional[set] = None,
) -> list[dict]:
    """Cauta pe LaJumate; returneaza listinguri in format standard.

    Canal UNIC: API-ul JSON public, cu pretul, categoria, starea si judetul filtrate
    SERVER-SIDE. Nu mai exista fallback pe pagina de categorie: categoria e acum un
    filtru care se combina cu keyword-ul in aceeasi cerere, deci canalul de rezerva
    (cu filtrarea lui locala pe keyword) n-ar mai avea ce sa adauge.

    Paginarea se opreste la `last_page` din raspuns; `_LAJUMATE_MAX_PAGES` ramane garda.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if page > _LAJUMATE_MAX_PAGES:
        return []

    query = _build_query(keyword_clean, max_price, min_price, condition, judet, category)
    url = f"{_API_BASE}/listing/{page}?{query}"
    log_manager.emit("radar", "SCAN", f'LaJumate "{keyword_clean}" (pag {page})')

    results, meta = _fetch_page(url)
    last_page = meta.get("last_page")
    current_page = meta.get("current_page")
    peste_ultima = (isinstance(current_page, int) and isinstance(last_page, int)
                    and current_page > last_page)
    if not results or peste_ultima:
        # Sfarsit normal de paginare, nu defect: INFO, nu WARN. (Un esec de retea a
        # emis deja WARN-ul lui in `_request`/`_fetch_page`.)
        log_manager.emit("radar", "INFO",
                         f'LaJumate: pagina {page} peste ultima ({last_page}) pentru "{keyword_clean}"')
        return []

    # Plasa locala: API-ul filtreaza corect, dar un pret neparsabil sau un cuvant
    # exclus tot trebuie sa cada, iar excluderile n-au echivalent server-side.
    results = _post_filter(results, max_price, min_price, exclude_words)
    _enrich_details(results, skip_enrich_ids)
    log_manager.emit("radar", "OK",
                     f'LaJumate: {len(results)} rezultate pentru "{keyword_clean}" '
                     f'(pag {page}/{last_page} · total {meta.get("total")})')
    return results
