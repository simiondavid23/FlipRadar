"""Scraper pentru publi24.ro — anunturi clasificate.

Folosim curl_cffi cu impersonate-ul chrome110. Site-ul foloseste rendering
server-side cu cateva clase CSS care se schimba periodic, deci selectoarele
sunt suficient de defensive.
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
    m = re.search(r"-(\d{6,})(?:\.html?|/?$)", url)
    if m:
        return f"publi24_{m.group(1)}"
    parsed = urllib.parse.urlparse(url)
    return f"publi24_{parsed.path.strip('/').replace('/', '_')[-50:]}"


def fetch_publi24_listing_details(url: str) -> dict:
    if not url:
        return {"images": [], "description": None}
    headers = build_headers({"Referer": "https://www.publi24.ro/"})
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
        print(f"[Publi24Scraper] details eroare: {exc}")
        return {"images": [], "description": None}

    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    seen = set()
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("data-original") or img.get("src") or ""
        if not src or src in seen:
            continue
        if "publi24" in src or src.startswith("https://"):
            seen.add(src)
            imgs.append(src)
    description = None
    desc_el = (
        soup.find(class_=re.compile(r"description|descriere|ad-detail", re.I))
        or soup.find("div", attrs={"itemprop": "description"})
    )
    if desc_el:
        description = desc_el.get_text("\n", strip=True) or None
    return {"images": imgs, "description": description}


def search_publi24(
    keyword: str,
    max_price: float,
    min_price: Optional[float] = None,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    judet: Optional[str] = None,
    oras: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
) -> list[dict]:
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []

    q = urllib.parse.quote(keyword_clean)
    if category:
        url = f"https://www.publi24.ro/anunturi/{category.strip('/')}/?q={q}"
    else:
        url = f"https://www.publi24.ro/anunturi/?q={q}"
    if max_price and max_price > 0:
        url += f"&pretMax={int(max_price)}"
    if min_price and min_price > 0:
        url += f"&pretMin={int(min_price)}"
    if page > 1:
        url += f"&pagina={page}"

    headers = build_headers({"Referer": "https://www.publi24.ro/"})
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
                print(f"[Publi24Scraper] 429 retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            print(f"[Publi24Scraper] HTTP {resp.status_code}")
            return []
        except Exception as exc:
            print(f"[Publi24Scraper] Eroare ({attempt+1}/3): {exc}")
            time.sleep(rate_limit_backoff(attempt))

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select(".article-content")
        or soup.select(".article-item")
        or soup.select(".listing-card")
        or soup.select("article")
        or soup.select("[data-id]")
    )

    results = []
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = "https://www.publi24.ro" + href

            title_tag = card.find(["h2", "h3"]) or link_tag
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_tag = card.find(class_=re.compile(r"price|pret", re.I))
            price = _parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if price is None:
                continue
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue

            location_tag = card.find(class_=re.compile(r"location|oras|judet|locatie", re.I))
            location = location_tag.get_text(" ", strip=True) if location_tag else None

            img_tag = card.find("img")
            image_url = (img_tag.get("data-src") or img_tag.get("src")) if img_tag else None
            images = [image_url] if image_url else []

            ext_id = _extract_external_id(href)
            if not ext_id:
                continue

            results.append({
                "external_id": ext_id,
                "platform": "publi24",
                "title": title,
                "price": price,
                "currency": "RON",
                "condition": None,
                "location": location,
                "url": href,
                "images": images,
                "description": None,
                "seller_name": None,
                "seller_id": None,
                "listed_at": None,
            })
        except Exception as exc:
            print(f"[Publi24Scraper] card eroare: {exc}")
            continue

    for idx, item in enumerate(results):
        if idx > 0:
            time.sleep(random.uniform(0.5, 1.0))
        try:
            details = fetch_publi24_listing_details(item["url"])
            if details.get("images"):
                item["images"] = details["images"]
            if details.get("description"):
                item["description"] = details["description"]
        except Exception as exc:
            print(f"[Publi24Scraper] details {item['external_id']}: {exc}")
            continue

    print(f"[Publi24Scraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
