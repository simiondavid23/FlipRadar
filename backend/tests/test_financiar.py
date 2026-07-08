"""Test pentru calculatorul de costuri de import auto (compute_import_costs).

Functie pura de calcul; singura dependenta externa e cursul EUR->RON, pe care il
monkeypatch-uim. auto_scorer importa get_eur_ron la nivel de MODUL, deci patch-uim
numele din namespace-ul auto_scorer (nu modulul-sursa bnr_exchange).
"""
import pytest

from app.services.auto_scorer import compute_import_costs


@pytest.fixture
def _rate_5(monkeypatch):
    monkeypatch.setattr("app.services.auto_scorer.get_eur_ron", lambda: 5.0)


def test_import_costs_totaluri_pe_curs_fix(_rate_5):
    res = compute_import_costs(10000)   # 10.000 EUR, curs 5.0
    # pe_roti:      price_ron=50000 + eur(130+275=405 -> *5 =2025) + fix(740+150+130=1020) = 53045
    assert res["pe_roti"]["total_ron"] == 53045
    # pe_platforma: price_ron=50000 + eur(550 -> *5 =2750)          + fix(1020)             = 53770
    assert res["pe_platforma"]["total_ron"] == 53770
    assert res["pe_roti"]["eur_ron_rate"] == 5.0


def test_import_costs_profitabilitate(_rate_5):
    # autovit_avg_ron peste total -> saving pozitiv -> is_profitable True.
    res = compute_import_costs(10000, autovit_avg_ron=60000)
    assert res["pe_roti"]["saving_ron"] == 60000 - 53045
    assert res["pe_roti"]["is_profitable"] is True
