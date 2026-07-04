"""Scraper Publi24.ro — anunturi clasificate.

Rescris complet de la zero (Faza 0 — diagnostic live, fara Playwright/cookie).
Foloseste curl_cffi cu impersonate=chrome110 ca OLX. Structura confirmata prin
fetch-uri reale:

- Cautare:   https://www.publi24.ro/anunturi/?q={kw}          (root)
             https://www.publi24.ro/anunturi/{cat}/{subcat}/?q={kw}  (cu categorie)
- Judet:     segment de path dupa categorie: /anunturi/{cat}/{judet-slug}/
- Pret:      &minprice={int}&maxprice={int}   (LOWERCASE — camelCase da 500)
- Stare:     &status=nou | &status=folosit
- Paginare:  &pag={N}                          (NU &pagina — bug-ul vechi)
- Card:      div.article-item (se sar cele promovate: .art-promoted / clasa *b2b*)
- external_id: ultimul segment de path inainte de .html (string alfanumeric complet)
"""
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager
from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config


_IMPERSONATE = "chrome110"
_BASE = "https://www.publi24.ro"

# Plasa de siguranta la paginare — scanner-ul se opreste oricum cand o pagina nu
# mai aduce anunturi noi; capul previne o bucla runaway daca site-ul repeta pagina 1.
_PUBLI24_MAX_PAGES = 20


_RO_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
    "ian": 1, "feb": 2, "mar": 3, "apr": 4, "iun": 6, "iul": 7, "aug": 8,
    "sep": 9, "oct": 10, "noi": 11, "dec": 12,
}


def _strip_accents(s: Optional[str]) -> str:
    return (s or "").lower().replace("ă", "a").replace("â", "a").replace("î", "i") \
        .replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")


def _judet_slug(judet: Optional[str]) -> Optional[str]:
    """Judetul devine slug de path (accent-insensitive, spatii -> '-')."""
    if not judet:
        return None
    s = _strip_accents(judet).strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s or None


def _parse_price(raw: str) -> tuple[Optional[float], str]:
    """Publi24 afiseaza intregi cu spatiu/punct/virgula ca separator de mii
    ('3 144 RON', '1.300 RON', '73,297 RON'). Returneaza (valoare, moneda)."""
    if not raw:
        return None, "RON"
    currency = "EUR" if ("EUR" in raw.upper() or "€" in raw) else "RON"
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None, currency
    try:
        return float(digits), currency
    except ValueError:
        return None, currency


def _extract_external_id(url: str) -> Optional[str]:
    """ID = ultimul segment de path inainte de .html (hash alfanumeric complet).
    NU regex pe cifre — ID-urile Publi24 sunt alfanumerice."""
    if not url:
        return None
    m = re.search(r"/([A-Za-z0-9_-]+)\.html?(?:[?#].*)?$", url)
    if m:
        return f"publi24_{m.group(1)}"
    parsed = urllib.parse.urlparse(url)
    tail = parsed.path.strip("/").replace("/", "_")[-50:]
    return f"publi24_{tail}" if tail else None


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    """'29 iunie' (zi + luna RO, fara an), 'azi'/'ieri'."""
    if not raw:
        return None
    t = _strip_accents(raw).strip()
    now = datetime.now()
    if t.startswith("azi") or "astazi" in t:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if t.startswith("ieri"):
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.search(r"(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?", t)
    if m:
        day = int(m.group(1))
        month = _RO_MONTHS.get(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if month:
            try:
                dt = datetime(year, month, day)
                # fara an: daca data iese in viitor, e din anul trecut
                if not m.group(3) and dt > now + timedelta(days=1):
                    dt = datetime(year - 1, month, day)
                return dt
            except ValueError:
                return None
    return None


def _upgrade_image(url: str) -> str:
    """Ridica thumbnail-ul Publi24 (top/large/...) la varianta extralarge."""
    if not url:
        return url
    return re.sub(
        r"(s3\.publi24\.ro/[^/]+/)(top|large|medium|small|thumb|thumbnail)/",
        r"\1extralarge/",
        url,
    )


def _condition_param(condition: str) -> Optional[str]:
    if condition == "new":
        return "nou"
    if condition == "used":
        return "folosit"
    return None


def _build_url(keyword: str, category: Optional[str], judet: Optional[str],
               max_price: Optional[float], min_price: Optional[float],
               status: Optional[str], page: int) -> str:
    q = urllib.parse.quote((keyword or "").strip())
    parts = ["anunturi"]
    if category:
        parts.append(category.strip("/"))
    js = _judet_slug(judet)
    if js:
        parts.append(js)
    path = "/".join(parts) + "/"

    params = {"q": q}
    if max_price and max_price > 0:
        params["maxprice"] = int(max_price)
    if min_price and min_price > 0:
        params["minprice"] = int(min_price)
    if status:
        params["status"] = status
    if page and page > 1:
        params["pag"] = int(page)
    # q e deja quote-uit; construim query manual ca sa nu-l dublu-encodam
    query = "&".join(
        f"{k}={v}" if k == "q" else f"{k}={urllib.parse.quote(str(v))}"
        for k, v in params.items()
    )
    return f"{_BASE}/{path}?{query}"


def _request(url: str, referer: str = _BASE + "/") -> Optional[str]:
    """GET cu 3 reincercari + backoff pe 429. None la esec."""
    headers = build_headers({"Referer": referer})
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
                log_manager.emit("radar", "WARN", f"Publi24: 429 rate-limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            if resp.status_code == 404:
                return None
            log_manager.emit("radar", "WARN", f"Publi24: HTTP {resp.status_code} pentru {url}")
            return None
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Publi24: eroare fetch ({attempt+1}/3): {str(exc)[:100]}")
            time.sleep(rate_limit_backoff(attempt))
    return None


def fetch_publi24_listing_details(url: str) -> dict:
    """Descarca pagina individuala si extrage descrierea completa + toate imaginile
    din galerie (la calitate extralarge). {"images": [...], "description": str|None}
    La orice eroare, dict gol -> caller-ul pastreaza datele din pagina de search."""
    if not url:
        return {"images": [], "description": None}
    html = _request(url, referer=_BASE + "/")
    if not html:
        return {"images": [], "description": None}

    soup = BeautifulSoup(html, "html.parser")

    # Descriere
    description = None
    desc_el = (
        soup.select_one(".article-description")
        or soup.find(attrs={"itemprop": "description"})
        or soup.select_one("#dvAnuntDescription")
    )
    if desc_el:
        txt = desc_el.get_text("\n", strip=True)
        description = txt or None

    # Imagini din galerie — scop preferat containerele de galerie, apoi orice imagine s3.
    imgs: list[str] = []
    seen = set()
    gallery_imgs = soup.select("#gallery img, #detail-gallery img")
    if not gallery_imgs:
        gallery_imgs = soup.select("img")
    for im in gallery_imgs:
        src = im.get("data-src") or im.get("src") or ""
        if not src or src.startswith("data:"):
            continue
        if "publi24.ro" not in src:
            continue
        up = _upgrade_image(src.split("?")[0])
        if up in seen:
            continue
        seen.add(up)
        imgs.append(up)

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
    """Cauta pe Publi24 dupa keyword; returneaza listinguri in format standard.

    `category` = slug de path 'categorie/subcategorie' (value din PLATFORM_CATEGORIES).
    `page` (>=1) adauga &pag=N. Enrichment secvential (descriere + galerie) ca la OLX.
    """
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if page > _PUBLI24_MAX_PAGES:
        return []

    status = _condition_param(condition)
    url = _build_url(keyword_clean, category, judet, max_price, min_price, status, page)
    log_manager.emit("radar", "SCAN", f'Publi24 "{keyword_clean}" (pag {page})')

    html = _request(url)
    if not html:
        log_manager.emit("radar", "WARN", f'Publi24: fara raspuns pentru "{keyword_clean}" (pag {page})')
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.article-item")

    # Conditia afisata pe card lipseste la Publi24; daca am filtrat server-side pe
    # status, toate rezultatele au acea stare -> o reflectam in listing.
    listing_condition = None
    if status == "nou":
        listing_condition = "nou"
    elif status == "folosit":
        listing_condition = "second hand"

    results: list[dict] = []
    for card in cards:
        try:
            cls = " ".join(card.get("class", []))
            # Sar peste anunturile promovate (ignora filtrele de pret/stare)
            if card.select_one(".art-promoted") or "b2b" in cls:
                continue

            link_tag = card.select_one("h2.article-title a[href]") or card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = _BASE + href

            title_tag = card.select_one("h2.article-title") or card.select_one(".article-title") or link_tag
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_el = card.select_one(".article-price")
            price, currency = (None, "RON")
            if price_el:
                new_price = price_el.select_one(".new-price")
                price_text = new_price.get_text(" ", strip=True) if new_price else price_el.get_text(" ", strip=True)
                price, currency = _parse_price(price_text)
            if price is None:
                continue
            if max_price and max_price > 0 and price > max_price:
                continue
            if min_price and min_price > 0 and price < min_price:
                continue

            loc_el = card.select_one("p.article-location span") or card.select_one(".article-location")
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            if location:
                location = location.strip() or None

            date_el = card.select_one("p.article-date span") or card.select_one(".article-date")
            listed_at = _parse_date(date_el.get_text(" ", strip=True)) if date_el else None

            img_tag = card.select_one(".art-img img") or card.find("img")
            image_url = None
            if img_tag:
                image_url = img_tag.get("data-src") or img_tag.get("src")
                if image_url and image_url.startswith("data:"):
                    image_url = None
            images = [_upgrade_image(image_url)] if image_url else []

            ext_id = _extract_external_id(href)
            if not ext_id:
                continue

            results.append({
                "external_id": ext_id,
                "platform": "publi24",
                "title": title,
                "price": price,
                "currency": currency,
                "condition": listing_condition,
                "location": location,
                "url": href,
                "images": images,
                "description": None,
                "seller_name": None,
                "seller_id": None,
                "listed_at": listed_at,
            })
        except Exception as exc:
            log_manager.emit("radar", "WARN", f"Publi24: card invalid ignorat: {str(exc)[:80]}")
            continue

    # Enrichment secvential — descriere completa + toate imaginile din galerie.
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
            log_manager.emit("radar", "WARN", f"Publi24: enrichment {item['external_id']}: {str(exc)[:80]}")
            continue

    log_manager.emit("radar", "OK", f'Publi24: {len(results)} rezultate pentru "{keyword_clean}" (pag {page})')
    return results
