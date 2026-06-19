"""Scraper eBay Kleinanzeigen (Marketplace, DE). curl_cffi AsyncSession + BeautifulSoup."""
import re

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.marketplace._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price, normalize_condition,
    make_result, price_in_range,
)

_BASE = "https://www.kleinanzeigen.de"
_SEARCH_URL = f"{_BASE}/s-suchanfrage.html"


async def search_kleinanzeigen(query: str, category_id: str = "", filters: dict = {}) -> list:
    query = (query or "").strip()
    if not query:
        return []
    filters = filters or {}

    params = {"keywords": query}
    if category_id:
        params["categoryId"] = category_id
    if filters.get("plz"):
        params["locationCity"] = filters["plz"]
    if filters.get("radius_km"):
        params["locationRadius"] = filters["radius_km"]

    headers = build_headers({"Referer": _BASE + "/", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    results = []

    try:
        async with AsyncSession() as session:
            resp = await session.get(
                _SEARCH_URL, params=params, headers=headers,
                impersonate=IMPERSONATE, timeout=20,
            )
            if resp.status_code != 200:
                print(f"[kleinanzeigen] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[kleinanzeigen] error: {exc}")
        return []

    cards = soup.select("article.aditem") or soup.select(".aditem")
    for card in cards:
        try:
            title_tag = (
                card.select_one(".aditem-main--middle--title")
                or card.select_one("h2 a")
                or card.find("a", href=True)
            )
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue

            link = card.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = _BASE + href

            price_tag = card.select_one(".aditem-main--middle--price-shipping--price") or card.select_one(".aditem-main--middle--price")
            price = parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if not price_in_range(price, filters):
                continue

            loc_tag = card.select_one(".aditem-main--top--left")
            location = loc_tag.get_text(" ", strip=True) if loc_tag else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-imgsrc") or img.get("data-src")) if img else None

            cond_tag = card.select_one(".text-module-end") or card.select_one(".aditem-main--bottom")
            condition = normalize_condition(cond_tag.get_text(" ", strip=True)) if cond_tag else normalize_condition(title)

            results.append(make_result(
                title=title, price=price, currency="EUR", condition=condition,
                location=location, source_url=href, thumbnail_url=thumb,
                source="kleinanzeigen", platform_id=card.get("data-adid"),
            ))
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[kleinanzeigen] card parse error: {exc}")
            continue

    print(f"[kleinanzeigen] {len(results)} rezultate pentru '{query}'")
    return results[:MAX_RESULTS]
