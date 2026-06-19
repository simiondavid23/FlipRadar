"""OpenLane — incearca intai JSON embed (Next.js __NEXT_DATA__) apoi HTML."""
import json
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.lots._common import (
    IMPERSONATE, MAX_LOTS, build_headers, parse_int, parse_money, make_lot,
)

_BASE = "https://www.openlane.com"
_LISTINGS = f"{_BASE}/en/listings"


def _walk_for_listings(obj, out, depth=0):
    """Cauta recursiv liste de obiecte ce par a fi vehicule in JSON-ul embed."""
    if depth > 6 or len(out) >= MAX_LOTS:
        return
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj.keys()}
        if ("make" in keys or "model" in keys) and ("year" in keys or "vin" in keys):
            out.append(obj)
            return
        for v in obj.values():
            _walk_for_listings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk_for_listings(v, out, depth + 1)


async def search_openlane_lots(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    filters = filters or {}
    url = _LISTINGS
    params = {"search": query} if query else None
    headers = build_headers({"Referer": _BASE + "/"})
    results = []

    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[openlane] HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[openlane] error: {exc}")
        return []

    # 1) JSON embed (__NEXT_DATA__ sau application/json)
    try:
        script = soup.find("script", id="__NEXT_DATA__") or soup.find("script", type="application/json")
        if script and script.string:
            data = json.loads(script.string)
            found = []
            _walk_for_listings(data, found)
            for it in found:
                title = it.get("title") or " ".join(str(it.get(k)) for k in ("year", "make", "model") if it.get(k)) or None
                if not title:
                    continue
                results.append(make_lot(
                    platform="openlane",
                    lot_number=str(it.get("id") or it.get("lotNumber") or "") or None,
                    title=title, make=it.get("make"), model=it.get("model"),
                    year=parse_int(it.get("year")), odometer=parse_int(it.get("odometer") or it.get("mileage")),
                    location_city=it.get("city") or it.get("location"),
                    thumbnail_url=(it.get("image") or it.get("thumbnail") or (it.get("images") or [None])[0]),
                    current_bid=parse_money(it.get("currentBid") or it.get("price")),
                    source_url=(f"{_BASE}{it.get('url')}" if str(it.get("url") or "").startswith("/") else it.get("url")),
                    vin=it.get("vin"), requires_account=[],
                ))
                if len(results) >= MAX_LOTS:
                    break
    except Exception as exc:
        print(f"[openlane] JSON embed error: {exc}")

    # 2) fallback HTML
    if not results:
        for card in (soup.select(".listing-card") or soup.select("[data-listing]") or soup.select("article")):
            try:
                link = card.find("a", href=True)
                href = link["href"] if link else None
                if href and href.startswith("/"):
                    href = _BASE + href
                title_el = card.find(["h3", "h4"]) or link
                title = title_el.get_text(strip=True) if title_el else None
                if not title:
                    continue
                img = card.find("img")
                thumb = (img.get("src") or img.get("data-src")) if img else None
                year_m = re.search(r"\b(19|20)\d{2}\b", title)
                results.append(make_lot(
                    platform="openlane", title=title,
                    year=int(year_m.group(0)) if year_m else None,
                    thumbnail_url=thumb, source_url=href, requires_account=[],
                ))
                if len(results) >= MAX_LOTS:
                    break
            except Exception:
                continue

    print(f"[openlane] {len(results)} loturi pentru '{query}'")
    return results[:MAX_LOTS]
