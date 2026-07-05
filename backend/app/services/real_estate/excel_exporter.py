"""Export feed Imobiliare Monitor în .xlsx, peste build_generic_xlsx (shared).

Coloane relevante pentru RealEstateMonitorListing (verificate pe model): Titlu, Platformă,
Grad, Preț, Preț/mp, Camere, Suprafață, Zonă, Etaj, Vânzător, Keyword, Data găsirii,
Status, URL.

Ajustări față de lista generică cerută, impuse de câmpurile REALE ale modelului:
  * NU există câmp de dată-postare (modelul are doar `found_at`) → "Data postării" omisă.
  * NU există nume vânzător, doar `seller_id` (identificator vânzător, populat
    când scraperul îl oferă) → coloana "Vânzător" mapează pe `seller_id`.
"""
from typing import Iterable

from app.services.shared.xlsx_helper import build_generic_xlsx, fmt_dt, GRADE_FILLS

_PLATFORM_LABELS = {
    "olx": "OLX", "storia": "Storia", "imobiliare_ro": "Imobiliare.ro",
    "facebook_marketplace": "FB Marketplace", "facebook_groups": "Grupuri FB",
}

_COLUMNS = [
    "Titlu", "Platformă", "Grad", "Preț", "Preț/mp", "Camere", "Suprafață",
    "Zonă", "Etaj", "Vânzător", "Keyword", "Data găsirii", "Status", "URL",
]
_URL_COL_IDX = len(_COLUMNS) - 1  # 13


def _price(item: dict) -> str:
    p = item.get("price")
    if p is None:
        return ""
    cur = item.get("currency") or "EUR"
    return f"{round(float(p)):,}".replace(",", ".") + f" {cur}"


def _price_sqm(item: dict):
    v = item.get("price_per_sqm")
    if v is None:
        return ""
    return round(float(v), 1)


def build_re_xlsx(rows: Iterable[dict]) -> bytes:
    """rows = iterable de dict-uri cu cheile: title, platform, grade, price, currency,
    price_per_sqm, rooms, area_sqm, zone_normalized, zone_raw, floor, seller_id,
    keyword_name, found_at, status, url."""
    table = []
    for it in rows:
        table.append([
            it.get("title") or "",
            _PLATFORM_LABELS.get(it.get("platform"), (it.get("platform") or "")),
            it.get("grade") or "",
            _price(it),
            _price_sqm(it),
            it.get("rooms") if it.get("rooms") is not None else "",
            it.get("area_sqm") if it.get("area_sqm") is not None else "",
            it.get("zone_normalized") or it.get("zone_raw") or "",
            it.get("floor") or "",
            it.get("seller_id") or "",
            it.get("keyword_name") or "",
            fmt_dt(it.get("found_at")),
            it.get("status") or "",
            it.get("url") or "",
        ])
    return build_generic_xlsx(
        _COLUMNS, table, hyperlink_col_idx=_URL_COL_IDX,
        row_fill_fn=lambda r: GRADE_FILLS.get(r[2]),
        sheet_title="Anunțuri Imobiliare",
    )
