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


# ── FBS-11 — comparatiile de pret devin constiente de moneda ─────────────────────
# Pana aici, un anunt la 500 EUR era „sub" un prag de 3000 RON pur si simplu fiindca
# 500 < 3000. Pragurile keyword-urilor Radar sunt de facto RON, deci comparatia trebuie
# facuta in RON — nu in numere fara unitate.
# FBS-12: USD a intrat aici odata cu `bnr_exchange.get_usd_ron` — era deja emis de
# parsere si deja suportat de `currency_service`, lipsea doar adaptorul.
_MONEDE_CONVERTIBILE = {"RON", "EUR", "USD"}


def normalizeaza_moneda(currency) -> str:
    """Codul de moneda, majuscule si fara spatii: „eur ", „EUR", „ Eur" -> „EUR"."""
    return (currency or "").strip().upper()


def moneda_convertibila(currency) -> bool:
    """True daca stim sa aducem moneda in RON: RON prin identitate, EUR si USD prin curs.

    Exista ca apelantul sa poata DEOSEBI cele doua motive pentru care
    `pret_comparabil_ron` intoarce None — moneda pe care n-o stim (D2) fata de cursul
    care n-a raspuns (D3) — fara sa-si tina o a doua lista de monede, care ar diverge.
    """
    return normalizeaza_moneda(currency) in _MONEDE_CONVERTIBILE


def pret_comparabil_ron(price, currency):
    """Pretul in RON PENTRU COMPARATIE, sau None daca nu se poate compara.

    FBS-11. Trei decizii, toate ale lui David:
      * D1 — EUR si USD se convertesc cu cursul BNR INAINTE de comparatia cu
        pragurile; RON trece prin identitate. Pragurile raman semantic RON, cum sunt
        azi. (USD s-a adaugat la FBS-12, odata cu parserele care spun adevarul despre
        moneda — pana atunci trecea permisiv.)
      * D2 — o moneda pe care n-o stim (GBP, CHF, orice cod de trei litere pe care
        parserele il raporteaza acum onest) da None, iar apelantul lasa anuntul sa
        TREACA de portile de pret. „Prefer sa nu pierd nimic daca exista sansa sa fie
        un deal bun" — permisiv, dar numarat.
      * D3 — daca cursul nu raspunde, tot None: filtrarea nu are voie sa pice fiindca
        BNR-ul e indisponibil. E o garda DEFENSIVA, nu reproducerea unui esec observat:
        lantul din `currency_service` se termina in fallback static si apoi in 1.0, deci
        `get_eur_ron` nu ridica pe caile cunoscute. Garda exista fiindca „nu ridica azi"
        nu e o proprietate pe care s-o putem sprijini.

    Valoarea intoarsa e DOAR pentru comparatie — pretul AFISAT al anuntului ramane cel
    original, in moneda lui.

    Apelul e prin MODUL (`bnr_exchange.get_eur_ron()`), nu printr-un nume importat: e
    exact avertismentul din docstring-ul lui `bnr_exchange`, si tot el face cursul
    inlocuibil din teste.
    """
    if not isinstance(price, (int, float)):
        return None
    moneda = normalizeaza_moneda(currency)
    if moneda == "RON":
        return float(price)
    if moneda not in _MONEDE_CONVERTIBILE:
        return None                                   # D2
    from app.services import bnr_exchange             # local: evita ciclul la import
    try:
        curs = (bnr_exchange.get_eur_ron() if moneda == "EUR"
                else bnr_exchange.get_usd_ron())
    except Exception:                                 # noqa: BLE001 — D3, orice esec
        return None
    if not isinstance(curs, (int, float)) or curs <= 0:
        return None                                   # curs absurd = curs indisponibil
    return float(price) * float(curs)


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
    # CLS-1 — provocarea JS Akamai Bot Manager, servita cu HTTP 200 (masurat pe
    # mobile.de, SONDA-AUTO 2026-09-03: ~2,7 KB, deci sub prag, dar niciun marker
    # vechi nu o prindea si `classify` o dadea OK). Doar id-uri/clase proprii ale
    # paginii de provocare: „akamai" singur apare si pe pagini bune (CDN/SDK), la
    # fel ca „datadome", iar „protected by" e proza.
    "sec-if-cpt-container", "scf-akamai-protected-by",
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
