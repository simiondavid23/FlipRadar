"""
Serviciu de conversie valutară folosind cursurile oficiale BNR (Banca Națională a României).
Descarcă zilnic cursul EUR -> RON de la https://www.bnr.ro/nbrfxrates.xml și îl stochează în memorie.
"""
import re
import time
from typing import Dict, Optional

from curl_cffi import requests as curl_requests


_CACHE: Dict[str, float] = {}
_CACHE_TIMESTAMP: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 6 * 3600  # 6 hours

# Rate de rezervă folosite dacă BNR este inaccesibil (aproape de mediile recente)
_FALLBACK_EUR_RON = 4.97
_FALLBACK_USD_RON = 4.60


def _fetch_bnr_rates() -> Optional[Dict[str, float]]:
    """Descarcă XML-ul BNR și parsează ratele EUR/USD -> RON."""
    url = "https://www.bnr.ro/nbrfxrates.xml"
    try:
        response = curl_requests.get(url, impersonate="chrome131", timeout=10)
    except Exception:
        return None

    if response.status_code != 200:
        return None

    text = response.text
    rates: Dict[str, float] = {}
    for match in re.finditer(
        r'<Rate\s+currency="([A-Z]{3})"(?:\s+multiplier="(\d+)")?>([\d.]+)</Rate>',
        text,
    ):
        currency = match.group(1)
        multiplier = int(match.group(2)) if match.group(2) else 1
        try:
            value = float(match.group(3))
        except ValueError:
            continue
        # Rata reprezintă câți RON echivalează `multiplier` unități din moneda respectivă
        rates[currency] = value / multiplier
    return rates or None


def _get_rate(currency: str) -> float:
    """Returnează rata de conversie valută -> RON (ex: EUR -> 4.97 înseamnă 1 EUR = 4.97 RON)."""
    currency = (currency or "").upper()
    if currency == "RON":
        return 1.0

    now = time.time()
    cached = _CACHE.get(currency)
    ts = _CACHE_TIMESTAMP.get(currency, 0)
    if cached is not None and (now - ts) < _CACHE_TTL_SECONDS:
        return cached

    rates = _fetch_bnr_rates()
    if rates:
        for cur, rate in rates.items():
            _CACHE[cur] = rate
            _CACHE_TIMESTAMP[cur] = now
        if currency in rates:
            return rates[currency]

    if currency == "EUR":
        return _FALLBACK_EUR_RON
    if currency == "USD":
        return _FALLBACK_USD_RON
    return 1.0


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Converteste `amount` dintr-o moneda in alta folosind cursul valutar al BNR."""
    if amount is None:
        return 0.0
    from_currency = (from_currency or "RON").upper()
    to_currency = (to_currency or "RON").upper()
    if from_currency == to_currency:
        return round(amount, 2)

    # Converteste totul folosind RON ca referinta
    amount_ron = amount * _get_rate(from_currency)
    if to_currency == "RON":
        return round(amount_ron, 2)
    to_rate = _get_rate(to_currency)
    if to_rate == 0:
        return 0.0
    return round(amount_ron / to_rate, 2)


def get_eur_ron_rate() -> float:
    """Returnează cursul EUR -> RON curent (ex: 4.97)."""
    return _get_rate("EUR")


def get_all_rates() -> Dict[str, float]:
    """Returnează ratele EUR/USD -> RON din cache, actualizând dacă e necesar."""
    _get_rate("EUR")  # trigger fetch
    return {
        "EUR_RON": _CACHE.get("EUR", _FALLBACK_EUR_RON),
        "USD_RON": _CACHE.get("USD", _FALLBACK_USD_RON),
    }
