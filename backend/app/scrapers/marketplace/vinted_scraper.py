"""Scraper Vinted.ro prin API-ul intern v2/catalog/items.

curl_cffi AsyncSession + impersonate=chrome131. Vinted poate cere un cookie de
sesiune pentru raspunsuri complete; daca `filters["cookie"]` e prezent, il trimitem.
"""
from curl_cffi.requests import AsyncSession

from app.scrapers.marketplace._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, make_result,
)

_API_URL = "https://www.vinted.ro/api/v2/catalog/items"

# Maparea status_ids -> eticheta lizibila (1..5 conform API-ului Vinted).
_STATUS_LABELS = {
    1: "Nou cu eticheta",
    2: "Nou fara eticheta",
    3: "Foarte bun",
    4: "Bun",
    5: "Satisfacator",
}


def _coerce_price(raw):
    """Vinted poate returna price ca obiect {amount, currency_code} sau ca string."""
    currency = "EUR"
    amount = None
    if isinstance(raw, dict):
        amount = raw.get("amount")
        currency = raw.get("currency_code") or currency
    elif isinstance(raw, (int, float, str)):
        amount = raw
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    return amount, currency


async def search_vinted(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    if not query:
        return []
    filters = filters or {}

    params = {
        "search_text": query,
        "per_page": 48,
        "page": 1,
        "order": "relevance",
    }
    if filters.get("brand_id"):
        params["brand_ids"] = filters["brand_id"]
    if filters.get("size_ids"):
        v = filters["size_ids"]
        params["size_ids"] = ",".join(map(str, v)) if isinstance(v, (list, tuple)) else v
    if filters.get("status_ids"):
        v = filters["status_ids"]
        params["status_ids"] = ",".join(map(str, v)) if isinstance(v, (list, tuple)) else v
    if filters.get("min_price") is not None:
        params["price_from"] = filters["min_price"]
    if filters.get("max_price") is not None:
        params["price_to"] = filters["max_price"]

    headers = build_headers({
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.vinted.ro/catalog",
        "X-Requested-With": "XMLHttpRequest",
    })
    if filters.get("cookie"):
        headers["Cookie"] = filters["cookie"]

    results = []
    try:
        async with AsyncSession() as session:
            resp = await session.get(
                _API_URL, params=params, headers=headers,
                impersonate=IMPERSONATE, timeout=20,
            )
            if resp.status_code != 200:
                print(f"[vinted] HTTP {resp.status_code}")
                return []
            data = resp.json()
    except Exception as exc:
        print(f"[vinted] error: {exc}")
        return []

    items = (data or {}).get("items") or []
    for item in items:
        try:
            title = item.get("title") or ""
            if not title:
                continue
            amount, currency = _coerce_price(item.get("price"))

            status = item.get("status")
            if isinstance(status, int):
                condition = _STATUS_LABELS.get(status)
            else:
                condition = status

            photos = item.get("photos") or []
            thumb = None
            if photos and isinstance(photos, list):
                thumb = (photos[0] or {}).get("url")
            if not thumb:
                thumb = (item.get("photo") or {}).get("url") if isinstance(item.get("photo"), dict) else None

            results.append(make_result(
                title=title, price=amount, currency=currency or "EUR",
                condition=condition, location=None,
                source_url=item.get("url"), thumbnail_url=thumb,
                source="vinted", platform_id=str(item.get("id")) if item.get("id") is not None else None,
            ))
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[vinted] item parse error: {exc}")
            continue

    print(f"[vinted] {len(results)} rezultate pentru '{query}'")
    return results[:MAX_RESULTS]
