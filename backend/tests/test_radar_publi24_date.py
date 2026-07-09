"""RP-1 — parserul de dată Publi24 ('Valabil din', M/D/YYYY + AM/PM, §7)."""
import os
from datetime import datetime

from app.services.radar.publi24_scraper import _parse_valabil_din

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "publi24_valabil.html")


def test_from_fixture_is_month_day_pm():
    with open(_FIX, encoding="utf-8") as f:
        html = f.read()
    # 7/9/2026 7:14:42 PM -> 9 iulie 2026, 19:14:42 (M/D + PM)
    assert _parse_valabil_din(html) == datetime(2026, 7, 9, 19, 14, 42)


def test_pm_adds_twelve():
    assert _parse_valabil_din("Valabil din 3/15/2026 1:05:00 PM") == datetime(2026, 3, 15, 13, 5, 0)


def test_twelve_pm_stays_noon():
    assert _parse_valabil_din("Valabil din 6/1/2026 12:30:00 PM") == datetime(2026, 6, 1, 12, 30, 0)


def test_twelve_am_is_midnight():
    assert _parse_valabil_din("Valabil din 6/1/2026 12:30:00 AM") == datetime(2026, 6, 1, 0, 30, 0)


def test_absent_returns_none():
    assert _parse_valabil_din("fara data aici") is None
    assert _parse_valabil_din("") is None
