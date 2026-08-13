"""Comune pentru toate scraperele Radar Marketplace.

User-Agent rotation, exponential backoff la rate-limit, filtru de cuvinte
excluse pe titlu. Centralizat aici ca sa fie consistent intre OLX, Vinted,
Okazii si Facebook si ca scrapere viitoare sa nu re-inventeze logica.
"""
import os
import random
from enum import Enum
from typing import Optional


def build_headers(extra: dict | None = None) -> dict:
    """Headers proprii — DOAR ce nu poate pune curl_cffi din profilul impersonat.

    Masurat pe httpbin (2026-08-13): cu `impersonate=<profil>`, curl_cffi trimite
    singur setul complet si COERENT al browserului — User-Agent, Sec-Ch-Ua* (cu
    versiunea si platforma potrivite), Accept cu avif/webp/apng, Accept-Encoding cu
    zstd, Sec-Fetch-*, Upgrade-Insecure-Requests, Priority. Header-ele date de noi
    doar SUPRASCRIU cheile lor, restul raman.

    Vechea implementare rotea un User-Agent dintr-o lista care continea si Firefox si
    Edge, peste o amprenta TLS/HTTP2 de Chrome. Rezultatul masurat era o contradictie
    pe care niciun browser real n-o poate produce si pe care serverul o vede direct:
        User-Agent: ... Firefox/130.0
        Sec-Ch-Ua:  "Chromium";v="146", "Google Chrome";v="146"
    Plus Accept/Accept-Encoding de Chrome vechi (fara zstd/avif) si `Connection:
    keep-alive`, ilegal pe HTTP/2. Adica exact semnalele pe care impersonarea le
    elimina. Acum nu mai suprascriem nimic din ele.

    Ramane doar `Accept-Language`: nu contrazice amprenta (e o preferinta de
    utilizator) si conteaza pe site-urile RO, care servesc continut dupa ea.
    `extra` (Referer, X-Requested-With etc.) ramane suveran, ca inainte.
    """
    headers = {
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
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


# SCRAPE-AUDIT: fara plierea diacriticelor, "mașină" din lista de excluderi nu
# prindea "masina" din titlu (si invers) — modul simplu e calea IMPLICITA a
# tuturor platformelor. Modul advanced (exclusion_engine) normaliza deja.
_ACCENT_MAP = str.maketrans("ăâîșşțţ", "aaisstt")


def _fold(text: str) -> str:
    return (text or "").lower().translate(_ACCENT_MAP)


def is_excluded(title: str, exclude_words: list[str]) -> bool:
    """True daca titlul contine vreun cuvant din lista (case- si diacritice-insensitive)."""
    if not exclude_words:
        return False
    if not title:
        return False
    title_low = _fold(title)
    for w in exclude_words:
        w = _fold((w or "").strip())
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
    reincerca imediat pe alt IP — NET-5.3: doar cand rotatia chiar a schimbat WAN-ul.

    Import lazy in corp: base_scraper NU capata dependente la nivel de modul.
    Nu arunca niciodata - un defect in telemetrie nu are voie sa opreasca un scan.
    """
    try:
        if outcome is Outcome.BLOCKED:
            from app.services.radar import health_watchdog
            health_watchdog.note_blocked(platform)
            from app.services.network.triggers import rotate_for
            return rotate_for(platform, outcome)
    except Exception:
        pass
    return False
