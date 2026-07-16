"""Acces la pagina HTML a itemelor Vinted (Next.js App Router) prin curl_cffi.

RP-1: endpointul JSON de detaliu (`/api/v2/items/{id}/details`) da 403 inclusiv pe
sesiune noua (dovedit in RP-DIAG). Ne pivotam pe pagina HTML a itemului, servita
200 cu `impersonate="chrome131"`. Datele SSR sunt in chunk-uri
`self.__next_f.push([1,"...escaped..."])` (format React Flight) — le decodam si le
concatenam intr-un singur text pe care extractoarele il parcurg.

Modul REUTILIZABIL: enrichment-ul Vinted (vinted_scraper), on-demand din router si
refresh-ul de catalog (RP-2) trec TOATE prin `get_html` — deci guard-ul de mai jos
(throttle + plafon zilnic + circuit breaker) se aplica o singura data si acopera
automat toti apelantii.

RP-1.1 — incident real: enrichment la cadenta sustinuta (15/ciclu la 6s) a degradat
progresiv reputatia IP-ului la DataDome pana la 403 pe TOATE paginile HTML (search-ul
prin API-ul wrapper-ului = alt tier, a ramas ok). Fix: cadenta mai lenta cu jitter,
plafon zilnic, si un circuit breaker care OPRESTE requesturile cand incepe blocarea.

NOTA de stare: contoarele plafonului zilnic + starea breaker-ului sunt IN MEMORIE (per
proces) — se reseteaza la restart. Acceptat: un restart e rar si oricum reface sesiunea.
"""
import json
import random
import re
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager


_IMPERSONATE = "chrome131"
# Doar Accept-Language adaugat — UA ramane cel al impersonarii (un UA custom ar
# strica potrivirea cu fingerprintul TLS si ne-ar bloca).
_ACCEPT_LANG = {"Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"}

# ── Guard per domeniu (constante documentate, usor de ajustat) ──────────────────
_MIN_INTERVAL = {"vinted.ro": 20.0}      # era 6.0 (RP-1) — cadenta mai lenta
_DEFAULT_MIN_INTERVAL = 3.0
_JITTER_MAX = {"vinted.ro": 10.0}        # interval efectiv Vinted: 20–30s
_DEFAULT_JITTER_MAX = 1.0
_DAILY_CAP = {"vinted.ro": 250}          # requesturi HTML / zi calendaristica
_BREAKER_THRESHOLD = 2                    # blocked-uri consecutive -> breaker deschis
_BREAKER_COOLDOWN_S = 6 * 3600           # pauza dupa deschidere

# ── Ceas/sleep injectabile (monkeypatch in teste, fara retea/sleep real) ────────
def _now() -> float:
    return time.time()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


# ── Stare (thread-safe) ─────────────────────────────────────────────────────────
_session = None
_session_lock = threading.Lock()
# limiter: momentul-tinta al urmatorului request permis per domeniu
_domain_next_ts: dict[str, float] = {}
_domain_lock = threading.Lock()
# guard: breaker + plafon zilnic
_guard_lock = threading.Lock()
_breaker: dict[str, dict] = {}                 # {domeniu: {consec, open_until, half_open, warned_skip}}
_daily: dict[str, tuple[str, int]] = {}        # {domeniu: (data_azi, count)}
_daily_cap_warned: dict[str, str] = {}         # {domeniu: data_ultimului_warn}


def _new_breaker() -> dict:
    return {"consec": 0, "open_until": 0.0, "half_open": False, "warned_skip": False}


def get_html_session() -> "curl_requests.Session":
    """Sesiune curl_cffi singleton, thread-safe, cu fingerprint chrome131."""
    global _session
    with _session_lock:
        if _session is None:
            _session = curl_requests.Session(
                impersonate=_IMPERSONATE, timeout=20, allow_redirects=True
            )
            _session.headers.update(_ACCEPT_LANG)
        return _session


def _domain_of(url: str) -> str:
    return (urlparse(url).netloc or "").replace("www.", "")


def _min_interval_for(domain: str) -> float:
    return next((iv for d, iv in _MIN_INTERVAL.items() if domain.endswith(d)), _DEFAULT_MIN_INTERVAL)


def _jitter_for(domain: str) -> float:
    return next((j for d, j in _JITTER_MAX.items() if domain.endswith(d)), _DEFAULT_JITTER_MAX)


def _cap_for(domain: str):
    return next((c for d, c in _DAILY_CAP.items() if domain.endswith(d)), None)


def _today_str() -> str:
    return datetime.fromtimestamp(_now()).strftime("%Y-%m-%d")


def _rate_limit(domain: str) -> None:
    """Throttle per domeniu: pastreaza intre requesturi consecutive un interval de
    `min_interval + uniform(0, jitter_max)`. Rezerva slotul sub lock, doarme in afara
    lui (nu blocheaza alt domeniu). Ceas/sleep injectabile (_now/_sleep)."""
    min_iv = _min_interval_for(domain)
    jitter = _jitter_for(domain)
    while True:
        with _domain_lock:
            now = _now()
            target = _domain_next_ts.get(domain, 0.0)
            if now >= target:
                # rezerva: urmatorul request permis la now + min_iv + jitter
                _domain_next_ts[domain] = now + min_iv + random.uniform(0, jitter)
                return
            wait = target - now
        _sleep(wait)


# ── Guard: circuit breaker + plafon zilnic (factorizat pentru teste) ────────────
def guard_before_request(domain: str) -> dict:
    """Decizie INAINTE de un request REAL (apelata din get_html sub lock propriu).
    Efecte laterale: rezerva slotul zilnic daca permite; marcheaza proba half-open.
    Returneaza {"allowed", "reason": None|"breaker_open"|"daily_cap", "open_until"}."""
    with _guard_lock:
        b = _breaker.setdefault(domain, _new_breaker())
        now = _now()

        # 1) breaker DESCHIS (cooldown neexpirat) -> skip
        if b["open_until"] > now:
            if not b["warned_skip"]:
                b["warned_skip"] = True
                log_manager.emit("radar", "INFO",
                    f"Vinted breaker DESCHIS — requesturi HTML in pauza pana la reincercarea de proba ({domain})")
            return {"allowed": False, "reason": "breaker_open", "open_until": b["open_until"]}

        # breaker in fereastra HALF-OPEN (a expirat cooldown-ul): lasa UN singur request de proba
        if b["open_until"] > 0:  # (si <= now, implicat de mai sus)
            if b["half_open"]:
                return {"allowed": False, "reason": "breaker_open", "open_until": b["open_until"]}
            b["half_open"] = True  # aceasta cerere e proba

        # 2) plafon zilnic
        cap = _cap_for(domain)
        if cap is not None:
            today = _today_str()
            date, count = _daily.get(domain, (today, 0))
            if date != today:
                date, count = today, 0
            if count >= cap:
                _daily[domain] = (date, count)
                if b["half_open"]:
                    b["half_open"] = False  # nu trimitem proba daca plafonul e atins
                if _daily_cap_warned.get(domain) != today:
                    _daily_cap_warned[domain] = today
                    log_manager.emit("radar", "WARN",
                        f"Plafon zilnic Vinted atins ({cap}) — enrichment in pauza pana maine ({domain})")
                return {"allowed": False, "reason": "daily_cap", "open_until": 0.0}
            _daily[domain] = (date, count + 1)

        return {"allowed": True, "reason": None, "open_until": b["open_until"]}


def guard_after_response(domain: str, blocked: bool) -> None:
    """Actualizeaza breaker-ul DUPA un raspuns (apelata din get_html)."""
    with _guard_lock:
        b = _breaker.setdefault(domain, _new_breaker())
        now = _now()
        was_half_open = b["half_open"]
        b["half_open"] = False
        if blocked:
            b["consec"] += 1
            if was_half_open:
                b["open_until"] = now + _BREAKER_COOLDOWN_S
                b["warned_skip"] = False
                log_manager.emit("radar", "WARN",
                    f"Vinted breaker re-DESCHIS {_BREAKER_COOLDOWN_S // 3600}h (proba half-open a esuat) ({domain})")
            elif b["consec"] >= _BREAKER_THRESHOLD and b["open_until"] <= now:
                b["open_until"] = now + _BREAKER_COOLDOWN_S
                b["warned_skip"] = False
                log_manager.emit("radar", "WARN",
                    f"Vinted breaker DESCHIS {_BREAKER_COOLDOWN_S // 3600}h ({_BREAKER_THRESHOLD}×403 consecutive) ({domain})")
        else:
            if was_half_open:
                log_manager.emit("radar", "OK", f"Vinted breaker INCHIS (proba a reusit) ({domain})")
            b["consec"] = 0
            b["open_until"] = 0.0
            b["warned_skip"] = False


def _release_half_open(domain: str) -> None:
    """Elibereaza slotul de proba half-open (ex. eroare de retea) fara a-l numara ca blocat."""
    with _guard_lock:
        b = _breaker.get(domain)
        if b:
            b["half_open"] = False


def guard_status(domain: str) -> dict:
    """Stare READ-ONLY pentru apelanti (ex. scanner-ul, inainte de un batch): decid
    FARA sa declanseze un request. Nu consuma plafonul, nu porneste proba half-open."""
    with _guard_lock:
        b = _breaker.get(domain, _new_breaker())
        now = _now()
        if b["open_until"] > now:
            return {"allowed": False, "reason": "breaker_open", "open_until": b["open_until"]}
        cap = _cap_for(domain)
        if cap is not None:
            today = _today_str()
            date, count = _daily.get(domain, (today, 0))
            if date == today and count >= cap:
                return {"allowed": False, "reason": "daily_cap", "open_until": 0.0}
        return {"allowed": True, "reason": None, "open_until": b.get("open_until", 0.0)}


def get_html(url: str, referer: str | None = None):
    """GET prin sesiunea singleton, respectand guard-ul (breaker + plafon zilnic) si
    throttle-ul cu jitter. Intoarce raspunsul sau `None` la SKIP (breaker/plafon) —
    motivul e interogabil prin `guard_status(domain)`. La 403/blocat, actualizeaza breaker-ul."""
    domain = _domain_of(url)
    decision = guard_before_request(domain)
    if not decision["allowed"]:
        return None  # marker de skip (get_html NU face HTTP)

    _rate_limit(domain)
    sess = get_html_session()
    headers = {"Referer": referer} if referer else None
    try:
        resp = sess.get(url, headers=headers)
    except Exception:
        _release_half_open(domain)  # eroare de retea: nu o numaram ca blocaj DataDome
        raise
    try:
        blocked = _looks_blocked(resp.status_code, resp.text or "")
    except Exception:
        blocked = False
    guard_after_response(domain, blocked)
    return resp


def decode_next_f(html: str) -> str:
    """Decodeaza chunk-urile RSC `self.__next_f.push([1,"..."])` intr-un singur text.

    Fiecare captura e un string JSON escapat -> `json.loads('"' + s + '"')`. Sarim
    chunk-urile care nu decodeaza. Rezultatul e concatenarea payload-urilor SSR
    (contine obiectele plugin item: user_info_header, attributes, gallery, ...).
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', html or "")
    parts: list[str] = []
    for c in chunks:
        try:
            parts.append(json.loads('"' + c + '"'))
        except Exception:
            continue
    return "".join(parts)


def _looks_blocked(status: int, html: str) -> bool:
    """Pagina reala e mare; substringul 'datadome' e doar SDK-ul client. Block real
    = 403 sau interstitial mic cu markeri de challenge."""
    low = (html or "").lower()
    if status == 403:
        return True
    if status == 200 and len(html) < 40000 and (
            "captcha-delivery" in low or ("datadome" in low and "captcha" in low)):
        return True
    return False


def fetch_item_page(item_id_or_url) -> dict | None:
    """Pagina HTML a unui item Vinted -> {"html", "decoded"} sau None la esec/skip.

    Accepta un id numeric (construieste URL-ul canonic; redirectul adauga slug-ul)
    sau un URL complet. `get_html` poate intoarce None (guard: breaker/plafon) — il
    tratam ca orice esec (None), deci contractul lui `get_vinted_item_detail` (si al
    router-ului/frontend-ului) ramane neschimbat.

    RAD-1: itemul sters/vandut (404 curat, fara semnatura de blocare) intoarce
    {"gone": True} — distinct de None, care ramane "esec, reincearca".
    """
    s = str(item_id_or_url or "").strip()
    if not s:
        return None
    url = s if s.startswith("http") else f"https://www.vinted.ro/items/{s}"
    try:
        resp = get_html(url, referer="https://www.vinted.ro/")
        if resp is None:
            return None  # skip din guard (breaker/plafon) — logat deja acolo
        status = resp.status_code
        html = resp.text or ""
        if status != 200 or _looks_blocked(status, html):
            if status == 404 and not _looks_blocked(status, html):
                # RAD-1 — item sters/vandut pe Vinted: propagam distinct, ca apelantul sa
                # marcheze listingul removed si sa-l scoata din coada de enrichment (altfel
                # e reincercat la nesfarsit si arde plafonul zilnic).
                return {"gone": True}
            log_manager.emit("radar", "WARN",
                f"Vinted HTML: item inaccesibil (HTTP {status}, blocat={_looks_blocked(status, html)})")
            return None
        return {"html": html, "decoded": decode_next_f(html)}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Vinted HTML: eroare fetch ({str(exc)[:100]})")
        return None
