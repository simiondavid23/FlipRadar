"""Export feed Auto Anunțuri în .xlsx, peste build_generic_xlsx (shared).

Coloane relevante pentru AutoFeedListing (verificate pe model): Titlu, Platformă, Grad,
Preț, An, Km, Combustibil, Locație, Vânzător, Keyword, Data postării, Data găsirii,
Status, URL. `seller_name` și `listed_at` sunt îmbogățite on-demand (pot fi goale până la
deschiderea detaliului), dar sunt câmpuri reale pe model, deci le păstrăm.
"""
from typing import Iterable

from app.services.shared.xlsx_helper import build_generic_xlsx, fmt_dt, GRADE_FILLS

_PLATFORM_LABELS = {
    "autovit": "Autovit", "olx_auto": "OLX Auto", "mobile_de": "Mobile.de",
    "autoscout24": "AutoScout24", "facebook_auto": "Facebook Auto",
    "kleinanzeigen_auto": "Kleinanzeigen",
}

_COLUMNS = [
    "Titlu", "Platformă", "Grad", "Preț", "An", "Km", "Combustibil",
    "Locație", "Vânzător", "Keyword", "Data postării", "Data găsirii", "Status", "URL",
]
_URL_COL_IDX = len(_COLUMNS) - 1  # 13


def _price(item: dict) -> str:
    p = item.get("price")
    if p is None:
        return ""
    cur = item.get("currency") or "RON"
    return f"{round(float(p)):,}".replace(",", ".") + f" {cur}"


def build_auto_xlsx(rows: Iterable[dict]) -> bytes:
    """rows = iterable de dict-uri cu cheile: title, platform, grade, price, currency,
    year, km, fuel_type, location, seller_name, keyword_name, listed_at, found_at,
    status, url."""
    table = []
    for it in rows:
        table.append([
            it.get("title") or "",
            _PLATFORM_LABELS.get(it.get("platform"), (it.get("platform") or "")),
            it.get("grade") or "",
            _price(it),
            it.get("year") or "",
            it.get("km") if it.get("km") is not None else "",
            it.get("fuel_type") or "",
            it.get("location") or "",
            it.get("seller_name") or "",
            it.get("keyword_name") or "",
            fmt_dt(it.get("listed_at")),
            fmt_dt(it.get("found_at")),
            it.get("status") or "",
            it.get("url") or "",
        ])
    return build_generic_xlsx(
        _COLUMNS, table, hyperlink_col_idx=_URL_COL_IDX,
        row_fill_fn=lambda r: GRADE_FILLS.get(r[2]),
        sheet_title="Anunțuri Auto",
    )
