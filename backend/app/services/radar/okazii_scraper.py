"""Scraper pentru Okazii.ro.

Site-ul foloseste rendering server-side, deci HTML-ul descarcat e suficient.
Pagina 1 e suficienta pentru polling frecvent — anunturile noi apar primele.
"""
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config
from app.services.radar.categories import OKAZII_CATEGORY_SLUGS


def _parse_okazii_date(raw: Optional[str]) -> Optional[datetime]:
    """Okazii foloseste format dd.mm.yyyy, uneori cu ora HH:MM."""
    if not raw:
        return None
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?:\s+(\d{1,2}):(\d{2}))?", raw)
    if not m:
        return None
    try:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        hour = int(m.group(4)) if m.group(4) else 0
        minute = int(m.group(5)) if m.group(5) else 0
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


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
    # Okazii foloseste path-uri de tip /a/numar/slug
    m = re.search(r"/a/(\d+)", url)
    if m:
        return f"okazii_{m.group(1)}"
    parsed = urllib.parse.urlparse(url)
    return f"okazii_{parsed.path.strip('/').replace('/', '_')[-50:]}"


def search_okazii(
    keyword: str,
    max_price: float,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Cauta pe Okazii.ro si returneaza listinguri in format standard."""
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []

    q = urllib.parse.quote(keyword_clean)
    # Daca avem categorie mapata, includem in path; altfel /cautare global
    cat_slug = OKAZII_CATEGORY_SLUGS.get(category) if category else None
    if cat_slug:
        url = f"https://www.okazii.ro/{cat_slug}/cautare?q={q}"
    else:
        url = f"https://www.okazii.ro/cautare?q={q}"
    if max_price and max_price > 0:
        url += f"&p_max={int(max_price)}"
    if min_price and min_price > 0:
        url += f"&p_min={int(min_price)}"

    headers = build_headers({"Referer": "https://www.okazii.ro/"})
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
                print(f"[OkaziiScraper] 429 rate limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            print(f"[OkaziiScraper] HTTP {resp.status_code}")
            return []
        except Exception as exc:
            print(f"[OkaziiScraper] Eroare ({attempt+1}/3): {exc}")
            time.sleep(rate_limit_backoff(attempt))

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    # Okazii foloseste div-uri de tip product/listing cu clase .item, .ofertaItem
    cards = soup.select(".oferta") or soup.select(".item") or soup.select("[data-product-id]") or soup.select("article")

    results = []
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = "https://www.okazii.ro" + href

            title_tag = card.find("h2") or card.find("h3") or card.find(class_=re.compile(r"title", re.I)) or link_tag
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_tag = card.find(class_=re.compile(r"pret|price", re.I))
            price = _parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if price is None:
                continue
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue

            location_tag = card.find(class_=re.compile(r"location|locatie|oras", re.I))
            location = location_tag.get_text(" ", strip=True) if location_tag else None

            date_tag = card.find(class_=re.compile(r"date|data", re.I)) or card.find("time")
            listed_at = None
            if date_tag:
                dt_attr = date_tag.get("datetime") if hasattr(date_tag, "get") else None
                if dt_attr:
                    try:
                        listed_at = datetime.fromisoformat(dt_attr.replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        listed_at = None
                if not listed_at:
                    listed_at = _parse_okazii_date(date_tag.get_text(" ", strip=True))

            img_tag = card.find("img")
            image_url = None
            if img_tag:
                image_url = img_tag.get("data-src") or img_tag.get("src")
            images = [image_url] if image_url else []

            seller_tag = card.find(class_=re.compile(r"seller|vanzator", re.I))
            seller_name = seller_tag.get_text(" ", strip=True) if seller_tag else None

            ext_id = _extract_external_id(href)
            if not ext_id:
                continue

            results.append({
                "external_id": ext_id,
                "platform": "okazii",
                "title": title,
                "price": price,
                "currency": "RON",
                "condition": None,
                "location": location,
                "url": href,
                "images": images,
                "description": None,
                "seller_name": seller_name,
                "seller_id": None,
                "listed_at": listed_at,
            })
        except Exception as exc:
            print(f"[OkaziiScraper] Eroare la parsare card: {exc}")
            continue

    print(f"[OkaziiScraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
