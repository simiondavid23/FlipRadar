"""NET-5.1 — al treilea semnal al watchdog-ului: „blocat".

Aceleasi conventii ca `test_radar_watchdog.py`: fara DB (db=None), fixture autouse cu
`_reset_state()` si `_dispatch_alert` monkeypatch-uit ca sa colecteze (text, level).

Pragul e 2, nu 5: un 403 nu are nevoie de guard anti-fals-pozitiv, iar la 5 cicluri x
5 minute alerta ar veni dupa 25 de minute de blocaj.
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


def _cycle(platform, results=0, errors=0, blocked=0, note=True):
    """Un ciclu complet al UNEI platforme, cu al treilea semnal in plus."""
    hw.open_cycle(platform)
    if note:
        hw.note_results(platform, results)
    for _ in range(errors):
        hw.note_error(platform)
    for _ in range(blocked):
        hw.note_blocked(platform)
    hw.close_cycle(None, platform)


def _alive(platform="olx"):
    """Ciclu sanatos al altei platforme — tine guard-ul any_alive deschis."""
    _cycle(platform, results=3)


def _is_blocked_text(text):
    """Textul de blocaj e distinct de „pare blocată" al celorlalte doua semnale."""
    return "răspunsuri de blocare" in text


# 1. No-op fara ciclu deschis — exact ca note_error.
def test_note_blocked_e_noop_fara_ciclu_deschis(alerts):
    hw.note_blocked("vinted")
    assert hw._acc_blocked == {}
    assert hw._acc_scanned == set()
    assert alerts == []


# 2. Doua cicluri consecutive cu blocaje -> o singura alerta, cu textul de blocaj.
def test_alerta_la_doua_cicluri_blocate(alerts):
    _cycle("vinted", results=0, blocked=1)
    assert alerts == []
    _cycle("vinted", results=0, blocked=1)
    assert len(alerts) == 1
    text, level = alerts[0]
    assert level == "WARN" and "vinted" in text and _is_blocked_text(text)


# 3. Al treilea ciclu blocat nu mai alerteaza (e deja suspect).
def test_al_treilea_ciclu_blocat_nu_re_alerteaza(alerts):
    for _ in range(3):
        _cycle("vinted", results=0, blocked=1)
    assert len(alerts) == 1


# 4. Recovery: alerta OK + reset la toate trei streak-urile.
def test_recovery_reseteaza_toate_trei_streak_urile(alerts):
    for _ in range(2):
        _alive()  # guard any_alive, ca sa creasca si _zero_streak
        _cycle("vinted", results=0, errors=1, blocked=1)
    assert len(alerts) == 1 and _is_blocked_text(alerts[0][0])
    assert hw._blocked_streak["vinted"] == 2
    assert hw._error_streak["vinted"] == 2
    assert hw._zero_streak["vinted"] == 2

    _cycle("vinted", results=3)  # revenire
    assert len(alerts) == 2 and alerts[1][1] == "OK" and "revenit" in alerts[1][0]
    assert "vinted" not in hw._suspect
    assert hw._blocked_streak["vinted"] == 0
    assert hw._error_streak["vinted"] == 0
    assert hw._zero_streak["vinted"] == 0


# 5. Ciclu cu blocaje SI erori -> castiga textul de blocaj (diagnostic mai precis).
def test_blocajul_bate_textul_de_eroare(alerts):
    for _ in range(3):
        _cycle("vinted", results=0, errors=1, blocked=1)
    assert len(alerts) == 1
    text, _ = alerts[0]
    assert _is_blocked_text(text) and "crăpat" not in text


# 6. Un ciclu fara blocaje reseteaza streak-ul (semantica lui _error_streak).
def test_streak_blocat_se_reseteaza_fara_blocaje(alerts):
    _cycle("vinted", results=0, blocked=1)
    assert hw._blocked_streak["vinted"] == 1
    _cycle("vinted", results=0)  # scanat, 0 rezultate, dar niciun blocaj
    assert hw._blocked_streak["vinted"] == 0
    _cycle("vinted", results=0, blocked=1)
    assert alerts == []  # streak-ul a repornit de la 1
