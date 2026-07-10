"""RP-6 — watchdog de sanatate Radar Piata (detectie blocaje).

Teste pure: fara DB (db=None peste tot), fara retea. Fixture autouse reseteaza starea
module-level (`_reset_state()`) si monkeypatch-uieste `_dispatch_alert` sa colecteze
(text, level) intr-o lista — pe care testele o cer prin numele fixture-ului.
"""
import pytest

from app.services.radar import health_watchdog as hw


@pytest.fixture(autouse=True)
def alerts(monkeypatch):
    hw._reset_state()
    captured = []
    monkeypatch.setattr(
        "app.services.radar.health_watchdog._dispatch_alert",
        lambda db, text, level: captured.append((text, level)),
    )
    return captured


def _cycle(results=None, errors=None):
    """Un ciclu complet: open_cycle, note_results/note_error, close_cycle(None)."""
    hw.open_cycle()
    for p, c in (results or {}).items():
        hw.note_results(p, c)
    for p in (errors or []):
        hw.note_error(p)
    hw.close_cycle(None)


# 1. Zero -> alerta exact la prag (al 5-lea ciclu, nu inainte).
def test_zero_alert_at_threshold(alerts):
    for _ in range(4):
        _cycle({"okazii": 0, "olx": 3})
        assert alerts == []
    _cycle({"okazii": 0, "olx": 3})  # al 5-lea
    assert len(alerts) == 1
    text, level = alerts[0]
    assert level == "WARN" and "okazii" in text


# 2. Suspect nu re-alerteaza.
def test_suspect_no_realert(alerts):
    for _ in range(6):
        _cycle({"okazii": 0, "olx": 3})
    assert len(alerts) == 1


# 3. Guard any_alive: totul pe 0 -> zero alerte, streak neincrementat.
def test_any_alive_guard(alerts):
    for _ in range(10):
        _cycle({"okazii": 0, "publi24": 0})
    assert alerts == []
    assert hw._zero_streak.get("okazii", 0) == 0
    assert hw._zero_streak.get("publi24", 0) == 0


# 4. Recovery + re-armare completa.
def test_recovery_then_rearm(alerts):
    for _ in range(5):
        _cycle({"okazii": 0, "olx": 3})
    assert len(alerts) == 1 and alerts[0][1] == "WARN"
    _cycle({"okazii": 2, "olx": 3})  # revenire
    assert len(alerts) == 2
    assert alerts[1][1] == "OK" and "revenit" in alerts[1][0]
    assert "okazii" not in hw._suspect
    for _ in range(5):  # re-armare
        _cycle({"okazii": 0, "olx": 3})
    assert len(alerts) == 3 and alerts[2][1] == "WARN"


# 5. Erori -> alerta la al 3-lea ciclu.
def test_error_alert_at_three(alerts):
    for _ in range(2):
        _cycle({"vinted": 0, "olx": 3}, errors=["vinted"])
        assert alerts == []
    _cycle({"vinted": 0, "olx": 3}, errors=["vinted"])  # al 3-lea
    assert len(alerts) == 1
    text, level = alerts[0]
    assert level == "WARN" and "crăpat" in text and "vinted" in text


# 6. Reset independent al streak-ului de erori.
def test_error_streak_resets_independently(alerts):
    _cycle({"vinted": 0, "olx": 3}, errors=["vinted"])  # es=1, zs=1
    _cycle({"vinted": 0, "olx": 3}, errors=["vinted"])  # es=2, zs=2
    _cycle({"vinted": 0, "olx": 3})                      # fara eroare: es=0, zs=3
    assert alerts == []
    assert hw._error_streak.get("vinted", 0) == 0
    assert hw._zero_streak.get("vinted", 0) == 3


# 7. No-op fara ciclu deschis.
def test_noop_without_open_cycle(alerts):
    hw.note_results("okazii", 0)
    hw.note_error("okazii")
    hw.close_cycle(None)
    assert alerts == []
    assert hw._acc_scanned == set()
    assert hw._zero_streak == {} and hw._error_streak == {}
    assert hw._cycle_open is False


# 8. Platforma nescanata = streak inghetat.
def test_unscanned_freezes_streak(alerts):
    for _ in range(4):
        _cycle({"okazii": 0, "olx": 3})
    assert alerts == [] and hw._zero_streak["okazii"] == 4
    for _ in range(2):
        _cycle({"olx": 3})  # okazii NU e notata -> inghetat
    assert hw._zero_streak["okazii"] == 4 and alerts == []
    _cycle({"okazii": 0, "olx": 3})  # al 5-lea ciclu de zero -> alerta
    assert len(alerts) == 1 and alerts[0][1] == "WARN" and "okazii" in alerts[0][0]
