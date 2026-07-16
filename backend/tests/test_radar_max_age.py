"""RAD-1 — functii pure de plafonare: vechimea maxima a unui anunt (_too_old) si
plafonul de pagini per platforma (_page_cap_for).

Teste pure: fara retea, fara DB, fara sleep. `now` e injectat in _too_old ca sa nu
depinda de ceasul real.
"""
from datetime import datetime, timedelta

from app.utils.radar_scanner import _page_cap_for, _too_old

_NOW = datetime(2026, 7, 17, 12, 0, 0)


# ── _too_old ────────────────────────────────────────────────────────────────────
def test_fara_limita_nu_e_niciodata_prea_vechi():
    vechi = _NOW - timedelta(days=3650)
    assert _too_old(vechi, None, now=_NOW) is False


def test_limita_zero_dezactiveaza_filtrul():
    vechi = _NOW - timedelta(days=3650)
    assert _too_old(vechi, 0, now=_NOW) is False


def test_fara_data_e_tolerant():
    # Platformele care nu expun listed_at nu trebuie sa piarda anunturi.
    assert _too_old(None, 30, now=_NOW) is False


def test_anunt_recent_trece():
    assert _too_old(_NOW - timedelta(days=5), 30, now=_NOW) is False


def test_anunt_vechi_e_respins():
    assert _too_old(_NOW - timedelta(days=40), 30, now=_NOW) is True


def test_exact_pe_limita_trece():
    # Comparatia e strict ">" -> fix la limita anuntul e inca acceptat.
    assert _too_old(_NOW - timedelta(days=30), 30, now=_NOW) is False
    assert _too_old(_NOW - timedelta(days=30, seconds=1), 30, now=_NOW) is True


def test_tip_invalid_nu_arunca():
    # listed_at venit ca string dintr-un scraper -> tolerant, nu crapa scanul.
    assert _too_old("2026-07-01", 30, now=_NOW) is False


# ── _page_cap_for ───────────────────────────────────────────────────────────────
def test_vinted_prima_scanare_are_plafon_strans():
    assert _page_cap_for("vinted", True) == 3


def test_vinted_scanare_normala():
    assert _page_cap_for("vinted", False) == 10


def test_olx_e_nelimitat():
    # OLX are plafon intern in scraper -> None (fara plafon in bucla).
    assert _page_cap_for("olx", False) is None
    assert _page_cap_for("olx", True) is None


def test_platforma_goala_e_nelimitata():
    assert _page_cap_for("", False) is None


def test_platforma_case_insensitive():
    assert _page_cap_for("Vinted", False) == 10
