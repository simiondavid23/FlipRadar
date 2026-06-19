"""Comune pentru scraperele de anunturi auto (OLX Auto, Autovit, Mobile.de,
AutoScout24, Facebook, Kleinanzeigen). curl_cffi (impersonate="chrome131") + BS4.
"""
import random
import re
from typing import Optional

IMPERSONATE = "chrome131"
MAX_LISTINGS = 30

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


def extract_year(text: Optional[str]) -> Optional[int]:
    """Primul an plauzibil (1980-2099) dintr-un text."""
    if not text:
        return None
    m = re.search(r"\b(19[89]\d|20\d{2})\b", text)
    return int(m.group(0)) if m else None


def extract_km(text: Optional[str]) -> Optional[int]:
    """Extrage kilometrajul ('123.000 km', '85 000 km') dintr-un text."""
    if not text:
        return None
    m = re.search(r"([\d.\s]{2,})\s*km", text, re.I)
    if not m:
        return None
    return parse_int(m.group(1))


def normalize_fuel(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "benzin" in t or "petrol" in t:
        return "benzina"
    if "diesel" in t or "motorina" in t:
        return "diesel"
    if "hibrid" in t or "hybrid" in t:
        return "hibrid"
    if "electric" in t:
        return "electric"
    if "gpl" in t or "lpg" in t:
        return "gpl"
    return None


def normalize_gearbox(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "automat" in t or "automatic" in t:
        return "automata"
    if "manual" in t:
        return "manuala"
    return None


def make_listing(
    *,
    platform: str,
    external_id: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    km: Optional[int] = None,
    engine_type: Optional[str] = None,
    gearbox: Optional[str] = None,
    body_type: Optional[str] = None,
    color: Optional[str] = None,
    pret: Optional[float] = None,
    moneda: str = "EUR",
    locatie: Optional[str] = None,
    titlu: Optional[str] = None,
    descriere: Optional[str] = None,
    source_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> dict:
    """Forma standard a unui anunt auto, aliniata cu modelul AutoListing."""
    return {
        "platform": platform,
        "external_id": external_id,
        "make": make,
        "model": model,
        "year": year,
        "km": km,
        "engine_type": engine_type,
        "gearbox": gearbox,
        "body_type": body_type,
        "color": color,
        "pret": pret,
        "moneda": moneda,
        "locatie": locatie,
        "titlu": titlu,
        "descriere": descriere,
        "source_url": source_url,
        "thumbnail_url": thumbnail_url,
    }
