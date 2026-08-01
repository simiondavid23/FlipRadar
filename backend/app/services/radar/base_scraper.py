"""Comune pentru toate scraperele Radar Marketplace.

User-Agent rotation, exponential backoff la rate-limit, filtru de cuvinte
excluse pe titlu. Centralizat aici ca sa fie consistent intre OLX, Vinted,
Okazii si Facebook si ca scrapere viitoare sa nu re-inventeze logica.
"""
import os
import random
from enum import Enum
from typing import Optional


_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def build_headers(extra: dict | None = None) -> dict:
    """Construieste headers realiste cu User-Agent rotit aleator."""
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if extra:
        headers.update(extra)
    return headers


def rate_limit_backoff(attempt: int, base_delay: float = 2.0) -> float:
    """Calculeaza delay-ul pentru retry exponential cu jitter.

    Folosit la 429 / blocaje temporare ca sa nu reincercam imediat
    si sa amplificam blocajul.
    """
    return base_delay * (2 ** attempt) + random.uniform(0, 1)


def get_proxy_config() -> Optional[dict]:
    """Citeste configuratia proxy din variabilele de mediu.

    Returneaza None daca proxy-ul nu e activat sau host-ul lipseste. Altfel
    returneaza un dict {"http": url, "https": url, "username", "password",
    "host", "port"} folosibil atat cu curl_cffi/requests cat si cu Playwright
    (care vrea username/password separat).
    """
    enabled = os.environ.get("PROXY_ENABLED", "false").lower() in ("1", "true", "yes")
    host = os.environ.get("PROXY_HOST", "").strip()
    port = os.environ.get("PROXY_PORT", "").strip()
    user = os.environ.get("PROXY_USER", "").strip()
    pwd = os.environ.get("PROXY_PASS", "").strip()
    if not enabled or not host:
        return None
    if port:
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if user:
        url = f"http://{user}:{pwd}@{netloc}"
    else:
        url = f"http://{netloc}"
    return {
        "http": url,
        "https": url,
        "username": user,
        "password": pwd,
        "host": host,
        "port": port,
    }


def is_excluded(title: str, exclude_words: list[str]) -> bool:
    """True daca titlul contine vreun cuvant din lista (case-insensitive)."""
    if not exclude_words:
        return False
    if not title:
        return False
    title_low = title.lower()
    for w in exclude_words:
        w = (w or "").strip().lower()
        if w and w in title_low:
            return True
    return False


# ── NET-5.1 — clasificator de blocaje ────────────────────────────────────────────
# „Platforma a returnat 0" nu spune nimic: poate fi blocaj, markup schimbat sau chiar
# zero rezultate reale. Clasificatorul separa cazurile ca alertele sa fie precise.


class Outcome(str, Enum):
    """Rezultatul unui request in termeni de DIAGNOSTIC, nu de HTTP.

    Baza `str`: se logheaza si se serializeaza direct, fara `.value` peste tot.
    """
    OK = "ok"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    SITE_CHANGED = "site_changed"
    TRANSIENT = "transient"
    NOT_FOUND = "not_found"


BLOCK_MARKERS: tuple[str, ...] = (
    "captcha-delivery", "cf-challenge", "<title>just a moment",
    "imperva", "incapsula", "access denied", "zugriff verweigert",
)
# „just a moment" e ancorat pe <title> pentru ca e singura expresie englezeasca
# obisnuita din lista: intr-o descriere de vanzator sub 40 KB ar clasifica pagina
# BLOCKED si, pe Vinted, ar arma breaker-ul de 6 ore. Cloudflare serveste exact
# `<title>Just a moment...</title>`, deci ancora pe titlu e si specifica, si suficienta
# (varianta „just a moment..." cu puncte tot ar prinde proza: „just a moment... hai sa vad").

# Pagina reala e mare; substringul "datadome" apare si in SDK-ul client de pe
# pagina normala. Peste pragul asta, prezenta markerilor nu mai e concludenta.
INTERSTITIAL_MAX_BYTES = 40_000


def _has_block_marker(low: str, markers: tuple[str, ...]) -> bool:
    """`datadome` SINGUR nu e marker (SDK-ul client apare si pe pagina buna) —
    conteaza doar impreuna cu `captcha`."""
    if any(m in low for m in markers):
        return True
    return "datadome" in low and "captcha" in low


def classify(
    status: Optional[int] = None,
    body: Optional[str] = None,
    exc: Optional[BaseException] = None,
    parsed: Optional[int] = None,
    extra_markers: Optional[tuple[str, ...]] = None,
    interstitial_max_bytes: int = INTERSTITIAL_MAX_BYTES,
) -> Outcome:
    """Clasifica rezultatul unui request de scraper.

    ORDINEA de decizie e parte din contract, nu detaliu de implementare: un 429 cu
    markeri in body ramane RATE_LIMITED (altfel am reincerca gresit), iar un 403 e
    BLOCKED indiferent ce contine body-ul.

    `parsed is None` inseamna „nu s-a parsat inca", NU zero — doar `parsed == 0`
    inseamna markup schimbat. `extra_markers` se ADAUGA la cele comune.
    """
    if exc is not None:
        return Outcome.TRANSIENT
    if status == 404:
        return Outcome.NOT_FOUND
    if status in (401, 403):
        return Outcome.BLOCKED
    if status == 429:
        return Outcome.RATE_LIMITED
    if status is not None and status >= 500:
        return Outcome.TRANSIENT
    if status == 200:
        markers = BLOCK_MARKERS + tuple(extra_markers or ())
        if body and len(body) < interstitial_max_bytes and _has_block_marker(
                body.lower(), markers):
            return Outcome.BLOCKED
        if parsed is not None and parsed == 0:
            return Outcome.SITE_CHANGED
    return Outcome.OK


def report_outcome(platform: str, outcome: "Outcome") -> bool:
    """Raporteaza rezultatul unui request. Intoarce True daca apelantul poate
    reincerca imediat pe alt IP (in 5.1 intotdeauna False - rotatia vine in 5.3).

    Import lazy in corp: base_scraper NU capata dependente la nivel de modul.
    Nu arunca niciodata - un defect in telemetrie nu are voie sa opreasca un scan.
    """
    try:
        if outcome is Outcome.BLOCKED:
            from app.services.radar import health_watchdog
            health_watchdog.note_blocked(platform)
    except Exception:
        pass
    return False
