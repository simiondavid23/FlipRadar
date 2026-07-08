"""Teste de caracterizare pentru scorer-ul imobiliar (logica pura, fara DB).

Ingheata comportamentul CURENT, inclusiv fixul F5: vanzarile primesc scor
neutru; chiriile se gradeaza dupa raportul pret/mp fata de media zonei.
Pragurile documentate mai jos sunt citite din scorer.py (compute_re_score).
"""
import pytest

from app.services.real_estate.scorer import compute_re_score


# ── F5: vanzarile primesc mereu (50, "C") — referintele _REFS sunt de chirie ─────
def test_vanzare_explicit_e_neutru():
    # tip_anunt="vanzare" -> guard-ul din compute_re_score intoarce imediat (50, "C").
    assert compute_re_score(100000, "EUR", 50, 2, None, "bucuresti", None,
                            tip_anunt="vanzare") == (50, "C")


def test_default_fara_tip_anunt_e_vanzare_neutru():
    # Fara tip_anunt -> default "vanzare" -> (50, "C"). Ingheata fixul F5.
    assert compute_re_score(100000, "EUR", 50, 2, None, "bucuresti", None) == (50, "C")


# ── Chirii: gradare pe raportul ppm/zone_avg ─────────────────────────────────────
# ppm = pret_eur / area_sqm. Cu area=50 si currency EUR, ppm = price / 50.
# Praguri (scorer.py): <=0.70:+35 · <=0.80:+25 · <=0.90:+12 · <=0.95:+5 ·
#                       >=1.20:-20 · >=1.10:-10 · altfel: 0. Baza = 50.
# Grade: >=80 A · >=60 B · >=40 C · altfel D.
@pytest.fixture
def _fix_bnr(monkeypatch):
    # compute_re_score face `from app.services.bnr_exchange import get_eur_ron`
    # LOCAL (in interiorul functiei) -> patch-uim modulul-sursa.
    monkeypatch.setattr("app.services.bnr_exchange.get_eur_ron", lambda: 5.0)


def test_chirie_ieftina_e_grad_A(_fix_bnr):
    # ppm = 300/50 = 6 ; ratio = 6/10 = 0.60 <= 0.70 -> +35 -> 85 -> "A".
    assert compute_re_score(300, "EUR", 50, 2, None, "bucuresti", 10.0,
                            tip_anunt="inchiriere") == (85, "A")


def test_chirie_scumpa_e_grad_D(_fix_bnr):
    # ppm = 650/50 = 13 ; ratio = 13/10 = 1.30 >= 1.20 -> -20 -> 30 -> "D".
    assert compute_re_score(650, "EUR", 50, 2, None, "bucuresti", 10.0,
                            tip_anunt="inchiriere") == (30, "D")


def test_chirie_in_banda_neutra_ramane_C(_fix_bnr):
    # ppm = 500/50 = 10 ; ratio = 10/10 = 1.00 (intre 0.95 si 1.10) -> 0 -> 50 -> "C".
    assert compute_re_score(500, "EUR", 50, 2, None, "bucuresti", 10.0,
                            tip_anunt="inchiriere") == (50, "C")
