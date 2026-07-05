"""Comune pentru scraperele imobiliare (OLX, Storia, Imobiliare.ro, Facebook).

curl_cffi (impersonate="chrome131") + BeautifulSoup. Forma standard a rezultatului
este aliniata cu modelul RealEstateListing.
"""
import random
import re
import unicodedata
from typing import Optional

IMPERSONATE = "chrome131"
MAX_RESULTS = 50


def norm_city_slug(name) -> str:
    """Normalizeaza numele unui oras la slug ascii: fara diacritice, lowercase, spatii -> '-'.

    ex. "București" -> "bucuresti", "Cluj-Napoca" -> "cluj-napoca". Aceeasi logica exacta ca
    storia_scraper._loc_key (extrasa aici ca helper comun; storia isi pastreaza copia proprie —
    nu o modificam in acest task). Necesara pentru path-urile de oras (site-urile .ro nu rezolva
    slug-urile cu diacritice).
    """
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return s.strip().lower().replace(" ", "-")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def build_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    if extra:
        headers.update(extra)
    return headers


def parse_price(raw) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[^\d.,]", "", str(raw)).replace(".", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def parse_int(raw) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    digits = re.sub(r"[^\d]", "", str(raw))
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


def extract_rooms(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d+)\s*camer", text, re.I)
    return int(m.group(1)) if m else None


def extract_surface(text: Optional[str]) -> Optional[float]:
    """Extrage suprafata in mp ('65 mp', '65 m²', '65,5 mp')."""
    if not text:
        return None
    m = re.search(r"([\d.,]+)\s*(?:mp|m²|m2|metri)", text, re.I)
    if not m:
        return None
    return parse_price(m.group(1))


def detect_currency(text: Optional[str]) -> str:
    if not text:
        return "EUR"
    t = text.lower()
    if "lei" in t or "ron" in t:
        return "RON"
    return "EUR"


def make_re_listing(
    *,
    platform: str,
    external_id: Optional[str] = None,
    tip_anunt: Optional[str] = None,
    tip_proprietate: Optional[str] = None,
    camere: Optional[int] = None,
    suprafata_mp: Optional[float] = None,
    etaj: Optional[str] = None,
    pret: Optional[float] = None,
    moneda: str = "EUR",
    locatie_judet: Optional[str] = None,
    locatie_oras: Optional[str] = None,
    an_constructie: Optional[int] = None,
    facilitati: Optional[dict] = None,
    titlu: Optional[str] = None,
    descriere: Optional[str] = None,
    source_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    listed_at: Optional[str] = None,
) -> dict:
    """Forma standard a unui anunt imobiliar (aliniata cu RealEstateListing)."""
    return {
        "platform": platform,
        "external_id": external_id,
        "tip_anunt": tip_anunt,
        "tip_proprietate": tip_proprietate,
        "camere": camere,
        "suprafata_mp": suprafata_mp,
        "etaj": etaj,
        "pret": pret,
        "moneda": moneda,
        "locatie_judet": locatie_judet,
        "locatie_oras": locatie_oras,
        "an_constructie": an_constructie,
        "facilitati": facilitati,
        "titlu": titlu,
        "descriere": descriere,
        "source_url": source_url,
        "thumbnail_url": thumbnail_url,
        "listed_at": listed_at,
    }
