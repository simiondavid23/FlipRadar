"""RP-1 — badge 'vânzător riscant' (compute_seller_risk), table-driven pe reguli."""
from datetime import datetime

import pytest

from app.services.radar.scorer import compute_seller_risk

_YEAR = datetime.now().year

# (platform, price, resale, seller_name, reviews, rating, extra, expected_risk)
_CASES = [
    # ── Vinted ──
    ("vinted", 100, 300, "user1", 0, 0.0, None, True),      # cont fara review-uri
    ("vinted", 100, 300, "user1", 3, 2.5, None, True),      # rating slab + putine review-uri
    ("vinted", 100, 300, "user1", 50, 2.5, None, False),    # rating slab dar multe review-uri
    ("vinted", 100, 300, "karolo", 48, 5.0, None, False),   # cont bun
    # ── Okazii ──
    ("okazii", 100, 300, "shop", 100, 3.5, None, True),     # sub 80% (rating < 4.0)
    ("okazii", 100, 300, "shop", 6382, 4.8, None, False),   # 96% pozitive
    # ── OLX ──
    ("olx", 100, 300, "Ion", None, None, {"olx_member_since": _YEAR}, True),   # cont nou + ieftin
    ("olx", 200, 300, "Ion", None, None, {"olx_member_since": _YEAR}, False),  # cont nou dar pret ok
    ("olx", 100, 300, "Ion", None, None, {"olx_member_since": 2018}, False),   # cont vechi
    # ── Generic (orice platforma, fara date de vanzator) ──
    ("publi24", 100, 300, None, None, None, None, True),    # necunoscut + pret < 40%
    ("publi24", 200, 300, None, None, None, None, False),   # necunoscut dar pret ok
]


@pytest.mark.parametrize("platform,price,resale,name,reviews,rating,extra,expected", _CASES)
def test_seller_risk_rules(platform, price, resale, name, reviews, rating, extra, expected):
    risk, reason = compute_seller_risk(platform, price, resale, name, reviews, rating, extra)
    assert risk is expected
    if expected:
        assert reason  # motivul e mereu setat cand e risc (pentru tooltip)
    else:
        assert reason is None


def test_missing_data_does_not_falsely_flag():
    # Fara pret de revanzare -> regula generica nu se poate aplica -> fara risc.
    risk, reason = compute_seller_risk("olx", 100, None, "Ion", None, None, {})
    assert risk is False and reason is None
