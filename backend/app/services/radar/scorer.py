"""Calcul scor + filtru de marja minima ("AI Price Filter") + fee ceiling.

Marja se calculeaza din pretul de revanzare estimat de utilizator. Listingurile
cu marja sub pragul setat (min_margin_pct) sunt marcate filtered=True ca sa nu
ajunga in feed-ul utilizatorului implicit.
"""
from typing import Optional


def calculate_score(
    listing_price: float,
    resale_price: float,
    min_margin_pct: float = 10.0,
) -> dict:
    """Returneaza scor A/B/C/D + marja calculata + flag filtered.

    Daca marja e negativa (listingul e mai scump decat pretul de revanzare),
    listingul nu primeste scor — filtered=True si nu apare in feed.
    """
    try:
        listing_price_f = float(listing_price)
        resale_price_f = float(resale_price)
    except (TypeError, ValueError):
        return {"score": None, "margin_pct": 0.0, "margin_value": 0.0, "filtered": True}

    if resale_price_f <= 0:
        return {"score": None, "margin_pct": 0.0, "margin_value": 0.0, "filtered": True}

    margin_value = resale_price_f - listing_price_f
    margin_pct = (margin_value / resale_price_f) * 100.0

    if margin_pct < 0:
        return {"score": None, "margin_pct": margin_pct, "margin_value": margin_value, "filtered": True}

    if margin_pct < float(min_margin_pct or 0):
        return {"score": "D", "margin_pct": margin_pct, "margin_value": margin_value, "filtered": True}

    if margin_pct >= 40:
        score = "A"
    elif margin_pct >= 25:
        score = "B"
    elif margin_pct >= 10:
        score = "C"
    else:
        score = "D"

    return {
        "score": score,
        "margin_pct": margin_pct,
        "margin_value": margin_value,
        "filtered": False,
    }


def calculate_fee_ceiling(
    resale_price: float,
    platform: str,
    shipping_cost: float = 20.0,
) -> float:
    """Pretul maxim recomandat de cumparare, dupa scaderea costurilor specifice
    platformei pe care vinzi mai departe.
    """
    try:
        resale = float(resale_price)
    except (TypeError, ValueError):
        return 0.0
    shipping = float(shipping_cost or 0)
    p = (platform or "").lower()
    if p == "okazii":
        return max(0.0, resale * 0.92 - shipping)
    # OLX, Vinted (cumparatorul plateste taxa), Facebook
    return max(0.0, resale - shipping)
