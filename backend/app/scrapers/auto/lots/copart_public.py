"""Copart — date PUBLICE fara cont.

Incearca intai endpoint-ul JSON public de search; daca redirectioneaza la login
sau nu returneaza JSON, cade pe scraping HTML al paginii publice. Campurile care
necesita cont (licitatie, VIN, stare) raman None si sunt listate in requires_account.
"""
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.lots._common import (
    IMPERSONATE, MAX_LOTS, REQUIRES_ACCOUNT,
    build_headers, parse_int, parse_epoch_ms, make_lot,
)
from app.services.log_manager import log_manager

_JSON_URL = "https://www.copart.com/public/lots/search-results"
_HTML_URL = "https://www.copart.com/vehicleFinderSearch"


def _g(it: dict, *keys):
    for k in keys:
        v = it.get(k)
        if v not in (None, "", []):
            return v
    return None


def _title(year, make, model):
    parts = [str(year) if year else None, make, model]
    out = " ".join(p for p in parts if p)
    return out or None


def _parse_json_lot(it: dict):
    try:
        lot_number = _g(it, "lotNumberStr", "ln", "lot")
        make = _g(it, "mkn", "make")
        model = _g(it, "lm", "lmg", "model")
        year = parse_int(_g(it, "lcy", "year"))
        title = _g(it, "ld") or _title(year, make, model)
        return make_lot(
            platform="copart",
            lot_number=str(lot_number) if lot_number else None,
            title=title, make=make, model=model, year=year,
            damage_primary=_g(it, "dd", "damageType", "primaryDamage"),
            location_city=_g(it, "yn", "la", "city"),
            location_state=_g(it, "st", "state"),
            auction_date=parse_epoch_ms(_g(it, "ad", "auctionDate")),
            odometer=parse_int(_g(it, "orr", "odometer")),
            thumbnail_url=_g(it, "tims", "image", "thumbnail"),
            source_url=(f"https://www.copart.com/lot/{lot_number}" if lot_number else None),
            requires_account=REQUIRES_ACCOUNT,  # current_bid/vin/title_type/etc. raman None
        )
    except Exception as exc:
        print(f"[copart] lot parse error: {exc}")
        return None


async def _scrape_html(session: AsyncSession, query: str) -> list:
    """Fallback HTML — pagina publica e SPA, deci adesea fara loturi statice."""
    try:
        resp = await session.get(
            _HTML_URL, params={"free": "true", "query": query},
            headers=build_headers({"Referer": "https://www.copart.com/"}),
            impersonate=IMPERSONATE, timeout=20,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[copart] HTML error: {exc}")
        return []

    out = []
    for row in soup.select("tr[data-uname], .lot-card, article"):
        try:
            link = row.find("a", href=True)
            href = link["href"] if link else None
            if href and href.startswith("/"):
                href = "https://www.copart.com" + href
            title_el = row.find(["h4", "h3", "a"])
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue
            img = row.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None
            out.append(make_lot(
                platform="copart", title=title, source_url=href, thumbnail_url=thumb,
                requires_account=REQUIRES_ACCOUNT,
            ))
            if len(out) >= MAX_LOTS:
                break
        except Exception:
            continue
    return out


async def search_copart_lots(query: str, filters: dict = {}) -> list:
    query = (query or "").strip()
    filters = filters or {}
    payload = {
        "query": [query] if query else [],
        "filter": {"MAKE": filters.get("make", []), "MODEL": filters.get("model", [])},
        "page": 0,
        "size": 20,
    }
    headers = build_headers({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://www.copart.com/",
    })

    log_manager.emit("auto_lots", "SCAN", f"Copart: cautare loturi '{query or '-'}'")
    results = []
    try:
        async with AsyncSession() as session:
            # 1) endpoint JSON public
            try:
                resp = await session.post(_JSON_URL, json=payload, headers=headers, impersonate=IMPERSONATE, timeout=20)
                ctype = (resp.headers.get("content-type") or "").lower()
                if resp.status_code == 200 and "json" in ctype:
                    data = resp.json()
                    content = (((data or {}).get("data") or {}).get("results") or {}).get("content") or []
                    for it in content:
                        lot = _parse_json_lot(it)
                        if lot:
                            results.append(lot)
                        if len(results) >= MAX_LOTS:
                            break
                else:
                    print(f"[copart] JSON indisponibil (status {resp.status_code}, {ctype}) — incerc HTML")
            except Exception as exc:
                print(f"[copart] JSON error: {exc} — incerc HTML")

            # 2) fallback HTML
            if not results:
                results = await _scrape_html(session, query)
    except Exception as exc:
        print(f"[copart] error: {exc}")
        log_manager.emit("auto_lots", "ERR", f"Copart eroare: {str(exc)[:80]}")
        return []

    print(f"[copart] {len(results)} loturi pentru '{query}'")
    log_manager.emit("auto_lots", "OK", f"Copart: {len(results)} loturi gasite")
    return results[:MAX_LOTS]
