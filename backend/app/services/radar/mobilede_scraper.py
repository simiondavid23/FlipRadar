"""Scraper pentru mobile.de — masini second-hand din Germania.

Mobile.de poate bloca rapid traficul automatizat — folosim curl_cffi cu impersonate
si delay generos intre request-uri.
"""
import random
import re
import time
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config


_IMPERSONATE = "chrome110"

_MAKE_IDS = {
    "BMW": 3500, "Mercedes-Benz": 17200, "Audi": 1900, "Volkswagen": 25200,
    "Toyota": 24100, "Ford": 9000, "Opel": 18700, "Skoda": 22900,
    "Renault": 21100, "Dacia": 5200, "Peugeot": 19800, "Seat": 22000,
    "Hyundai": 11600, "Kia": 13600, "Honda": 11000, "Mazda": 17000,
    "Nissan": 18600, "Volvo": 25400, "Porsche": 20100,
}
_FUEL_MAP = {
    "benzina": "PETROL", "benzină": "PETROL", "petrol": "PETROL",
    "diesel": "DIESEL", "motorina": "DIESEL", "motorină": "DIESEL",
    "hibrid": "HYBRID", "hybrid": "HYBRID",
    "electric": "ELECTRICITY",
    "gpl": "LPG", "lpg": "LPG",
    "gnc": "CNG", "cng": "CNG",
}
_GEARBOX_MAP = {
    "manuala": "MANUAL_GEAR", "manuală": "MANUAL_GEAR", "manual": "MANUAL_GEAR",
    "automata": "AUTOMATIC_GEAR", "automată": "AUTOMATIC_GEAR", "automatic": "AUTOMATIC_GEAR",
    "automat": "AUTOMATIC_GEAR",
}


def _parse_price(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.,]", "", raw).replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_external_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/(\d{8,})(?:[?.]|$)", url)
    if m:
        return f"mobilede_{m.group(1)}"
    parsed = urllib.parse.urlparse(url)
    return f"mobilede_{parsed.path.strip('/').replace('/', '_')[-50:]}"


def _norm(d: dict, key: str, mapping: dict) -> Optional[str]:
    val = d.get(key) if d else None
    if not val:
        return None
    return mapping.get(str(val).strip().lower())


def build_mobilede_url(
    keyword: str,
    max_price: Optional[float],
    min_price: Optional[float],
    car_filters: Optional[dict],
) -> str:
    base = "https://suchen.mobile.de/fahrzeuge/search.html"
    params = {
        "lang": "ro",
        "isSearchRequest": "true",
    }
    if keyword and keyword.strip():
        params["q"] = keyword.strip()
    if max_price and max_price > 0:
        params["maxPrice"] = int(max_price)
    if min_price and min_price > 0:
        params["minPrice"] = int(min_price)
    if car_filters:
        marca = (car_filters.get("marca") or "").strip()
        if marca and marca in _MAKE_IDS:
            params["makeModelVariant1.makeId"] = _MAKE_IDS[marca]
        if car_filters.get("an_de_la"):
            params["minFirstRegistrationDate"] = f"{int(car_filters['an_de_la'])}-01"
        if car_filters.get("an_pana_la"):
            params["maxFirstRegistrationDate"] = f"{int(car_filters['an_pana_la'])}-12"
        if car_filters.get("km_maxim"):
            params["maxMileage"] = int(car_filters["km_maxim"])
        fuel = _norm(car_filters, "combustibil", _FUEL_MAP)
        if fuel:
            params["fuel"] = fuel
        gearbox = _norm(car_filters, "cutie_viteze", _GEARBOX_MAP)
        if gearbox:
            params["transmission"] = gearbox

    return base + "?" + urllib.parse.urlencode(params)


def fetch_mobilede_listing_details(url: str) -> dict:
    if not url:
        return {"images": [], "description": None, "specs": {}}
    headers = build_headers({
        "Referer": "https://www.mobile.de/",
        "Accept-Language": "ro-RO,ro;q=0.9,de;q=0.8,en;q=0.7",
    })
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
    try:
        resp = curl_requests.get(url, **req_kwargs)
        if resp.status_code != 200:
            return {"images": [], "description": None, "specs": {}}
        html = resp.text
    except Exception as exc:
        print(f"[MobileDeScraper] details eroare: {exc}")
        return {"images": [], "description": None, "specs": {}}

    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    seen = set()
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if "mobile.de" in src or "mobile-static" in src:
            if src not in seen:
                seen.add(src)
                imgs.append(src)
    description = None
    desc_el = (
        soup.find(attrs={"data-testid": "vip-description-text"})
        or soup.find(class_=re.compile(r"description|beschreibung|descriere", re.I))
    )
    if desc_el:
        description = desc_el.get_text("\n", strip=True) or None
    specs = {}
    for row in soup.select("dl, table"):
        for dt, dd in zip(row.select("dt, th"), row.select("dd, td")):
            k = dt.get_text(" ", strip=True)
            v = dd.get_text(" ", strip=True)
            if k and v:
                specs[k] = v
    return {"images": imgs, "description": description, "specs": specs}


def search_mobilede(
    keyword: str,
    max_price: Optional[float],
    min_price: Optional[float] = None,
    exclude_words: Optional[list[str]] = None,
    car_filters: Optional[dict] = None,
) -> list[dict]:
    exclude_words = exclude_words or []
    url = build_mobilede_url(keyword, max_price, min_price, car_filters)

    headers = build_headers({
        "Referer": "https://www.mobile.de/",
        "Accept-Language": "ro-RO,ro;q=0.9,de;q=0.8,en;q=0.7",
    })
    proxy_cfg = get_proxy_config()
    req_kwargs = {"headers": headers, "impersonate": _IMPERSONATE, "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}

    html = None
    for attempt in range(3):
        try:
            resp = curl_requests.get(url, **req_kwargs)
            if resp.status_code == 200:
                html = resp.text
                break
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt, base_delay=3.0)
                print(f"[MobileDeScraper] 429 retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            print(f"[MobileDeScraper] HTTP {resp.status_code}")
            return []
        except Exception as exc:
            print(f"[MobileDeScraper] Eroare ({attempt+1}/3): {exc}")
            time.sleep(rate_limit_backoff(attempt, base_delay=3.0))

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select("[data-testid='result-listing']")
        or soup.select("article")
        or soup.select("[data-listing-id]")
    )

    results = []
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = "https://www.mobile.de" + href

            title_tag = card.find(["h2", "h3"]) or link_tag
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_tag = card.find(class_=re.compile(r"price", re.I))
            price = _parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if price is None:
                continue
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue

            location_tag = card.find(class_=re.compile(r"location|city", re.I))
            location = location_tag.get_text(" ", strip=True) if location_tag else None

            img_tag = card.find("img")
            image_url = (img_tag.get("data-src") or img_tag.get("src")) if img_tag else None
            images = [image_url] if image_url else []

            specs_text = card.get_text(" ", strip=True)
            year_m = re.search(r"\b(19|20)\d{2}\b", specs_text)
            km_m = re.search(r"([\d.\s]+)\s*km\b", specs_text, re.I)
            year = int(year_m.group(0)) if year_m else None
            mileage = None
            if km_m:
                try:
                    mileage = int(re.sub(r"[^\d]", "", km_m.group(1)))
                except ValueError:
                    mileage = None

            ext_id = _extract_external_id(href)
            if not ext_id:
                continue

            results.append({
                "external_id": ext_id,
                "platform": "mobilede",
                "title": title,
                "price": price,
                "currency": "EUR",
                "condition": None,
                "location": location,
                "url": href,
                "images": images,
                "description": None,
                "seller_name": None,
                "seller_id": None,
                "listed_at": None,
                "year": year,
                "mileage": mileage,
            })
        except Exception as exc:
            print(f"[MobileDeScraper] card eroare: {exc}")
            continue

    for idx, item in enumerate(results):
        if idx > 0:
            time.sleep(random.uniform(1.5, 3.0))
        try:
            details = fetch_mobilede_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
            if details.get("specs"):
                item.setdefault("specs", {}).update(details["specs"])
        except Exception as exc:
            print(f"[MobileDeScraper] details {item['external_id']}: {exc}")
            continue

    print(f"[MobileDeScraper] {len(results)} rezultate pentru '{keyword}'")
    return results
