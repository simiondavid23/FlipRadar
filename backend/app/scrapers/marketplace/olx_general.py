"""Scraper OLX.ro general (Marketplace) — exclude categoriile auto si imobiliare.

curl_cffi AsyncSession + impersonate=chrome131 + BeautifulSoup. Max 3 pagini.
"""
import asyncio
import random
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.marketplace._common import (
    IMPERSONATE, MAX_RESULTS, PAGE_DELAY_RANGE,
    build_headers, parse_price, normalize_condition, make_result, price_in_range,
)

_BASE = "https://www.olx.ro"
# Excludem orice anunt al carui href trimite spre auto sau imobiliare.
_EXCLUDED_HREF = ("/auto", "/imobiliare", "autovit.ro", "storia.ro")


def _platform_id(href: str):
    m = re.search(r"-ID([A-Za-z0-9]+)\.html", href or "")
    if m:
        return m.group(1)
    return None


async def search_olx_general(query: str, category: str = "", filters: dict = {}) -> list:
    query = (query or "").strip()
    if not query:
        return []
    filters = filters or {}

    q = urllib.parse.quote(query)
    base_url = f"{_BASE}/oferte/q-{q}/"

    params = {}
    if filters.get("min_price") is not None:
        try:
            params["search[filter_float_price:from]"] = int(float(filters["min_price"]))
        except (TypeError, ValueError):
            pass
    if filters.get("max_price") is not None:
        try:
            params["search[filter_float_price:to]"] = int(float(filters["max_price"]))
        except (TypeError, ValueError):
            pass
    state = (filters.get("state") or "").strip().lower()
    if state in ("nou", "new"):
        params["search[filter_enum_state][0]"] = "new"
    elif state in ("folosit", "used", "second hand"):
        params["search[filter_enum_state][0]"] = "used"

    location_filter = (filters.get("location") or "").strip().lower()
    headers = build_headers({"Referer": _BASE + "/"})
    results = []

    try:
        async with AsyncSession() as session:
            for page in range(1, 4):  # maxim 3 pagini
                if page > 1:
                    await asyncio.sleep(random.uniform(*PAGE_DELAY_RANGE))
                page_params = dict(params)
                if page > 1:
                    page_params["page"] = page
                try:
                    resp = await session.get(
                        base_url, params=page_params, headers=headers,
                        impersonate=IMPERSONATE, timeout=20,
                    )
                except Exception as exc:
                    print(f"[olx_general] fetch error page {page}: {exc}")
                    break
                if resp.status_code != 200:
                    print(f"[olx_general] HTTP {resp.status_code} page {page}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select('div[data-cy="l-card"]') or soup.select('[data-testid="l-card"]')
                if not cards:
                    break

                for card in cards:
                    try:
                        link = card.find("a", href=True)
                        if not link:
                            continue
                        href = link["href"]
                        if href.startswith("/"):
                            href = _BASE + href
                        low = href.lower()
                        if any(x in low for x in _EXCLUDED_HREF):
                            continue

                        title_tag = card.find("h4") or card.find("h6") or link
                        title = title_tag.get_text(strip=True) if title_tag else ""
                        if not title:
                            continue

                        price_tag = card.find(attrs={"data-testid": "ad-price"}) or card.find("p")
                        price = parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
                        if not price_in_range(price, filters):
                            continue

                        loc_tag = card.find(attrs={"data-testid": "location-date"})
                        location = None
                        if loc_tag:
                            raw = loc_tag.get_text(" ", strip=True)
                            location = raw.split("-")[0].strip() if "-" in raw else raw.strip()
                        if location_filter and (not location or location_filter not in location.lower()):
                            continue

                        cond_tag = card.find(attrs={"data-testid": "ad-state"})
                        condition = normalize_condition(cond_tag.get_text(" ", strip=True)) if cond_tag else None

                        img = card.find("img")
                        thumb = (img.get("src") or img.get("data-src")) if img else None

                        results.append(make_result(
                            title=title, price=price, currency="RON", condition=condition,
                            location=location, source_url=href, thumbnail_url=thumb,
                            source="olx", platform_id=_platform_id(href),
                        ))
                        if len(results) >= MAX_RESULTS:
                            return results
                    except Exception as exc:
                        print(f"[olx_general] card parse error: {exc}")
                        continue
    except Exception as exc:
        print(f"[olx_general] error: {exc}")
        return []

    print(f"[olx_general] {len(results)} rezultate pentru '{query}'")
    return results[:MAX_RESULTS]
