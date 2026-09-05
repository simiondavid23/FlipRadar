"""
Serviciu de conversie valutară folosind cursurile oficiale BNR (Banca Națională a României).
Descarcă cursurile de la https://curs.bnr.ro/nbrfxrates.xml și le ține în memorie + pe disc.

BNR-1 (2026-08-13) — DOUA schimbari structurale:
  * Feed-ul s-a MUTAT de pe www.bnr.ro pe subdomeniul curs.bnr.ro. Adresa veche
    raspunde in continuare cu 200, dar corpul e HTML (pagina noului site, ~119 KB),
    deci parsarea esua mereu. Masurat pe 2026-08-13 la toate profilurile de
    impersonare: adresa noua da 1796 de octeti, text/xml, 37 de rate, sub 0.11s.
  * Modulul devine IMPLEMENTAREA UNICA a cursului valutar din aplicatie.
    `app.services.bnr_exchange.get_eur_ron()` era un al doilea fetch+cache paralel
    (folosit de Radar/Auto/Imobiliare in scoring) si a devenit un adaptor subtire
    peste `get_eur_ron_rate()` de aici. O singura sursa = un singur URL de intretinut.
"""
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Dict, Optional, Tuple

from curl_cffi import requests as curl_requests

from app.config import DATA_DIR
from app.utils.http_profile import impersonate_for


# Feed-ul oficial de cursuri de referinta BNR (XML), pe subdomeniul nou.
_BNR_URL = "https://curs.bnr.ro/nbrfxrates.xml"

_CACHE: Dict[str, float] = {}
_CACHE_TIMESTAMP: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 6 * 3600  # 6 hours

# Backoff pe esec: `get_eur_ron_rate()` e apelat PER ANUNT in buclele de scorare
# (Radar/Auto/Imobiliare). Fara backoff, un BNR cazut ar adauga timeout-ul de 10s la
# fiecare anunt scorat — o scanare de 200 de anunturi ar dura peste jumatate de ora.
_FETCH_RETRY_SECONDS = 600
_LAST_FETCH_FAILURE = 0.0

# Persistenta pe disc: acopera pornirea LA RECE cu BNR picat (proces nou, memoria
# goala, dar cursul de ieri exista pe disc). Vechimea maxima acceptata e configurabila.
_DISK_FILENAME = "curs_bnr.json"
_DEFAULT_MAX_STALE_DAYS = 7
_DISK_CACHE: Dict[str, float] = {}
_DISK_AGE_DAYS: Optional[int] = None
_DISK_LOADED = False

# Rate de rezervă folosite dacă BNR e inaccesibil ȘI nu există nimic în memorie/pe disc.
# Nivelurile masurate pe 2026-08-13 (EUR 5.2435, USD ~4.56); SEK setat in CUR-1.
_FALLBACK_EUR_RON = 5.24
_FALLBACK_USD_RON = 4.56
_FALLBACK_SEK_RON = 0.44

# Ultimul WARN per cheie — vezi `_warn`.
_WARN_TIMESTAMPS: Dict[str, float] = {}


def _warn(cheie: str, mesaj: str) -> None:
    """WARN cu prefixul `[CURS]`, cel mult unul per cheie la fiecare fereastra de backoff.

    Esecul complet TACIT (vechiul `return None` fara niciun semnal) a fost cauza pentru
    care mutarea feed-ului a trecut neobservata. Dar nici zgomotul nu e gratis: treptele
    de rezerva se aleg per APEL, iar apelurile vin per anunt scorat — un print necontrolat
    ar umple log-ul cu sute de linii identice per scanare. Deduparea pe aceeasi fereastra
    ca backoff-ul pastreaza semnalul (o linie la 10 minute, per motiv si per valuta) fara
    zgomot.
    """
    now = time.time()
    ultim = _WARN_TIMESTAMPS.get(cheie, 0.0)
    if ultim and (now - ultim) < _FETCH_RETRY_SECONDS:
        return
    _WARN_TIMESTAMPS[cheie] = now
    print(f"[CURS] {mesaj}")


def _parse(xml_text: str) -> Dict[str, float]:
    """Extrage {currency: RON_per_unitate} din XML-ul BNR.

    Namespace-agnostic: match dupa local-name `Rate`, ca sa nu depinda de valoarea
    exacta a atributului xmlns al feed-ului (ex. "http://www.bnr.ro/xsd"). Respecta
    atributul `multiplier` (unele valute — HUF, JPY — sunt cotate per 100/1000);
    EUR nu are multiplier, deci ramane cursul direct RON/EUR.
    """
    root = ET.fromstring(xml_text)
    rates: Dict[str, float] = {}
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


# ── Persistenta pe disc ─────────────────────────────────────────────────────────

def _max_stale_days() -> int:
    """Vechimea maxima acceptata a cache-ului de pe disc, citita la fiecare apel
    (nu la import) ca env-ul sa poata fi schimbat/monkeypatch-uit."""
    try:
        return max(0, int(os.getenv("CUR_MAX_STALE_DAYS", str(_DEFAULT_MAX_STALE_DAYS))))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_STALE_DAYS


def _disk_path():
    """Calea fisierului de cache. Se compune la APEL, nu la import, ca DATA_DIR sa
    poata fi monkeypatch-uit in teste."""
    return DATA_DIR / _DISK_FILENAME


def _save_to_disk(rates: Dict[str, float]) -> None:
    """Scrie atomic ratele proaspete: fisier temporar + `os.replace`.

    Atomic fiindca fisierul e citit la pornirea procesului: o scriere intrerupta
    (crash, kill) ar lasa un JSON trunchiat, adica exact scenariul in care ne-am baza
    pe el — cold start — ar fi cel stricat.
    """
    path = _disk_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": date.today().isoformat(), "rates": rates}
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:
        _warn("disc-scriere", f"nu am putut persista cursul in {path}: {e}")
        return
    # Tinem si vederea "de pe disc" sincronizata, ca sa nu ramana una veche in proces.
    global _DISK_LOADED, _DISK_AGE_DAYS
    _DISK_CACHE.clear()
    _DISK_CACHE.update(rates)
    _DISK_AGE_DAYS = 0
    _DISK_LOADED = True


def _read_disk_file() -> Tuple[Optional[Dict[str, float]], Optional[int]]:
    """Citeste fisierul de cache. Returneaza (rate, varsta_in_zile) sau (None, None)
    daca lipseste, e corupt sau e mai vechi decat pragul."""
    path = _disk_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = date.fromisoformat(raw["fetched_at"])
        rates = {str(k).upper(): float(v) for k, v in (raw.get("rates") or {}).items()}
    except FileNotFoundError:
        return None, None
    except Exception as e:
        _warn("disc-citire", f"cache-ul de pe disc {path} e corupt ({e}) — ignorat")
        return None, None

    if not rates:
        return None, None

    varsta = (date.today() - fetched_at).days
    prag = _max_stale_days()
    if varsta > prag:
        _warn(
            "disc-vechime",
            f"cache-ul de pe disc are {varsta} zile (peste pragul CUR_MAX_STALE_DAYS={prag}) — ignorat",
        )
        return None, None
    return rates, varsta


def _disk_rates() -> Dict[str, float]:
    """Ratele de pe disc, citite LENES o singura data pe proces."""
    global _DISK_LOADED, _DISK_AGE_DAYS
    if not _DISK_LOADED:
        _DISK_LOADED = True
        rates, varsta = _read_disk_file()
        _DISK_CACHE.clear()
        if rates:
            _DISK_CACHE.update(rates)
            _DISK_AGE_DAYS = varsta
    return _DISK_CACHE


# ── Fetch ───────────────────────────────────────────────────────────────────────

def _fetch_bnr_rates() -> Optional[Dict[str, float]]:
    """Descarcă XML-ul BNR și parsează toate ratele -> RON."""
    try:
        response = curl_requests.get(
            _BNR_URL, impersonate=impersonate_for("bnr"), timeout=10
        )
    except Exception as e:
        _warn("fetch", f"fetch BNR esuat ({type(e).__name__}: {e})")
        return None

    if response.status_code != 200:
        _warn("fetch", f"fetch BNR esuat (HTTP {response.status_code})")
        return None

    try:
        rates = _parse(response.text)
    except Exception as e:
        # Exact simptomul mutarii feed-ului: 200 + HTML in loc de XML.
        _warn("fetch", f"raspuns BNR neparsabil ({type(e).__name__}: {e})")
        return None

    if not rates:
        _warn("fetch", "raspuns BNR fara nicio rata")
        return None
    return rates


def _fetch_cu_backoff(now: float) -> Optional[Dict[str, float]]:
    """Incearca un fetch, dar nu mai des de o data la `_FETCH_RETRY_SECONDS` dupa un esec."""
    global _LAST_FETCH_FAILURE
    if _LAST_FETCH_FAILURE and (now - _LAST_FETCH_FAILURE) < _FETCH_RETRY_SECONDS:
        return None

    rates = _fetch_bnr_rates()
    if not rates:
        _LAST_FETCH_FAILURE = now
        return None

    _LAST_FETCH_FAILURE = 0.0
    _save_to_disk(rates)
    return rates


# ── Lantul de rezerva ───────────────────────────────────────────────────────────

def _rate_din_surse(currency: str, now: float) -> Optional[float]:
    """Treptele (a)-(d) ale lantului: cache proaspat > fetch BNR > cache EXPIRAT > disc.
    None daca moneda nu apare in NICIUNA dintre ele.

    Extras la CUR-1 ca `_get_rate` (care mai adauga peste el fallback-ul static si 1.0,
    de care depinde `convert`) si `get_rate_strict` (care NU adauga nimic) sa imparta
    exact acelasi lant, in loc sa-l duplice si sa divergheze in timp.
    """
    cached = _CACHE.get(currency)
    ts = _CACHE_TIMESTAMP.get(currency, 0)

    # (a) cache in memorie, proaspat
    if cached is not None and (now - ts) < _CACHE_TTL_SECONDS:
        return cached

    # (b) fetch BNR
    rates = _fetch_cu_backoff(now)
    if rates:
        for cur, rate in rates.items():
            _CACHE[cur] = rate
            _CACHE_TIMESTAMP[cur] = now
        if currency in rates:
            return rates[currency]

    # (c) cache in memorie, EXPIRAT
    if cached is not None:
        _warn(
            f"expirat:{currency}",
            f"BNR indisponibil — folosesc cursul expirat din memorie pentru {currency}",
        )
        return cached

    # (d) cache de pe disc (doar daca nu e mai vechi de CUR_MAX_STALE_DAYS)
    pe_disc = _disk_rates().get(currency)
    if pe_disc is not None:
        _warn(
            f"disc:{currency}",
            f"BNR indisponibil — folosesc cursul de pe disc pentru {currency} "
            f"(vechi de {_DISK_AGE_DAYS} zile)",
        )
        return pe_disc

    return None


def get_rate_strict(currency) -> Optional[float]:
    """Cursul moneda -> RON din SURSE REALE, sau None daca moneda nu e in nicio sursa.

    CUR-1. Diferenta fata de `_get_rate` e tot ce nu face: fara fallback static, fara
    1.0 la final. `_get_rate` are voie sa spuna „1:1" fiindca `convert` prefera o suma
    nealterata unei exceptii; portile de pret si scorarea NU au voie sa confunde „nu
    stiu moneda asta" cu „valoreaza cat un leu" — un anunt de 800 GBP tratat 1:1 ar
    trece drept 800 RON si ar primi un grad fals.
    """
    cod = (currency or "").strip().upper()
    if not cod:
        return None
    if cod == "RON":
        return 1.0
    return _rate_din_surse(cod, time.time())


def catalog_ron() -> Dict[str, float]:
    """Tot ce stim ACUM sa aducem in RON: {cod: curs}, cu "RON": 1.0 inclus.

    CUR-1. Sursa e cache-ul proaspat; daca e gol sau expirat, un fetch cu backoff; daca
    nici acela nu raspunde, discul. Fara static si fara 1.0 — un cod care lipseste de
    aici e un cod pe care apelantul TREBUIE sa-l trateze ca necunoscut.

    Spre deosebire de `_rate_din_surse`, treapta „cache EXPIRAT" nu are corespondent:
    pentru un instantaneu al INTREGULUI catalog, discul poarta acelasi continut ca
    ultimul fetch reusit, deci n-ar adauga informatie. In cel mai rau caz intoarce
    {"RON": 1.0}, iar apelantul decide (scorarea cade pe cursurile EUR/USD ale scanului).
    """
    now = time.time()
    proaspete = {c: r for c, r in _CACHE.items()
                 if (now - _CACHE_TIMESTAMP.get(c, 0)) < _CACHE_TTL_SECONDS}
    if not proaspete:
        rates = _fetch_cu_backoff(now)
        if rates:
            for cur, rate in rates.items():
                _CACHE[cur] = rate
                _CACHE_TIMESTAMP[cur] = now
            proaspete = dict(rates)
        else:
            proaspete = _disk_rates()
    catalog = {c: float(r) for c, r in proaspete.items()
               if isinstance(r, (int, float)) and r > 0}
    catalog["RON"] = 1.0
    return catalog


def _get_rate(currency: str) -> float:
    """Returnează rata de conversie valută -> RON (ex: EUR -> 5.24 înseamnă 1 EUR = 5.24 RON)."""
    currency = (currency or "").upper()
    if currency == "RON":
        return 1.0

    # Lantul de rezerva, de la cea mai buna informatie la cea mai slaba:
    #   (a) cache proaspat > (b) fetch BNR > (c) cache EXPIRAT > (d) disc > (e) static > 1.0
    # Cache-ul expirat e apararea reala pentru un proces care ruleaza de mult: ratele
    # valutare se misca lent, deci o rata de acum cateva ore bate orice constanta din cod.
    # Cache-ul de pe disc e aceeasi idee, dar peste repornire: acopera pornirea LA RECE.
    # Fallback-ul static ramane doar pentru cazul in care nu exista NIMIC masurat.
    # (a)-(d) stau in `_rate_din_surse`, partajat cu `get_rate_strict` (CUR-1).
    din_surse = _rate_din_surse(currency, time.time())
    if din_surse is not None:
        return din_surse

    # (e) fallback static
    if currency in ("EUR", "USD", "SEK"):
        static = {
            "EUR": _FALLBACK_EUR_RON,
            "USD": _FALLBACK_USD_RON,
            "SEK": _FALLBACK_SEK_RON,
        }[currency]
        _warn(
            f"static:{currency}",
            f"BNR indisponibil si nimic in memorie/pe disc — folosesc fallback-ul "
            f"static pentru {currency} ({static})",
        )
        return static

    # Ultimul resort pentru monede complet necunoscute. Semantica ramane
    # neschimbata pentru restul aplicatiei: 1:1, adica suma trece nealterata.
    _warn(f"unu-la-unu:{currency}", f"moneda necunoscuta {currency} — trece 1:1 in RON")
    return 1.0


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Converteste `amount` dintr-o moneda in alta folosind cursul valutar al BNR."""
    if amount is None:
        return 0.0
    from_currency = (from_currency or "RON").upper()
    to_currency = (to_currency or "RON").upper()
    if from_currency == to_currency:
        return round(amount, 2)

    # Converteste totul folosind RON ca referinta
    amount_ron = amount * _get_rate(from_currency)
    if to_currency == "RON":
        return round(amount_ron, 2)
    to_rate = _get_rate(to_currency)
    if to_rate == 0:
        return 0.0
    return round(amount_ron / to_rate, 2)


def get_eur_ron_rate() -> float:
    """Returnează cursul EUR -> RON curent (ex: 5.24)."""
    return _get_rate("EUR")


def get_all_rates() -> Dict[str, float]:
    """Returnează ratele EUR/USD -> RON din cache, actualizând dacă e necesar.

    Trece prin `_get_rate`, nu direct prin `_CACHE`: altfel treptele (c) cache expirat
    si (d) disc ar fi ocolite exact aici, iar Catalog/Gestiune ar vedea fallback-ul
    static in timp ce scorarea (prin `get_eur_ron_rate`) vede cursul real de pe disc.
    """
    return {
        "EUR_RON": _get_rate("EUR"),
        "USD_RON": _get_rate("USD"),
    }
