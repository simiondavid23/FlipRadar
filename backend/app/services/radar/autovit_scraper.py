"""Scraper pentru autovit.ro (parte din grupul OLX).

Structura HTML e similara cu OLX. Filtrele auto se trimit ca query params
de tip `search[filter_*]`. Pentru anunturile gasite imbogatim cu fetch de
pagina detalii (imagini hi-res + descriere + specs cheie).
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

_FUEL_MAP = {
    "benzina": "petrol", "benzină": "petrol", "petrol": "petrol",
    "diesel": "diesel", "motorina": "diesel", "motorină": "diesel",
    "hibrid": "hybrid", "hybrid": "hybrid",
    "electric": "electric",
    "gpl": "lpg", "lpg": "lpg",
    "gnc": "cng", "cng": "cng",
}
_BODY_MAP = {
    "sedan": "sedan", "berlina": "sedan", "berlină": "sedan",
    "suv": "suv",
    "break": "combi", "combi": "combi", "estate": "combi",
    "hatchback": "hatchback",
    "coupe": "coupe",
    "cabrio": "cabrio", "decapotabila": "cabrio", "decapotabilă": "cabrio",
    "van": "van",
    "pickup": "pickup",
}
_GEARBOX_MAP = {
    "manuala": "manual", "manuală": "manual", "manual": "manual",
    "automata": "automatic", "automată": "automatic", "automatic": "automatic",
    "automat": "automatic",
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
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", url)
    if m:
        return f"autovit_{m.group(1)}"
    parsed = urllib.parse.urlparse(url)
    return f"autovit_{parsed.path.strip('/').replace('/', '_')[-50:]}"


def _norm(d: dict, key: str, mapping: dict) -> Optional[str]:
    val = d.get(key) if d else None
    if not val:
        return None
    return mapping.get(str(val).strip().lower())


def build_autovit_url(
    keyword: str,
    max_price: Optional[float],
    min_price: Optional[float],
    car_filters: Optional[dict],
) -> str:
    base = "https://www.autovit.ro/autoturisme"
    q = urllib.parse.quote((keyword or "").strip())
    params = {}
    if q:
        params["search[filter_str_q]"] = (keyword or "").strip()
    if max_price and max_price > 0:
        params["search[filter_float_price:to]"] = int(max_price)
    if min_price and min_price > 0:
        params["search[filter_float_price:from]"] = int(min_price)
    if car_filters:
        marca = (car_filters.get("marca") or "").strip().lower()
        model = (car_filters.get("model") or "").strip().lower()
        if marca:
            params["search[filter_str_make]"] = marca
        if model:
            params["search[filter_str_model]"] = model
        if car_filters.get("an_de_la"):
            params["search[filter_float_year:from]"] = int(car_filters["an_de_la"])
        if car_filters.get("an_pana_la"):
            params["search[filter_float_year:to]"] = int(car_filters["an_pana_la"])
        if car_filters.get("km_maxim"):
            params["search[filter_float_mileage:to]"] = int(car_filters["km_maxim"])
        fuel = _norm(car_filters, "combustibil", _FUEL_MAP)
        if fuel:
            params["search[filter_enum_fuel_type][]"] = fuel
        body = _norm(car_filters, "caroserie", _BODY_MAP)
        if body:
            params["search[filter_enum_car_body_type][]"] = body
        gearbox = _norm(car_filters, "cutie_viteze", _GEARBOX_MAP)
        if gearbox:
            params["search[filter_enum_gearbox][]"] = gearbox

    if params:
        return base + "/?" + urllib.parse.urlencode(params)
    return base + "/"


def fetch_autovit_listing_details(url: str) -> dict:
    if not url:
        return {"images": [], "description": None, "specs": {}}
    headers = build_headers({"Referer": "https://www.autovit.ro/"})
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
        print(f"[AutovitScraper] details eroare: {exc}")
        return {"images": [], "description": None, "specs": {}}

    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    seen = set()
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if "apollo.olxcdn.com" in src or "autovit" in src:
            up = re.sub(r";s=\d+x\d+", ";s=1000x1000", src)
            if up not in seen:
                seen.add(up)
                imgs.append(up)
    description = None
    desc_el = (
        soup.find(attrs={"data-testid": "ad-description"})
        or soup.find(attrs={"data-cy": "ad_description"})
    )
    if desc_el:
        description = desc_el.get_text("\n", strip=True) or None
    specs = {}
    # Autovit afiseaza specs intr-o lista cu dt/dd sau div-uri itemprop
    for li in soup.select("li"):
        text = li.get_text(" ", strip=True)
        m = re.match(r"(An|Km|Motor|Combustibil|Cutie|Putere|Culoare|Caroserie)[:\s]+(.+)", text, re.I)
        if m:
            specs[m.group(1).lower()] = m.group(2).strip()
    return {"images": imgs, "description": description, "specs": specs}


def search_autovit(
    keyword: str,
    max_price: Optional[float],
    min_price: Optional[float] = None,
    exclude_words: Optional[list[str]] = None,
    car_filters: Optional[dict] = None,
    page: int = 1,
) -> list[dict]:
    exclude_words = exclude_words or []
    url = build_autovit_url(keyword, max_price, min_price, car_filters)
    if page > 1:
        url += (f"&page={page}" if "?" in url else f"?page={page}")

    headers = build_headers({"Referer": "https://www.autovit.ro/"})
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
                delay = rate_limit_backoff(attempt)
                print(f"[AutovitScraper] 429 retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            print(f"[AutovitScraper] HTTP {resp.status_code}")
            return []
        except Exception as exc:
            print(f"[AutovitScraper] Eroare ({attempt+1}/3): {exc}")
            time.sleep(rate_limit_backoff(attempt))

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select("article")
        or soup.select("[data-id]")
        or soup.select("div[data-cy='l-card']")
    )

    results = []
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = "https://www.autovit.ro" + href

            title_tag = card.find(["h2", "h3"]) or link_tag
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_tag = (
                card.find(attrs={"data-testid": "ad-price"})
                or card.find(class_=re.compile(r"price|pret", re.I))
            )
            price = _parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if price is None:
                continue
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue

            # Autovit afiseaza EUR de obicei; daca textul contine "RON" pastram RON
            currency = "EUR"
            if price_tag and "RON" in price_tag.get_text(" ", strip=True).upper():
                currency = "RON"

            location_tag = card.find(class_=re.compile(r"location|loc", re.I))
            location = location_tag.get_text(" ", strip=True) if location_tag else None

            img_tag = card.find("img")
            image_url = (img_tag.get("data-src") or img_tag.get("src")) if img_tag else None
            images = [image_url] if image_url else []

            # Specs vizibile in card: an, km, motor
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
                "platform": "autovit",
                "title": title,
                "price": price,
                "currency": currency,
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
            print(f"[AutovitScraper] card eroare: {exc}")
            continue

    for idx, item in enumerate(results):
        if idx > 0:
            time.sleep(random.uniform(0.7, 1.4))
        try:
            details = fetch_autovit_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
            if details.get("specs"):
                item.setdefault("specs", {}).update(details["specs"])
        except Exception as exc:
            print(f"[AutovitScraper] details {item['external_id']}: {exc}")
            continue

    print(f"[AutovitScraper] {len(results)} rezultate pentru '{keyword}'")
    return results
