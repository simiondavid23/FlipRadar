"""BNR daily EUR/RON rate — fetched once per day, cached in memory."""
import xml.etree.ElementTree as ET
from datetime import date
from curl_cffi.requests import Session

_cache: dict = {}
_BNR_URL = "https://www.bnr.ro/nbrfx.aspx"


def _fetch() -> dict:
    try:
        with Session(impersonate="chrome124") as s:
            r = s.get(_BNR_URL, timeout=10)
        root = ET.fromstring(r.text)
        ns = {"b": "http://www.bnr.ro/xsd"}
        return {
            el.get("currency"): float(el.text)
            for el in root.findall(".//b:Rate", ns)
            if el.text
        }
    except Exception as e:
        print(f"[BNR] fetch error: {e}")
        return {}


def get_eur_ron() -> float:
    today = date.today()
    if _cache.get("_date") == today and "EUR" in _cache:
        return _cache["EUR"]
    rates = _fetch()
    if rates:
        _cache.update(rates)
        _cache["_date"] = today
    return _cache.get("EUR", 5.0)
