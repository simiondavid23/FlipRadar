"""RP-6 — watchdog de sanatate Radar Piata (detectie blocaje).

Teste pure: fara DB (db=None peste tot), fara retea. Fixture autouse reseteaza starea
module-level (`_reset_state()`) si monkeypatch-uieste `_dispatch_alert` sa colecteze
(text, level) intr-o lista — pe care testele o cer prin numele fixture-ului.

SCHED-1: ciclurile sunt PER PLATFORMA (open/close primesc platforma), deci un ciclu
vechi de forma {"okazii": 0, "olx": 3} devine DOUA cicluri. Ordinea conteaza: platforma
vie se inchide prima, altfel `_last_alive_at` inca nu e setat cand se evalueaza zero-ul.
Guard-ul any_alive e testat black-box (inchidem un ciclu al altei platforme cu
rezultate), nu prin semanarea directa a lui `_last_alive_at`.
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


class _Clock:
    """Ceas injectabil (conventia din test_radar_vinted_guard)."""

    def __init__(self, t=1000.0):
        self.t = float(t)

    def now(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _cycle(platform, results=0, errors=0, note=True):
    """Un ciclu complet al UNEI platforme: open_cycle, note_*, close_cycle(None).

    `note=False` = jobul a rulat dar platforma n-a fost atinsa (niciun keyword pe ea).
    """
    hw.open_cycle(platform)
    if note:
        hw.note_results(platform, results)
    for _ in range(errors):
        hw.note_error(platform)
    hw.close_cycle(None, platform)


def _alive(platform="olx"):
    """Ciclu sanatos al altei platforme — tine guard-ul any_alive deschis."""
    _cycle(platform, results=3)


# 1. Zero -> alerta exact la prag (al 5-lea ciclu, nu inainte).
def test_zero_alert_at_threshold(alerts):
    for _ in range(4):
        _alive()
        _cycle("okazii", results=0)
        assert alerts == []
    _alive()
    _cycle("okazii", results=0)  # al 5-lea
    assert len(alerts) == 1
    text, level = alerts[0]
    assert level == "WARN" and "okazii" in text


# 2. Suspect nu re-alerteaza.
def test_suspect_no_realert(alerts):
    for _ in range(6):
        _alive()
        _cycle("okazii", results=0)
    assert len(alerts) == 1


# 3. Guard any_alive: totul pe 0 -> zero alerte, streak neincrementat.
def test_any_alive_guard(alerts):
    for _ in range(10):
        _cycle("okazii", results=0)
        _cycle("publi24", results=0)
    assert alerts == []
    assert hw._zero_streak.get("okazii", 0) == 0
    assert hw._zero_streak.get("publi24", 0) == 0


# 4. Recovery + re-armare completa.
def test_recovery_then_rearm(alerts):
    for _ in range(5):
        _alive()
        _cycle("okazii", results=0)
    assert len(alerts) == 1 and alerts[0][1] == "WARN"
    _cycle("okazii", results=2)  # revenire
    assert len(alerts) == 2
    assert alerts[1][1] == "OK" and "revenit" in alerts[1][0]
    assert "okazii" not in hw._suspect
    for _ in range(5):  # re-armare
        _alive()
        _cycle("okazii", results=0)
    assert len(alerts) == 3 and alerts[2][1] == "WARN"


# 5. Erori -> alerta la al 3-lea ciclu.
def test_error_alert_at_three(alerts):
    for _ in range(2):
        _alive()
        _cycle("vinted", results=0, errors=1)
        assert alerts == []
    _alive()
    _cycle("vinted", results=0, errors=1)  # al 3-lea
    assert len(alerts) == 1
    text, level = alerts[0]
    assert level == "WARN" and "crăpat" in text and "vinted" in text


# 6. Reset independent al streak-ului de erori.
def test_error_streak_resets_independently(alerts):
    _alive()
    _cycle("vinted", results=0, errors=1)  # es=1, zs=1
    _alive()
    _cycle("vinted", results=0, errors=1)  # es=2, zs=2
    _alive()
    _cycle("vinted", results=0)            # fara eroare: es=0, zs=3
    assert alerts == []
    assert hw._error_streak.get("vinted", 0) == 0
    assert hw._zero_streak.get("vinted", 0) == 3


# 7. No-op fara ciclu deschis pentru platforma.
def test_noop_without_open_cycle(alerts):
    hw.note_results("okazii", 0)
    hw.note_error("okazii")
    hw.close_cycle(None, "okazii")
    assert alerts == []
    assert hw._acc_scanned == set()
    assert hw._zero_streak == {} and hw._error_streak == {}
    assert hw._open_platforms == set()


# 7b. SCHED-1 — ciclul altei platforme nu inchide/atinge platforma noastra.
def test_note_ignored_for_platform_without_open_cycle(alerts):
    hw.open_cycle("olx")
    hw.note_results("okazii", 5)   # okazii NU are ciclu deschis -> ignorat
    assert hw._acc_results.get("okazii") is None
    hw.close_cycle(None, "olx")
    assert "okazii" not in hw._last_alive_at


# 8. Platforma nescanata = streak inghetat.
def test_unscanned_freezes_streak(alerts):
    for _ in range(4):
        _alive()
        _cycle("okazii", results=0)
    assert alerts == [] and hw._zero_streak["okazii"] == 4
    for _ in range(2):
        _alive()
        _cycle("okazii", note=False)  # jobul ruleaza, dar okazii nu e atinsa -> inghetat
    assert hw._zero_streak["okazii"] == 4 and alerts == []
    _alive()
    _cycle("okazii", results=0)  # al 5-lea ciclu de zero -> alerta
    assert len(alerts) == 1 and alerts[0][1] == "WARN" and "okazii" in alerts[0][0]


# 9. SCHED-1 (NOU) — 0 rezultate si NICIO alta platforma vie in fereastra -> inghetat.
def test_streak_frozen_when_alive_window_expired(alerts, monkeypatch):
    clock = _Clock(1000.0)
    monkeypatch.setattr(hw, "_now", clock.now)
    _alive()                                  # olx vie acum...
    clock.advance(hw._ALIVE_WINDOW_S + 1)     # ...dar fereastra expira
    for _ in range(10):
        _cycle("okazii", results=0)
    assert alerts == []
    assert hw._zero_streak.get("okazii", 0) == 0


# 10. SCHED-1 — in fereastra, o platforma vie ramane vie intre cicluri (nu doar in al ei).
def test_alive_persists_across_cycles_within_window(alerts, monkeypatch):
    clock = _Clock(1000.0)
    monkeypatch.setattr(hw, "_now", clock.now)
    _alive()  # olx vie o singura data
    for _ in range(5):
        clock.advance(60)  # cicluri de okazii la 1 min, in fereastra de 30
        _cycle("okazii", results=0)
    assert len(alerts) == 1 and alerts[0][1] == "WARN" and "okazii" in alerts[0][0]
