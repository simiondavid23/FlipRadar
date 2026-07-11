"""IM-4 — polling per keyword Imobiliare: funcții PURE _polling_due / _due_keywords.

Fără DB, fără scheduler. `now` e injectat cu datetime(...) explicit (aware UTC); kw e un
SimpleNamespace cu doar atributele citite (last_scan_at, polling_interval_minutes).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.real_estate_scanner import _polling_due, _due_keywords

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def _kw(last_scan_at=None, interval=30):
    return SimpleNamespace(last_scan_at=last_scan_at, polling_interval_minutes=interval)


def test_due_fara_istoric():
    assert _polling_due(_kw(last_scan_at=None), _NOW) is True


def test_due_interval_neexpirat():
    # interval 30, ultimul scan acum 10 min -> încă nescadent
    assert _polling_due(_kw(last_scan_at=_NOW - timedelta(minutes=10), interval=30), _NOW) is False


def test_due_interval_expirat():
    # interval 15, acum 16 min -> scadent
    assert _polling_due(_kw(last_scan_at=_NOW - timedelta(minutes=16), interval=15), _NOW) is True


def test_due_naive_utc():
    # last_scan_at naiv (fără tzinfo) tratat ca UTC — fără excepție aware/naive
    naive = (_NOW - timedelta(minutes=31)).replace(tzinfo=None)
    assert _polling_due(_kw(last_scan_at=naive, interval=30), _NOW) is True


def test_due_fallback_30():
    # polling_interval_minutes None -> fallback 30
    assert _polling_due(_kw(last_scan_at=_NOW - timedelta(minutes=29), interval=None), _NOW) is False
    assert _polling_due(_kw(last_scan_at=_NOW - timedelta(minutes=31), interval=None), _NOW) is True


def test_due_keywords_filtrare():
    due = _kw(last_scan_at=None, interval=30)                              # scadent (fără istoric)
    not_due = _kw(last_scan_at=_NOW - timedelta(minutes=5), interval=30)   # nescadent
    assert _due_keywords([due, not_due], _NOW, force=False) == [due]


def test_due_keywords_force():
    due = _kw(last_scan_at=None, interval=30)
    not_due = _kw(last_scan_at=_NOW - timedelta(minutes=5), interval=30)
    # force True (scan manual) -> lista întreagă, inclusiv cel nescadent
    assert _due_keywords([due, not_due], _NOW, force=True) == [due, not_due]
