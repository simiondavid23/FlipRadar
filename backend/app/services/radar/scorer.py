"""Calcul scor + filtru de marja minima ("AI Price Filter") + fee ceiling.

Marja se calculeaza din pretul de revanzare estimat de utilizator. Listingurile
cu marja sub pragul setat (min_margin_pct) sunt marcate filtered=True ca sa nu
ajunga in feed-ul utilizatorului implicit.
"""
from datetime import datetime
from typing import Optional


# ── RP-1: praguri pentru badge-ul "vânzător riscant" (documentate, ajustabile) ──
# Rating-ul e mereu pe scară normalizată 0–5 (Vinted: feedback_reputation×5;
# Okazii: procent_pozitive/20).
_VINTED_RATING_MIN = 3.5      # rating sub acest prag + puține review-uri = risc
_VINTED_FEW_REVIEWS = 5       # „puține review-uri" pentru regula Vinted de mai sus
_OKAZII_RATING_MIN = 4.0      # 4.0/5 == 80% calificative pozitive (sub → risc)
_OLX_CHEAP_RATIO = 0.5        # cont nou + preț < 50% din revânzare = risc
_GENERIC_CHEAP_RATIO = 0.4    # vânzător necunoscut + preț < 40% din revânzare = risc


def calculate_score(
    listing_price: float,
    resale_price: float,
    min_margin_pct: float = 10.0,
    grade_a_min: Optional[float] = None,
    grade_b_min: Optional[float] = None,
    grade_c_min: Optional[float] = None,
) -> dict:
    """Returneaza scor A/B/C/D + marja calculata + flag filtered.

    Daca marja e negativa (listingul e mai scump decat pretul de revanzare),
    listingul nu primeste scor — filtered=True si nu apare in feed.

    grade_a_min/grade_b_min/grade_c_min sunt pragurile (%) de la care se acorda
    fiecare grad. Cand sunt None se folosesc valorile implicite 40/25/10, deci
    comportamentul ramane IDENTIC cu cel dinainte daca nu sunt setate per-keyword.
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

    a_min = grade_a_min if grade_a_min is not None else 40.0
    b_min = grade_b_min if grade_b_min is not None else 25.0
    c_min = grade_c_min if grade_c_min is not None else 10.0

    if margin_pct >= a_min:
        score = "A"
    elif margin_pct >= b_min:
        score = "B"
    elif margin_pct >= c_min:
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


def compute_seller_risk(
    platform: str,
    price: Optional[float],
    resale_price: Optional[float],
    seller_name: Optional[str],
    seller_reviews: Optional[int],
    seller_rating: Optional[float],
    extra: Optional[dict] = None,
) -> tuple[bool, Optional[str]]:
    """Decide daca un vanzator e "riscant" + motivul (pentru badge/tooltip).

    Functie PURA (fara DB), table-driven pe pragurile _*_ documentate sus.
    Defensiv: datele lipsa (None) NU declanseaza singure risc, cu exceptia
    regulilor care testeaza EXPLICIT lipsa (cont fara review-uri / vanzator
    necunoscut). Se aplica prima regula care se potriveste.
    """
    extra = extra or {}
    p = (platform or "").lower()
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None
    try:
        resale_f = float(resale_price) if resale_price else None
    except (TypeError, ValueError):
        resale_f = None

    # ── Vinted — cont fara review-uri / rating slab pe cont mic ──
    if p == "vinted":
        if seller_reviews == 0:
            return True, "Cont Vinted fără review-uri"
        if (seller_rating is not None and seller_rating < _VINTED_RATING_MIN
                and seller_reviews is not None and seller_reviews < _VINTED_FEW_REVIEWS):
            return True, f"Rating scăzut ({seller_rating:.1f}/5) și puține review-uri ({seller_reviews})"

    # ── Okazii — sub 80% calificative pozitive ──
    if p == "okazii":
        if seller_rating is not None and seller_rating < _OKAZII_RATING_MIN:
            return True, f"Calificative pozitive sub 80% (~{seller_rating * 20:.0f}%)"

    # ── OLX — cont nou (anul curent) + pret suspect de mic ──
    if p == "olx":
        member_since = extra.get("olx_member_since")
        if member_since is not None and price_f is not None and resale_f:
            try:
                if int(member_since) == datetime.now().year and price_f < _OLX_CHEAP_RATIO * resale_f:
                    return True, "Cont nou (înregistrat anul acesta) + preț suspect de mic"
            except (TypeError, ValueError):
                pass

    # ── Generic (orice platforma, inclusiv fara date de vanzator) ──
    if (not seller_name or not str(seller_name).strip()) and price_f is not None and resale_f:
        if price_f < _GENERIC_CHEAP_RATIO * resale_f:
            return True, "Vânzător necunoscut + preț mult sub valoarea de revânzare"

    return False, None
