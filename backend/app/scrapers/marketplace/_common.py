"""Comune pentru scraperele Modulul 1 Marketplace.

Foloseste curl_cffi (profil din app/utils/http_profile.py, AsyncSession) ca sa treaca peste
WAF-urile anti-bot. Aici sunt centralizate: header-ele realiste cu User-Agent rotit,
parsarea preturilor in format romanesc si forma standard a rezultatului.
"""
import re
from typing import Optional
from app.utils.http_profile import DEFAULT_IMPERSONATE

# Toate scraperele impersoneaza Chrome 131 prin curl_cffi.
IMPERSONATE = DEFAULT_IMPERSONATE   # profil unic, vezi app/utils/http_profile.py
# Numarul maxim de rezultate returnate de fiecare scraper.
MAX_RESULTS = 50


# Delay aleator (secunde) intre pagini cand scrapeam mai multe pagini.
PAGE_DELAY_RANGE = (0.5, 1.2)


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

    Ramane Accept-Language (ro-RO): nu contrazice amprenta (e preferinta de utilizator) si conteaza pe
    site-urile tinta. `extra` ramane suveran — call site-urile isi pun in continuare
    Referer, Accept: application/json, X-Requested-With, Content-Type sau alta limba.
    """
    headers = {
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
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
