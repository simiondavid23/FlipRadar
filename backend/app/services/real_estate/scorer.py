"""
Scores real estate listings based on price/sqm vs zone average.
Uses DB averages when available (≥5 listings), falls back to
hardcoded reference prices per city/zone/room-count.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

# Reference prices EUR/sqm/month (chirie) — 2025-2026 market data
# Format: (city, zone_canonical): {rooms: avg_eur_per_sqm}
_REFS = {
    ("bucuresti", "Floreasca"):           {1: 10.5, 2: 9.8, 3: 9.2},
    ("bucuresti", "Dorobanți"):           {1: 10.0, 2: 9.5, 3: 9.0},
    ("bucuresti", "Herăstrău"):           {1: 11.0, 2: 10.2, 3: 9.8},
    ("bucuresti", "Aviatorilor"):         {1: 10.5, 2: 9.8, 3: 9.5},
    ("bucuresti", "Pipera / Aurel Vlaicu"): {1: 9.0, 2: 8.5, 3: 8.0},
    ("bucuresti", "Victoriei / Romană"):  {1: 9.5, 2: 9.0, 3: 8.5},
    ("bucuresti", "Unirii / Centru"):     {1: 9.0, 2: 8.5, 3: 8.0},
    ("bucuresti", "Timpuri Noi"):         {1: 7.5, 2: 7.0, 3: 6.8},
    ("bucuresti", "Titan / IOR"):         {1: 6.5, 2: 6.0, 3: 5.8},
    ("bucuresti", "Cotroceni / Eroilor"): {1: 8.5, 2: 8.0, 3: 7.5},
    ("bucuresti", "Grozăvești / Politehnica"): {1: 7.5, 2: 7.0, 3: 6.5},
    ("bucuresti", "Militari"):            {1: 6.0, 2: 5.8, 3: 5.5},
    ("bucuresti", "Drumul Taberei"):      {1: 6.0, 2: 5.5, 3: 5.2},
    ("bucuresti", "Berceni"):             {1: 5.8, 2: 5.5, 3: 5.2},
    ("bucuresti", "Tineretului"):         {1: 7.0, 2: 6.5, 3: 6.2},
    ("bucuresti", None):                  {1: 7.5, 2: 7.0, 3: 6.5},
    ("cluj-napoca", None):                {1: 9.5, 2: 9.0, 3: 8.5},
    ("iasi", None):                       {1: 6.5, 2: 6.0, 3: 5.8},
    ("timisoara", None):                  {1: 7.5, 2: 7.0, 3: 6.5},
    ("brasov", None):                     {1: 7.5, 2: 7.0, 3: 6.5},
}


def get_zone_avg_ppm(db: Session, model_class,
                     user_id: int, city: str,
                     zone_normalized: str,
                     rooms: int = None,
                     tip_anunt: str | None = None) -> Optional[float]:
    """Compute average price/sqm from DB listings (≥5 required)."""
    try:
        q = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.price_per_sqm.isnot(None),
            model_class.price_per_sqm > 0,
        )
        # Media pe chirii nu se contamineaza cu vanzari: filtram pe tip prin
        # keyword (model_class.keyword_id -> real_estate_keywords.tip_anunt).
        if tip_anunt and hasattr(model_class, "keyword_id"):
            q = q.join(RealEstateMonitorKeyword,
                       model_class.keyword_id == RealEstateMonitorKeyword.id
                ).filter(RealEstateMonitorKeyword.tip_anunt == tip_anunt)
        if zone_normalized:
            q = q.filter(model_class.zone_normalized == zone_normalized)
        if rooms:
            q = q.filter(model_class.rooms == rooms)
        rows = q.all()
        if len(rows) >= 5:
            vals = [float(r.price_per_sqm) for r in rows]
            return sum(vals) / len(vals)
    except Exception:
        pass
    return None


def get_ref_ppm(city: str, zone: str, rooms: int = None) -> Optional[float]:
    city = (city or "bucuresti").lower()
    if city in ("bucurești", "bucharest"):
        city = "bucuresti"
    zone_key = (city, zone)
    ref = _REFS.get(zone_key) or _REFS.get((city, None))
    if not ref:
        return None
    if rooms and rooms in ref:
        return ref[rooms]
    return sum(ref.values()) / len(ref)


def compute_re_score(price: float, currency: str, area_sqm: int,
                     rooms: int, zone_normalized: str, city: str,
                     zone_avg_ppm: float = None,
                     tip_anunt: str | None = None) -> tuple:
    if (tip_anunt or "vanzare") != "inchiriere":
        # Referintele (_REFS) si mediile sunt de CHIRIE; vanzarile primesc scor
        # neutru pana exista referinte de vanzare (post-licenta).
        return 50, "C"
    from app.services.bnr_exchange import get_eur_ron
    score = 50

    eur_ron = get_eur_ron()
    price_eur = price / eur_ron if currency == "RON" else price

    if area_sqm and area_sqm > 0:
        ppm = price_eur / area_sqm
        avg = zone_avg_ppm or get_ref_ppm(city, zone_normalized, rooms)
        if avg:
            ratio = ppm / avg
            if ratio <= 0.70:    score += 35
            elif ratio <= 0.80:  score += 25
            elif ratio <= 0.90:  score += 12
            elif ratio <= 0.95:  score += 5
            elif ratio >= 1.20:  score -= 20
            elif ratio >= 1.10:  score -= 10
    else:
        score = 40  # no area → can't compute properly

    score = max(0, min(100, score))
    grade = "A" if score >= 80 else "B" if score >= 60 else \
            "C" if score >= 40 else "D"
    return score, grade
