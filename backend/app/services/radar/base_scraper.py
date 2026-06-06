"""Comune pentru toate scraperele Radar Marketplace.

User-Agent rotation, exponential backoff la rate-limit, filtru de cuvinte
excluse pe titlu. Centralizat aici ca sa fie consistent intre OLX, Vinted,
Okazii si Facebook si ca scrapere viitoare sa nu re-inventeze logica.
"""
import os
import random
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
