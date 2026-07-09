"""Acces la pagina HTML a itemelor Vinted (Next.js App Router) prin curl_cffi.

RP-1: endpointul JSON de detaliu (`/api/v2/items/{id}/details`) da 403 inclusiv pe
sesiune noua (dovedit in RP-DIAG). Ne pivotam pe pagina HTML a itemului, servita
200 cu `impersonate="chrome131"`. Datele SSR sunt in chunk-uri
`self.__next_f.push([1,"...escaped..."])` (format React Flight) — le decodam si le
concatenam intr-un singur text pe care extractoarele il parcurg.

Modul REUTILIZABIL: enrichment-ul Vinted (vinted_scraper) si viitorul refresh de
catalog (RP-2) trec toate prin aceeasi sesiune singleton + limiter per domeniu.
"""
import json
import random
import re
import threading
import time
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

from app.services.log_manager import log_manager


_IMPERSONATE = "chrome131"
# Doar Accept-Language adaugat — UA ramane cel al impersonarii (un UA custom ar
# strica potrivirea cu fingerprintul TLS si ne-ar bloca).
_ACCEPT_LANG = {"Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"}

# Interval minim intre requesturi catre acelasi domeniu (secunde). Vinted e sensibil
# la rate-limit pe pagina HTML -> >=6s + jitter.
_MIN_INTERVAL = {"vinted.ro": 6.0}
_DEFAULT_MIN_INTERVAL = 3.0

_session = None
_session_lock = threading.Lock()
_domain_last: dict[str, float] = {}
_domain_lock = threading.Lock()


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


def _rate_limit(domain: str) -> None:
    """Impune intervalul minim per domeniu + jitter, rezervand slotul sub lock si
    dormind IN AFARA lock-ului (nu blocheaza requesturile catre alt domeniu)."""
    min_iv = next((iv for d, iv in _MIN_INTERVAL.items() if domain.endswith(d)), _DEFAULT_MIN_INTERVAL)
    while True:
        with _domain_lock:
            now = time.time()
            wait = (_domain_last.get(domain, 0.0) + min_iv) - now
            if wait <= 0:
                _domain_last[domain] = now  # rezerva slotul curent
                return
        time.sleep(wait + random.uniform(0.1, 0.6))


def get_html(url: str, referer: str | None = None):
    """GET prin sesiunea singleton, respectand limiterul de domeniu."""
    _rate_limit(_domain_of(url))
    sess = get_html_session()
    headers = {"Referer": referer} if referer else None
    return sess.get(url, headers=headers)


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
    """Pagina HTML a unui item Vinted -> {"html", "decoded"} sau None la esec.

    Accepta un id numeric (construieste URL-ul canonic; redirectul adauga slug-ul)
    sau un URL complet. Trateaza 403/captcha ca esec logat.
    """
    s = str(item_id_or_url or "").strip()
    if not s:
        return None
    url = s if s.startswith("http") else f"https://www.vinted.ro/items/{s}"
    try:
        resp = get_html(url, referer="https://www.vinted.ro/")
        status = resp.status_code
        html = resp.text or ""
        if status != 200 or _looks_blocked(status, html):
            log_manager.emit("radar", "WARN",
                f"Vinted HTML: item inaccesibil (HTTP {status}, blocat={_looks_blocked(status, html)})")
            return None
        return {"html": html, "decoded": decode_next_f(html)}
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Vinted HTML: eroare fetch ({str(exc)[:100]})")
        return None
