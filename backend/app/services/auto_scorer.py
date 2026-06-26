"""Scoring and import cost calculator for auto feed listings."""
from typing import Optional
from app.services.bnr_exchange import get_eur_ron

_YEAR = 2026
IMPORT_PLATFORMS = {"mobile_de", "autoscout24", "kleinanzeigen_auto"}

_NEG = ["probleme", "lovit", "avariat", "piese", "accident",
        "face apa", "nu porneste", "fum", "reparatie", "dezmembrez"]
_POS = ["impecabil", "garantie", "service la zi", "carte service",
        "un proprietar", "recent adus", "adus germania", "adus austria",
        "full option", "xenon", "piele", "panoramic", "trapa"]

# Real costs 2025-2026 (sources: underepar.com, promotor.ro)
COSTS = {
    "pe_roti": {
        "zoll_eur":            130,   # numere Zoll + asigurare temporara
        "combustibil_eur":     275,   # combustibil ~250 EUR + viniete ~25 EUR
        "rar_ron":             740,   # RAR omologare import
        "itp_ron":             150,
        "inmatriculare_ron":   130,
    },
    "pe_platforma": {
        "transport_eur":       550,   # medie 300-800 EUR
        "rar_ron":             740,
        "itp_ron":             150,
        "inmatriculare_ron":   130,
    },
}


def compute_score(
    price: Optional[float],
    currency: str,
    year: Optional[int],
    km: Optional[int],
    title: str = "",
    market_avg_ron: Optional[float] = None,
) -> tuple:
    score = 50
    t = (title or "").lower()
    rate = get_eur_ron()
    price_ron = (price or 0) * (rate if currency == "EUR" else 1)

    # 1. Price vs market
    if market_avg_ron and price_ron:
        r = price_ron / market_avg_ron
        if r <= 0.60:    score += 35
        elif r <= 0.70:  score += 25
        elif r <= 0.80:  score += 15
        elif r <= 0.90:  score += 5
        elif r >= 1.20:  score -= 20
        elif r >= 1.10:  score -= 10

    # 2. Km/year
    if year and km:
        age = max(1, _YEAR - year)
        kpy = km / age
        if kpy < 8_000:    score += 20
        elif kpy < 12_000: score += 12
        elif kpy < 18_000: score += 5
        elif kpy > 30_000: score -= 10
        elif kpy > 40_000: score -= 20

    # 3. Signals
    score -= sum(1 for w in _NEG if w in t) * 8
    score += min(sum(1 for w in _POS if w in t) * 4, 16)

    score = max(0, min(100, score))
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
    return score, grade


def compute_import_costs(
    price_eur: float,
    autovit_avg_ron: Optional[float] = None,
) -> dict:
    """Returns cost breakdown for both transport modes.
    Calorie: persoana fizica, no TVA.
    """
    rate = get_eur_ron()

    def _build(mode: str) -> dict:
        c = COSTS[mode]
        fixed_ron = sum(v for k, v in c.items() if k.endswith("_ron"))
        eur_costs  = sum(v for k, v in c.items() if k.endswith("_eur"))
        eur_ron    = round(eur_costs * rate, 0)
        price_ron  = round(price_eur * rate, 0)
        total      = price_ron + eur_ron + fixed_ron
        saving     = round(autovit_avg_ron - total, 0) if autovit_avg_ron else None
        breakdown  = {k: (round(v * rate, 0) if k.endswith("_eur") else v)
                      for k, v in c.items()}
        return {
            "mode":            mode,
            "price_ron":       price_ron,
            "breakdown_ron":   breakdown,
            "total_ron":       total,
            "eur_ron_rate":    round(rate, 4),
            "autovit_avg_ron": autovit_avg_ron,
            "saving_ron":      saving,
            "is_profitable":   (saving > 0) if saving is not None else None,
        }

    return {
        "pe_roti":      _build("pe_roti"),
        "pe_platforma": _build("pe_platforma"),
    }
