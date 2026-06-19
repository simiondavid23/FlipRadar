"""Scraper LaJumate.ro (Marketplace). curl_cffi AsyncSession + BeautifulSoup."""
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.marketplace._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price, normalize_condition,
    make_result, price_in_range,
)

_BASE = "https://www.lajumate.ro"


async def search_lajumate(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    if not query:
        return []
    filters = filters or {}
    url = f"{_BASE}/cauta/?q={urllib.parse.quote(query)}"
    headers = build_headers({"Referer": _BASE + "/"})
    results = []

    try:
        async with AsyncSession() as session:
            resp = await session.get(url, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[lajumate] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[lajumate] error: {exc}")
        return []

    cards = (
        soup.select(".anunt-item")
        or soup.select(".listing-item")
        or soup.select("article")
        or soup.select("[data-id]")
    )
    for card in cards:
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = _BASE + href

            title_tag = card.find(["h2", "h3"]) or link
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue

            price_tag = card.find(class_=re.compile(r"price|pret", re.I))
            price = parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
            if not price_in_range(price, filters):
                continue

            loc_tag = card.find(class_=re.compile(r"location|oras|locatie|judet", re.I))
            location = loc_tag.get_text(" ", strip=True) if loc_tag else None

            cond_tag = card.find(class_=re.compile(r"stare|condition", re.I))
            condition = normalize_condition(cond_tag.get_text(" ", strip=True)) if cond_tag else normalize_condition(title)

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_result(
                title=title, price=price, currency="RON", condition=condition,
                location=location, source_url=href, thumbnail_url=thumb,
                source="lajumate", platform_id=card.get("data-id"),
            ))
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[lajumate] card parse error: {exc}")
            continue

    print(f"[lajumate] {len(results)} rezultate pentru '{query}'")
    return results[:MAX_RESULTS]
