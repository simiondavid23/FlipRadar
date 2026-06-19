"""Comune pentru scraperele Modulul 1 Marketplace.

Foloseste curl_cffi cu impersonate="chrome131" (AsyncSession) ca sa treaca peste
WAF-urile anti-bot. Aici sunt centralizate: header-ele realiste cu User-Agent rotit,
parsarea preturilor in format romanesc si forma standard a rezultatului.
"""
import random
import re
from typing import Optional

# Toate scraperele impersoneaza Chrome 131 prin curl_cffi.
IMPERSONATE = "chrome131"
# Numarul maxim de rezultate returnate de fiecare scraper.
MAX_RESULTS = 50

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Delay aleator (secunde) intre pagini cand scrapeam mai multe pagini.
PAGE_DELAY_RANGE = (0.5, 1.2)


def build_headers(extra: Optional[dict] = None) -> dict:
    """Header-e realiste cu User-Agent rotit aleator."""
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra:
        headers.update(extra)
    return headers


def parse_price(raw: Optional[str]) -> Optional[float]:
    """Converteste un text de pret romanesc (ex: '2.500 lei', '1.234,56') in float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    cleaned = re.sub(r"[^\d.,]", "", str(raw))
    if not cleaned:
        return None
    # Punctul e separator de mii, virgula e separator zecimal (format RO).
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_condition(text: Optional[str]) -> Optional[str]:
    """Detectie generica Nou / Folosit dintr-un text liber."""
    if not text:
        return None
    t = text.strip().lower()
    if "nou" in t or "new" in t or "neu" in t or "sigilat" in t:
        return "nou"
    if "folosit" in t or "second" in t or "used" in t or "gebraucht" in t or "utilizat" in t:
        return "folosit"
    return None


def make_result(
    *,
    title: str,
    price: Optional[float],
    currency: str = "RON",
    condition: Optional[str] = None,
    location: Optional[str] = None,
    source_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    source: str = "",
    platform_id: Optional[str] = None,
) -> dict:
    """Forma standard a unui rezultat de scraping marketplace."""
    return {
        "title": title,
        "price": price,
        "currency": currency,
        "condition": condition,
        "location": location,
        "source_url": source_url,
        "thumbnail_url": thumbnail_url,
        "source": source,
        "platform_id": platform_id,
    }


def price_in_range(price: Optional[float], filters: dict) -> bool:
    """True daca pretul respecta min_price/max_price din filters (sau nu sunt setate)."""
    if price is None:
        return True
    try:
        mn = filters.get("min_price")
        mx = filters.get("max_price")
        if mn is not None and price < float(mn):
            return False
        if mx is not None and price > float(mx):
            return False
    except (TypeError, ValueError):
        return True
    return True
