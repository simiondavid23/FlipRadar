"""IM-6 — cuvinte excluse per keyword Imobiliare: funcția pură _matches_exclusions + API.

Pure: _matches_exclusions (primește text + listă, fără DB). HTTP: create/get + update fără câmp
(fixtures din conftest, ca testele IM-2/IM-3).
"""
from app.services.real_estate_scanner import _matches_exclusions

_KW = "/api/real-estate-monitor/keywords"


# ── funcția pură ─────────────────────────────────────────────────────────────
def test_excluderi_gol_trece():
    assert _matches_exclusions("orice text", None) is True
    assert _matches_exclusions("orice text", []) is True
    assert _matches_exclusions(None, ["demisol"]) is True   # text None => "" => niciun termen


def test_excluderi_termen_prezent_respinge():
    assert _matches_exclusions("Apartament la demisol", ["demisol"]) is False


def test_excluderi_diacritice():
    # "Mansardă" ~ "mansarda" (NFKD -> ascii)
    assert _matches_exclusions("Mansardă superbă în centru", ["mansarda"]) is False


def test_excluderi_case_insensitive():
    assert _matches_exclusions("REGIM HOTELIER pe termen scurt", ["regim hotelier"]) is False


def test_excluderi_niciun_termen():
    assert _matches_exclusions("Apartament luminos cu balcon", ["garaj"]) is True
    # termeni goli / whitespace ignorați (nu resping)
    assert _matches_exclusions("Apartament luminos", ["", "   ", "garaj"]) is True


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _base_payload(**over):
    p = {"name": "Test excluderi", "platform": "olx"}
    p.update(over)
    return p


def test_api_create_si_get_exclude_words(auth_client):
    r = auth_client.post(_KW, json=_base_payload(exclude_words=["demisol", "mansarda"]))
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    assert r.json()["exclude_words"] == ["demisol", "mansarda"]
    g = auth_client.get(_KW)
    assert g.status_code == 200, g.text
    kw = next(k for k in g.json() if k["id"] == kid)
    assert kw["exclude_words"] == ["demisol", "mansarda"]


def test_api_update_fara_camp_nu_crapa(auth_client):
    r = auth_client.post(_KW, json=_base_payload(exclude_words=["demisol"]))
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    # PUT fără exclude_words -> normalizat la [] (Pasul 3), 200 (nu crapă, nu rămâne NULL)
    r2 = auth_client.put(f"{_KW}/{kid}", json=_base_payload(name="Test excluderi editat"))
    assert r2.status_code == 200, r2.text
    assert r2.json()["exclude_words"] == []
