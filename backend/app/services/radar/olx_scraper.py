"""Scraper pentru OLX.ro.

Foloseste curl_cffi cu impersonate=chrome110 ca sa treaca peste WAF-ul Cloudflare
care blocheaza requests-ul standard. Daca primim 429, aplicam backoff exponential
si reincercam de maxim 3 ori inainte sa renuntam.
"""
import json
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config


_IMPERSONATE = "chrome110"

# OLX nu afiseaza mai mult de ~5 pagini utile per query; peste asta apar 404-uri
# (paginare depasita). Cap hard ca sa nu paginam la nesfarsit / sa nu crape scanul.
_OLX_MAX_PAGES = 5


# Maparea simpla judet -> slug folosit in URL-ul OLX. Acopera judetele
# cele mai cautate; pentru restul cadem inapoi pe cautarea fara filtru.
_JUDET_SLUGS = {
    "bucuresti": "bucuresti-ilfov",
    "ilfov": "bucuresti-ilfov",
    "cluj": "cluj",
    "timis": "timis",
    "iasi": "iasi",
    "brasov": "brasov",
    "constanta": "constanta",
    "dolj": "dolj",
    "galati": "galati",
    "bihor": "bihor",
    "arges": "arges",
    "prahova": "prahova",
    "sibiu": "sibiu",
    "mures": "mures",
    "bacau": "bacau",
    "suceava": "suceava",
    "neamt": "neamt",
    "maramures": "maramures",
}


# MODIFICARE 5 — maparea numelui de afisare al categoriei (din MARKETPLACE_CATEGORIES.olx)
# la slug-ul de path OLX. keyword.category stocheaza numele de afisare, nu slug-ul.
OLX_CATEGORY_SLUGS = {
    "Electronice si electrocasnice": "electronice-si-electrocasnice",
    "Moda si frumusete": "moda-si-frumusete",
    "Piese auto": "piese-auto-moto-si-ambarcatiuni",
    "Casa si gradina": "casa-si-gradina",
    "Mama si copilul": "mama-si-copilul",
    "Sport, timp liber, arta": "sport-timp-liber-si-arta",
    "Animale de companie": "animale-de-companie",
    "Agro si industrie": "agro-si-industrie",
    "Servicii": "servicii",
    "Echipamente profesionale si vanzare companii": "echipamente-profesionale-si-vanzare-companii",
    "Cazare - Turism": "cazare-si-turism",
    "Inchiriere bunuri si vehicule": "inchiriere-bunuri-si-vehicule",
}


def _olx_category_slug(category: Optional[str]) -> Optional[str]:
    """Traduce numele categoriei la slug OLX. Daca nu e in mapping dar arata deja
    ca un slug (fara spatii), il pastreaza; altfel None (cautare generala)."""
    if not category:
        return None
    cat = category.strip()
    slug = OLX_CATEGORY_SLUGS.get(cat)
    if slug:
        return slug
    # Compat: daca vine deja un slug (fara spatii), foloseste-l ca atare.
    if " " not in cat:
        return cat.strip("/") or None
    return None


def _normalize_judet(judet: Optional[str]) -> Optional[str]:
    if not judet:
        return None
    key = judet.strip().lower()
    key = key.replace("ă", "a").replace("â", "a").replace("î", "i").replace("ș", "s").replace("ț", "t")
    return _JUDET_SLUGS.get(key)


def _parse_price(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.,]", "", raw).replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_condition(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip().lower()
    if "nou" in t:
        return "nou"
    if "folosit" in t or "second" in t:
        return "second hand"
    return None


_OLX_RO_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
    "ian": 1, "feb": 2, "mar": 3, "apr": 4,
    "iun": 6, "iul": 7, "aug": 8, "sep": 9, "oct": 10, "noi": 11, "dec": 12,
}


def _parse_olx_date(raw: Optional[str]) -> Optional[datetime]:
    """OLX afiseaza "Azi la HH:MM", "Ieri la HH:MM" sau "dd lun yyyy"."""
    if not raw:
        return None
    t = raw.strip().lower()
    # Cazul cu locatie + data — separam dupa "-"
    if "-" in t:
        t = t.split("-")[-1].strip()
    now = datetime.now()
    m_time = re.search(r"(\d{1,2}):(\d{2})", t)
    hour = int(m_time.group(1)) if m_time else 0
    minute = int(m_time.group(2)) if m_time else 0
    if t.startswith("azi"):
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t.startswith("ieri"):
        d = now - timedelta(days=1)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Format complet: 23 octombrie 2025 sau 23 oct 2025
    m = re.search(r"(\d{1,2})\s+([a-zăâîșț]+)\s+(\d{4})", t)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).replace("ă", "a").replace("â", "a").replace("î", "i").replace("ș", "s").replace("ț", "t")
        month = _OLX_RO_MONTHS.get(month_name)
        year = int(m.group(3))
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
    return None


def _upgrade_image_url(url: str) -> str:
    """OLX serveste thumbnails prin ;s=WxH — il urcam la 1000x1000 pentru a obtine
    versiunea de calitate maxima fara a sparge URL-ul.
    """
    if not url:
        return url
    upgraded = re.sub(r";s=\d+x\d+", ";s=1000x1000", url)
    return upgraded


def fetch_olx_listing_details(url: str) -> dict:
    """Descarca pagina de detalii a unui anunt OLX si extrage imaginile la calitate
    maxima + descrierea vânzătorului. Returneaza {"images": [...], "description": str}.
    La orice eroare returneaza {"images": [], "description": None} — caller-ul
    cade pe datele din pagina de search.
    """
    if not url:
        return {"images": [], "description": None}
    headers = build_headers({"Referer": "https://www.olx.ro/"})
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
    try:
        resp = curl_requests.get(url, **req_kwargs)
        if resp.status_code != 200:
            return {"images": [], "description": None}
        html = resp.text
    except Exception as exc:
        print(f"[OlxScraper] details fetch eroare: {exc}")
        return {"images": [], "description": None}

    soup = BeautifulSoup(html, "html.parser")

    # Imagini din galeria detaliilor
    imgs = []
    seen = set()
    for img in soup.select("img"):
        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("srcset", "").split(" ")[0]
            or img.get("src")
            or ""
        )
        if not src or src.startswith("data:"):
            continue
        if "olxcdn.com" not in src and "olx-cdn.com" not in src:
            continue
        upgraded = _upgrade_image_url(src)
        if upgraded in seen:
            continue
        seen.add(upgraded)
        imgs.append(upgraded)

    # Descriere
    desc_el = (
        soup.find(attrs={"data-testid": "ad-description"})
        or soup.find(attrs={"data-cy": "ad_description"})
        or soup.select_one("div.css-bgzo2k")
        or soup.select_one("div[data-cy='ad-description']")
    )
    description = None
    if desc_el:
        text = desc_el.get_text("\n", strip=True)
        description = text if text else None

    return {"images": imgs, "description": description}


def _extract_external_id(url: str) -> Optional[str]:
    if not url:
        return None
    # OLX foloseste slug-uri terminate in -ID<XXX>.html
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", url)
    if m:
        return f"olx_{m.group(1)}"
    # Fallback: foloseste path-ul ca id (stabil pentru acelasi anunt)
    parsed = urllib.parse.urlparse(url)
    return f"olx_{parsed.path.strip('/').replace('/', '_')[-50:]}"


def _fetch_detail_image(url: str) -> Optional[str]:
    """Acceseaza pagina individuala a anuntului si extrage prima imagine."""
    try:
        resp = curl_requests.get(
            url,
            headers=build_headers({"Referer": "https://www.olx.ro/"}),
            impersonate=_IMPERSONATE,
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        selectors = [
            'img[data-cy="ad-photo"]',
            '[data-testid="image-gallery-image"]',
            '.swiper-slide img',
            '[data-cy="adPhotos-swiperSlide"] img',
            'img[class*="Photo"]',
        ]
        for sel in selectors:
            img = soup.select_one(sel)
            if img:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy") or ""
                if src.startswith("http") and "olxcdn" in src:
                    return src
        return None
    except Exception as exc:
        print(f"[OlxScraper] _fetch_detail_image error: {exc}")
        return None


def _extract_olx_categories(html: str) -> dict:
    """Extrage {href_id -> category_id} din window.__PRERENDERED_STATE__ (Apollo).

    OLX NU foloseste __NEXT_DATA__; ad-urile sunt in state.listing.listing.ads[],
    fiecare cu category:{id:<numeric>}. Cheia e ID-ul din url (`-ID<xxx>.html`) ca
    sa se potriveasca cu external_id-ul cardului. Fara request extra per listing.
    Dict gol la orice esec (safe default → nu se exclude nimic).
    """
    try:
        import json
        m = re.search(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', html, re.DOTALL)
        if not m:
            return {}
        state = json.loads(json.loads(m.group(1)))  # dublu-decode (string JSON escapat)
        ads = (state.get("listing") or {}).get("listing", {}).get("ads") or []
        result: dict = {}
        for ad in ads:
            cat = ad.get("category")
            cat_id = cat.get("id") if isinstance(cat, dict) else None
            url = ad.get("url") or ad.get("urlPath") or ""
            mm = re.search(r"-ID([A-Za-z0-9]+)\.html", url)
            if mm and cat_id is not None:
                result[mm.group(1)] = str(cat_id)
        return result
    except Exception as e:
        print(f"[OlxScraper] __PRERENDERED_STATE__ parse error: {e}")
        return {}


def _extract_olx_numeric_ids(html: str) -> dict:
    """{token_external_id -> id_numeric} din window.__PRERENDERED_STATE__.ads[] (S2).

    Necesare pentru /api/v1/offers/{id_numeric}: cardul are doar `-ID<token>.html`,
    dar API-ul cere id-ul numeric, prezent in state langa url. Dict gol la esec.
    """
    try:
        m = re.search(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', html, re.DOTALL)
        if not m:
            return {}
        state = json.loads(json.loads(m.group(1)))
        ads = (state.get("listing") or {}).get("listing", {}).get("ads") or []
        result: dict = {}
        for ad in ads:
            aid = ad.get("id")
            url = ad.get("url") or ad.get("urlPath") or ""
            mm = re.search(r"-ID([A-Za-z0-9]+)\.html", url)
            if mm and aid is not None:
                result[mm.group(1)] = aid
        return result
    except Exception as e:
        print(f"[OlxScraper] __PRERENDERED_STATE__ numeric-id parse error: {e}")
        return {}


def _parse_iso_dt(s) -> Optional[datetime]:
    """ISO 8601 cu offset ('2026-07-07T12:08:09+03:00') -> datetime NAIV local
    (consecvent cu conventia listed_at a scraperelor)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def fetch_olx_offer_details(numeric_id) -> dict:
    """GET https://www.olx.ro/api/v1/offers/{id} -> date vanzator + data postarii.

    Confirmat RP-DIAG (§5): `data.user.name`, `data.user.created` (an), `data.created_time`,
    `data.description`. Returneaza dict cu cheile disponibile (seller_name, seller_id,
    olx_member_since, listed_at, description) sau {} la orice esec (caller pastreaza ce are).
    """
    if not numeric_id:
        return {}
    url = f"https://www.olx.ro/api/v1/offers/{numeric_id}"
    try:
        resp = curl_requests.get(
            url,
            headers=build_headers({
                "Referer": "https://www.olx.ro/",
                "Accept": "application/json, text/plain, */*",
            }),
            impersonate=_IMPERSONATE, timeout=20,
        )
        if resp.status_code != 200:
            return {}
        data = (resp.json() or {}).get("data") or {}
    except Exception as exc:
        print(f"[OlxScraper] offer details eroare ({numeric_id}): {exc}")
        return {}
    return _map_olx_offer(data)


def _map_olx_offer(data: dict) -> dict:
    """Mapeaza `data` din /api/v1/offers/{id} la campurile noastre (functie PURA,
    testabila pe fixture): seller_name/seller_id/olx_member_since/listed_at/description."""
    out: dict = {}
    if not isinstance(data, dict):
        return out
    user = data.get("user") or {}
    if user.get("name"):
        out["seller_name"] = user.get("name")
    if user.get("id") is not None:
        out["seller_id"] = str(user.get("id"))
    created = user.get("created")
    if created:
        mm = re.match(r"(\d{4})", str(created))
        if mm:
            out["olx_member_since"] = int(mm.group(1))
    dt = _parse_iso_dt(data.get("created_time"))
    if dt:
        out["listed_at"] = dt
    desc = data.get("description")
    if desc:
        txt = re.sub(r"<[^>]+>", " ", str(desc))
        txt = re.sub(r"\s+", " ", txt).strip()
        out["description"] = txt or None
    return out


def fetch_olx_seller_rating(seller_id) -> dict:
    """Rating public al vanzatorului OLX, FARA auth (confirmat RP-DIAG-2). Doua GET-uri:
      1. /api/v1/users/{seller_id}/  -> data.uuid;
      2. rating-cdn.css.olx.io/ratings/v1/public/olxro/user/{uuid}/eligibleClusters
         ?includeScores=true  -> _map_olx_rating.
    Returneaza {seller_rating, seller_reviews} (doar cheile prezente) sau {} la orice
    status != 200 / lipsa uuid / exceptie (caller pastreaza ce are). Fara cookie/Origin
    (build_headers nu le adauga); fara retry agresiv."""
    if not seller_id:
        return {}
    hdrs = build_headers({
        "Referer": "https://www.olx.ro/",
        "Accept": "application/json, text/plain, */*",
    })
    try:
        ru = curl_requests.get(
            f"https://www.olx.ro/api/v1/users/{seller_id}/",
            headers=hdrs, impersonate=_IMPERSONATE, timeout=20,
        )
        if ru.status_code != 200:
            return {}
        uuid = ((ru.json() or {}).get("data") or {}).get("uuid")
        if not uuid:
            return {}
        rr = curl_requests.get(
            f"https://rating-cdn.css.olx.io/ratings/v1/public/olxro/user/{uuid}/eligibleClusters?includeScores=true",
            headers=hdrs, impersonate=_IMPERSONATE, timeout=20,
        )
        if rr.status_code != 200:
            return {}
        clusters = rr.json() or {}
    except Exception as exc:
        print(f"[OlxScraper] seller rating eroare ({seller_id}): {exc}")
        return {}
    return _map_olx_rating(clusters)


def _map_olx_rating(clusters: dict) -> dict:
    """Mapeaza raspunsul eligibleClusters (rating-cdn) la campurile noastre (functie
    PURA, testabila pe fixture): seller_rating/seller_reviews.

    Forma reala (RP-DIAG-2): clusters[0].scoreDetails.value (media stelelor 0-5) si
    clusters[0].scoreDetails.ratings.totalCount (nr. recenzii). Toleranta la structura
    lipsa/None -> {} (un camp absent se omite, nu se inventeaza 0)."""
    out: dict = {}
    if not isinstance(clusters, dict):
        return out
    lst = clusters.get("clusters")
    if not isinstance(lst, list) or not lst:
        return out
    first = lst[0]
    if not isinstance(first, dict):
        return out
    score = first.get("scoreDetails")
    if not isinstance(score, dict):
        return out
    value = score.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        out["seller_rating"] = float(value)
    ratings = score.get("ratings")
    if isinstance(ratings, dict):
        total = ratings.get("totalCount")
        if isinstance(total, int) and not isinstance(total, bool):
            out["seller_reviews"] = total
    return out


def search_olx(
    keyword: str,
    max_price: float,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
    exclude_description_words: Optional[list] = None,
    page: int = 1,
) -> list[dict]:
    """Cauta pe OLX dupa keyword si returneaza listinguri in format standard.

    `page` (>=1) adauga ?page=N la cererea OLX; scanner-ul pagineaza pana cand o
    pagina nu mai aduce anunturi noi.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []

    # FIX paginare — peste limita hard nu mai cerem nimic de la OLX (evita 404-urile
    # de paginare depasita si opreste bucla de paginare din scanner).
    if page > _OLX_MAX_PAGES:
        return []

    q = urllib.parse.quote(keyword_clean)
    judet_slug = _normalize_judet(judet)
    # MODIFICARE 5 — mapam numele categoriei la slug OLX (None => cautare generala).
    category_path = _olx_category_slug(category)

    def _fetch_and_parse(cat_path: Optional[str]) -> list[dict]:
        # Path-ul OLX: /[judet]/[categorie]/oferte/q-<keyword>/
        parts = []
        if judet_slug:
            parts.append(judet_slug)
        if cat_path:
            parts.append(cat_path)
        parts.append("oferte")
        parts.append(f"q-{q}")
        base_url = "https://www.olx.ro/" + "/".join(parts) + "/"

        params = {}
        if max_price and max_price > 0:
            params["search[filter_float_price:to]"] = int(max_price)
        if min_price and min_price > 0:
            params["search[filter_float_price:from]"] = int(min_price)
        if condition and condition != "all":
            # OLX foloseste filter_enum_state cu valoarea "new" sau "used"
            params["search[filter_enum_state][0]"] = "new" if condition == "new" else "used"
        if page > 1:
            params["page"] = page

        if params:
            url = base_url + "?" + urllib.parse.urlencode(params)
        else:
            url = base_url

        headers = build_headers({"Referer": "https://www.olx.ro/"})
        proxy_cfg = get_proxy_config()
        request_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
        if proxy_cfg:
            request_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}

        html = None
        for attempt in range(3):
            try:
                resp = curl_requests.get(url, **request_kwargs)
                if resp.status_code == 200:
                    html = resp.text
                    break
                if resp.status_code == 429:
                    delay = rate_limit_backoff(attempt)
                    print(f"[OlxScraper] 429 rate limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                    time.sleep(delay)
                    continue
                # 404 = paginare depasita (pagina nu exista) -> stop curat, nu eroare.
                if resp.status_code == 404:
                    return []
                # Orice alt status non-200 opreste fetch-ul fara crash.
                print(f"[OlxScraper] HTTP {resp.status_code} pentru {url}")
                return []
            except Exception as exc:
                print(f"[OlxScraper] Eroare la fetch ({attempt+1}/3): {exc}")
                time.sleep(rate_limit_backoff(attempt))

        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('div[data-cy="l-card"]')
        if not cards:
            cards = soup.select('[data-testid="l-card"]')
        if not cards:
            cards = soup.select("div.css-1sw7q4x")

        parsed = []
        for card in cards:
            try:
                link_tag = card.find("a", href=True)
                if not link_tag:
                    continue
                href = link_tag["href"]
                if href.startswith("/"):
                    href = "https://www.olx.ro" + href

                title_tag = card.find("h4") or card.find("h6") or link_tag
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue
                if is_excluded(title, exclude_words):
                    continue

                # MODULE 1b — exclude pe descriere (din cardul de search, daca exista)
                desc_tag = (
                    card.find(attrs={"data-cy": "ad-description"})
                    or card.find(class_=re.compile(r"description|descriere|css-qijjoas", re.I))
                )
                description = desc_tag.get_text(" ", strip=True)[:500] if desc_tag else ""
                if exclude_description_words and description:
                    if is_excluded(description, exclude_description_words):
                        continue

                price_tag = card.find(attrs={"data-testid": "ad-price"}) or card.select_one("p.css-13afqrm") or card.find("p")
                price = _parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
                if price is None:
                    continue
                if max_price and price > max_price:
                    continue
                if min_price and price < min_price:
                    continue

                location_tag = card.find(attrs={"data-testid": "location-date"}) or card.select_one("p.css-1a4brun")
                location_raw = location_tag.get_text(" ", strip=True) if location_tag else None
                # OLX combina "Locatie - Data" intr-un singur element; separa-le
                location = None
                listed_at = None
                if location_raw:
                    if "-" in location_raw:
                        loc_part, _, date_part = location_raw.partition("-")
                        location = loc_part.strip()
                        listed_at = _parse_olx_date(date_part.strip())
                    else:
                        location = location_raw.strip()
                        listed_at = _parse_olx_date(location_raw)

                img_tag = card.find("img")
                image_url = None
                if img_tag:
                    image_url = (
                        img_tag.get("data-src")
                        or img_tag.get("data-lazy-src")
                        or img_tag.get("data-original")
                        or img_tag.get("srcset", "").split(" ")[0]
                        or img_tag.get("src")
                        or None
                    )
                    if image_url and image_url.startswith("data:"):
                        image_url = None
                # MODULE 3c — daca thumbnail-ul lipseste, ia prima imagine din pagina de detalii
                if not image_url:
                    time.sleep(random.uniform(0.3, 0.7))  # small delay to avoid hammering
                    image_url = _fetch_detail_image(href)
                images = [image_url] if image_url else []

                cond_tag = card.find(attrs={"data-testid": "ad-state"})
                cond = _normalize_condition(cond_tag.get_text(" ", strip=True)) if cond_tag else None
                if condition == "new" and cond != "nou":
                    continue
                if condition == "used" and cond != "second hand":
                    continue

                ext_id = _extract_external_id(href)
                if not ext_id:
                    continue

                parsed.append({
                    "external_id": ext_id,
                    "platform": "olx",
                    "title": title,
                    "price": price,
                    "currency": "RON",
                    "condition": cond,
                    "location": location,
                    "url": href,
                    "images": images,
                    "description": None,
                    "seller_name": None,
                    "seller_id": None,
                    "listed_at": listed_at,
                })
            except Exception as exc:
                print(f"[OlxScraper] Eroare la parsarea unui card: {exc}")
                continue

        # Atasam categoria OLX (ID numeric) din __PRERENDERED_STATE__, pentru
        # filtrarea pe subcategorie din scanner. Fara request extra per listing.
        cat_map = _extract_olx_categories(html)
        if cat_map:
            for item in parsed:
                hid = (item.get("external_id") or "").replace("olx_", "")
                item["olx_category"] = cat_map.get(hid, "")
        # RP-1 — id numeric pentru enrichment prin /api/v1/offers/{id} (fara request extra).
        num_map = _extract_olx_numeric_ids(html)
        if num_map:
            for item in parsed:
                hid = (item.get("external_id") or "").replace("olx_", "")
                if num_map.get(hid) is not None:
                    item["olx_numeric_id"] = num_map.get(hid)
        return parsed

    # FIX paginare — intreaga colectare + procesare e protejata: nicio exceptie
    # (404, parsing, retea) nu trebuie sa iasa din search_olx si sa opreasca scanul.
    results: list[dict] = []
    try:
        results = _fetch_and_parse(category_path)
        # Fallback: daca subcategoria completa nu da rezultate, reincearca pe categoria principala
        if len(results) == 0 and category_path and "/" in category_path:
            main_cat = category_path.split("/")[0]
            results = _fetch_and_parse(main_cat)
        # MODIFICARE 5 — daca URL-ul cu categorie nu da nimic (slug gresit / blocat),
        # cadem pe cautare generala (fara categorie) ca sa nu ramanem cu 0 anunturi.
        if len(results) == 0 and category_path:
            results = _fetch_and_parse(None)

        # Imbogateste fiecare rezultat cu imaginile la rezolutie maxima si descrierea
        # de pe pagina detaliilor. Apelurile sunt secventiale cu delay aleator pentru
        # a nu supraincarca OLX.
        for idx, item in enumerate(results):
            if idx > 0:
                time.sleep(random.uniform(0.5, 1.0))
            try:
                details = fetch_olx_listing_details(item["url"])
                if details.get("images"):
                    item["images"] = details["images"]
                elif item.get("images"):
                    item["images"] = [_upgrade_image_url(u) for u in item["images"] if u]
                if details.get("description"):
                    item["description"] = details["description"]
            except Exception as exc:
                print(f"[OlxScraper] details {item['external_id']}: {exc}")
                continue
    except Exception as e:
        # Stop curat: returnam ce s-a colectat pana acum, fara sa propagam eroarea.
        print(f"[OlxScraper] Eroare la paginare (page={page}): {e}")

    print(f"[OlxScraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
