"""Comune pentru scraperele de loturi din licitatii auto (Copart, IAAI, SCA, OpenLane).

curl_cffi (profil din app/utils/http_profile.py) + BeautifulSoup. Multe campuri (licitatie
curenta, VIN, stare cheie/pornire) necesita cont — la scraping public le marcam
ca None si le listam in `requires_account`.
"""
import re
from datetime import datetime
from typing import Optional
from app.utils.http_profile import DEFAULT_IMPERSONATE

IMPERSONATE = DEFAULT_IMPERSONATE   # profil unic, vezi app/utils/http_profile.py
MAX_LOTS = 30

# Campurile care, la scraping public (fara cont), nu sunt disponibile.
REQUIRES_ACCOUNT = ["current_bid", "title_type", "starts", "drives", "keys", "vin", "full_photos"]



def build_headers(extra: Optional[dict] = None) -> dict:
    """Headers proprii — DOAR ce nu poate pune curl_cffi din profilul impersonat.

    IMP-1b: cu `impersonate=<profil>` curl_cffi trimite singur setul complet si
    COERENT al browserului (User-Agent, Sec-Ch-Ua* cu versiunea si platforma
    potrivite, Accept cu avif/webp, Accept-Encoding cu zstd, Sec-Fetch-*, Priority).
    Vechea implementare suprascria User-Agent-ul cu unul rotit din lista, deci
    requestul spunea "Chrome 131" (sau Edge) in UA in timp ce Sec-Ch-Ua si amprenta
    TLS spuneau alta versiune — contradictie pe care niciun browser real n-o produce.
    La fel Accept/Accept-Encoding (fara zstd/avif) si `Connection: keep-alive`,
    care pe HTTP/2 nici nu exista. Le-am scos pe toate.

    Ramane Accept-Language (en-US — site-uri de licitatii US): nu contrazice amprenta (e preferinta de utilizator) si conteaza pe
    site-urile tinta. `extra` ramane suveran — call site-urile isi pun in continuare
    Referer, Accept: application/json, X-Requested-With, Content-Type sau alta limba.
    """
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
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
    # SCRAPE-AUDIT: vechiul `re.sub(r"[^\d.]")` facea "€ 12.500" -> 12.5 (1000x mai
    # mic, tacut) si "1.234.567" -> None. Regula: cu ambele separatoare decide
    # ULTIMUL; doar virgule/puncte in grupuri de 3 = separatoare de mii.
    cleaned = re.sub(r"[^\d.,]", "", str(raw))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", cleaned):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
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
