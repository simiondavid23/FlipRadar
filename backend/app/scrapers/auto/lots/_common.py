"""Comune pentru scraperele de loturi din licitatii auto (Copart, IAAI, SCA, OpenLane).

curl_cffi (impersonate="chrome131") + BeautifulSoup. Multe campuri (licitatie
curenta, VIN, stare cheie/pornire) necesita cont — la scraping public le marcam
ca None si le listam in `requires_account`.
"""
import random
import re
from datetime import datetime
from typing import Optional

IMPERSONATE = "chrome131"
MAX_LOTS = 30

# Campurile care, la scraping public (fara cont), nu sunt disponibile.
REQUIRES_ACCOUNT = ["current_bid", "title_type", "starts", "drives", "keys", "vin", "full_photos"]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def build_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    if extra:
        headers.update(extra)
    return headers


def parse_int(raw) -> Optional[int]:
    """Extrage primul numar intreg dintr-un text (an, km)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    digits = re.sub(r"[^\d]", "", str(raw))
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


def parse_money(raw) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    cleaned = re.sub(r"[^\d.]", "", str(raw))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def parse_epoch_ms(raw) -> Optional[str]:
    """Copart/IAAI returneaza uneori datele ca epoch in milisecunde."""
    if raw is None:
        return None
    try:
        ts = int(raw)
        if ts > 10_000_000_000:  # ms
            ts = ts / 1000.0
        return datetime.utcfromtimestamp(ts).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def make_lot(
    *,
    platform: str,
    lot_number: Optional[str] = None,
    title: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    damage_primary: Optional[str] = None,
    damage_secondary: Optional[str] = None,
    location_city: Optional[str] = None,
    location_state: Optional[str] = None,
    auction_date: Optional[str] = None,
    odometer: Optional[int] = None,
    thumbnail_url: Optional[str] = None,
    source_url: Optional[str] = None,
    current_bid: Optional[float] = None,
    buy_now_price: Optional[float] = None,
    title_type: Optional[str] = None,
    starts: Optional[bool] = None,
    drives: Optional[bool] = None,
    keys_present: Optional[bool] = None,
    vin: Optional[str] = None,
    requires_account: Optional[list] = None,
) -> dict:
    """Forma standard a unui lot, aliniata cu modelul AutoLot."""
    return {
        "platform": platform,
        "lot_number": lot_number,
        "title": title,
        "make": make,
        "model": model,
        "year": year,
        "damage_primary": damage_primary,
        "damage_secondary": damage_secondary,
        "location_city": location_city,
        "location_state": location_state,
        "auction_date": auction_date,
        "odometer": odometer,
        "thumbnail_url": thumbnail_url,
        "source_url": source_url,
        "current_bid": current_bid,
        "buy_now_price": buy_now_price,
        "title_type": title_type,
        "starts": starts,
        "drives": drives,
        "keys_present": keys_present,
        "vin": vin,
        "requires_account": requires_account if requires_account is not None else [],
    }
