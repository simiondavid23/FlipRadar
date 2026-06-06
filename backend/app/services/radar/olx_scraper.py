"""Scraper pentru OLX.ro.

Foloseste curl_cffi cu impersonate=chrome110 ca sa treaca peste WAF-ul Cloudflare
care blocheaza requests-ul standard. Daca primim 429, aplicam backoff exponential
si reincercam de maxim 3 ori inainte sa renuntam.
"""
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config
from app.services.radar.categories import OLX_CATEGORY_SLUGS


_IMPERSONATE = "chrome110"


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
        src = img.get("data-src") or img.get("src") or ""
        if "apollo.olxcdn.com" not in src:
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


def search_olx(
    keyword: str,
    max_price: float,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Cauta pe OLX dupa keyword si returneaza listinguri in format standard."""
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []

    q = urllib.parse.quote(keyword_clean)
    judet_slug = _normalize_judet(judet)
    category_slug = OLX_CATEGORY_SLUGS.get(category) if category else None

    # Path-ul OLX: /[judet]/[categorie]/oferte/q-<keyword>/
    parts = []
    if judet_slug:
        parts.append(judet_slug)
    if category_slug:
        parts.append(category_slug)
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

    results = []
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
            image_url = img_tag.get("src") if img_tag else None
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

            results.append({
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

    print(f"[OlxScraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
