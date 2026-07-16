"""C-15 — watchdog de sanatate Catalog (detectie magazin blocat la refresh pret).

Teste pure pe API-ul watchdog-ului: fara retea, fara DB (db=None -> dispatch-ul pe
Discord se sare, logging-ul merge). Starea e module-level, deci fixture-ul autouse o
reseteaza inainte SI dupa fiecare test (altfel testele se contamineaza intre ele).
"""
import pytest

from app.services import catalog_health_watchdog as wd


@pytest.fixture(autouse=True)
def _clean_state():
    wd._reset_state()
    yield
    wd._reset_state()


def _cycle(results: dict):
    """Un ciclu complet: open + note_refresh per magazin + close(None).
    `results` = {magazin: (nr_reusite, nr_esecuri)}."""
    wd.open_cycle()
    for source, (ok, fail) in results.items():
        for _ in range(ok):
            wd.note_refresh(source, success=True)
        for _ in range(fail):
            wd.note_refresh(source, success=False)
    wd.close_cycle(None)


# ── (a) pragul de 5 cicluri ──────────────────────────────────────────────────────
def test_fail_streak_atinge_prag_alerteaza():
    """5 cicluri in care pcgarage esueaza total, iar altex raspunde -> suspect.
    La al 4-lea NU inca: pragul e 5, nu 'cateva'."""
    for i in range(1, 5):
        _cycle({"altex.ro": (3, 0), "pcgarage.ro": (0, 2)})
        assert wd._fail_streak["pcgarage.ro"] == i
        assert "pcgarage.ro" not in wd._suspect, f"alertat prea devreme, la ciclul {i}"

    _cycle({"altex.ro": (3, 0), "pcgarage.ro": (0, 2)})
    assert wd._fail_streak["pcgarage.ro"] == 5
    assert "pcgarage.ro" in wd._suspect
    # Magazinul sanatos nu e atins.
    assert "altex.ro" not in wd._suspect
    assert wd._fail_streak["altex.ro"] == 0


# ── (b) recovery ─────────────────────────────────────────────────────────────────
def test_recovery_reseteaza():
    for _ in range(5):
        _cycle({"altex.ro": (3, 0), "pcgarage.ro": (0, 2)})
    assert "pcgarage.ro" in wd._suspect

    _cycle({"altex.ro": (3, 0), "pcgarage.ro": (1, 0)})
    assert "pcgarage.ro" not in wd._suspect
    assert wd._fail_streak["pcgarage.ro"] == 0


# ── (c) guard any_alive ──────────────────────────────────────────────────────────
def test_guard_any_alive():
    """Daca TOATE magazinele esueaza, probabil e net-ul — nu acuzam magazinele."""
    for _ in range(6):
        _cycle({"altex.ro": (0, 2), "pcgarage.ro": (0, 2)})

    assert wd._fail_streak.get("altex.ro", 0) == 0
    assert wd._fail_streak.get("pcgarage.ro", 0) == 0
    assert wd._suspect == set()


# ── (d) magazin neatins -> streak inghetat ───────────────────────────────────────
def test_magazin_nescanat_ingheata():
    for _ in range(3):
        _cycle({"altex.ro": (3, 0), "pcgarage.ro": (0, 2)})
    assert wd._fail_streak["pcgarage.ro"] == 3

    # Ciclu fara nicio sursa pcgarage: nici reset, nici incrementare.
    _cycle({"altex.ro": (3, 0)})
    assert wd._fail_streak["pcgarage.ro"] == 3
    assert "pcgarage.ro" not in wd._suspect


# ── (e) note fara ciclu deschis ──────────────────────────────────────────────────
def test_note_fara_ciclu_noop():
    wd.note_refresh("altex.ro", success=False)
    wd.note_refresh("altex.ro", success=True)
    assert wd._acc_scanned == set()
    assert wd._acc_ok == {}
    assert wd._acc_fail == {}

    # close fara open e la randul lui no-op (nu crapa, nu alerteaza).
    wd.close_cycle(None)
    assert wd._suspect == set()


# ── alerta pleaca o SINGURA data cat timp magazinul e suspect ────────────────────
def test_alerta_doar_la_tranzitie(monkeypatch):
    """Cat e suspect nu se mai alerteaza — altfel ar spama la fiecare ciclu."""
    alerts = []
    monkeypatch.setattr(wd, "_dispatch_alert",
                        lambda db, text, level: alerts.append((level, text)))

    for _ in range(7):  # 2 cicluri peste prag
        _cycle({"altex.ro": (3, 0), "pcgarage.ro": (0, 2)})
    assert len(alerts) == 1, f"alerte duplicate: {alerts}"
    assert alerts[0][0] == "WARN"
    assert "pcgarage.ro" in alerts[0][1]

    _cycle({"altex.ro": (3, 0), "pcgarage.ro": (1, 0)})
    assert len(alerts) == 2
    assert alerts[1][0] == "OK"
