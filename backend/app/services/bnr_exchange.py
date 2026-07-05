"""BNR daily EUR/RON rate — fetched once per day, cached in memory."""
import xml.etree.ElementTree as ET
from datetime import date
from curl_cffi.requests import Session

_cache: dict = {}
# Feed-ul oficial de cursuri de referinta BNR (XML). Vechiul `nbrfx.aspx` NU era
# feed-ul XML, ci o pagina — de aceea ET.fromstring esua mereu si get_eur_ron() se
# intorcea silentios pe fallback-ul 5.0. Acesta e URL-ul documentat oficial de BNR.
_BNR_URL = "https://www.bnr.ro/nbrfxrates.xml"


def _parse(xml_text: str) -> dict:
    """Extrage {currency: RON_per_unitate} din XML-ul BNR.

    Namespace-agnostic: match dupa local-name `Rate`, ca sa nu depinda de valoarea
    exacta a atributului xmlns al feed-ului (ex. "http://www.bnr.ro/xsd"). Respecta
    atributul `multiplier` (unele valute — HUF, JPY — sunt cotate per 100/1000);
    EUR nu are multiplier, deci ramane cursul direct RON/EUR.
    """
    root = ET.fromstring(xml_text)
    rates: dict = {}
    for el in root.iter():
        # tag-ul poate fi "{http://www.bnr.ro/xsd}Rate" — luam doar local-name-ul.
        if el.tag.rsplit("}", 1)[-1] != "Rate":
            continue
        cur = el.get("currency")
        if not cur or not (el.text and el.text.strip()):
            continue
        try:
            val = float(el.text)
            mult = float(el.get("multiplier") or 1) or 1
            rates[cur] = val / mult
        except (TypeError, ValueError):
            continue
    return rates


def _fetch() -> dict:
    try:
        with Session(impersonate="chrome124") as s:
            r = s.get(_BNR_URL, timeout=10)
        return _parse(r.text)
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
