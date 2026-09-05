"""Rezolvarea marcii mobile.de — `_resolve_make` + endpoint-ul read-only /makes/mobile-de.

Doua origini, un singur fisier (TIDY-1 le-a unit, fiindca testau aceeasi functie):

  * AA-6 — functia pura cu aliase (`vw` -> Volkswagen, `mercedes benz`, `škoda`) si
    endpoint-ul care expune marcile mapate. `auth_client` vine din conftest.
  * KA-1 (2026-09-03) — lookup-ul e case-insensitive. Treapta finala era
    `.get(make.title())`, care rezolva "volkswagen" (cheia e "Volkswagen") dar NU si
    "bmw": `.title()` da "Bmw", iar cheia din dictionar e "BMW". Masurat,
    `_resolve_make("bmw")` intorcea "", deci `makeModelVariant1.makeId` nu se seta
    niciodata si cautarea mergea pe TOATE marcile — tacut, fiindca scraperul doar loga
    un INFO. "BMW" e azi singura cheie non-title-case din `MOBILE_DE_MAKE_IDS`, dar
    testul e scris pe proprietate (orice cheie, orice grafie), nu pe cazul particular.
"""
import pytest

from app.scrapers.auto.listings.mobile_de_scraper import (
    MOBILE_DE_MAKE_IDS, _resolve_make,
)


# ── AA-6: cheia exacta, aliasele, endpoint-ul ──────────────────────────────────
def test_resolve_exact():
    assert _resolve_make("Volkswagen") == "25200"


def test_resolve_alias_vw():
    assert _resolve_make("vw") == "25200"


def test_resolve_alias_strip():
    assert _resolve_make("  vw  ") == "25200"


def test_resolve_aliase_compuse():
    # aliasele pe care .title() NU le-ar prinde (cratima / diacritic)
    assert _resolve_make("mercedes benz") == "17200"   # -> Mercedes-Benz
    assert _resolve_make("škoda") == "22900"           # -> Skoda


def test_makes_endpoint(auth_client):
    r = auth_client.get("/api/auto-listings/makes/mobile-de")
    assert r.status_code == 200, r.text
    makes = r.json()["makes"]
    assert makes == sorted(makes)                      # lista sortata
    assert "Volkswagen" in makes
    assert len(makes) == len(MOBILE_DE_MAKE_IDS)       # toate cheile din dict


# ── KA-1 (2026-09-03): lookup case-insensitive ─────────────────────────────────
@pytest.mark.parametrize("grafie", ["bmw", "BMW", "Bmw", "bMw", "  BmW  "])
def test_bmw_se_rezolva_indiferent_de_grafie(grafie):
    assert _resolve_make(grafie) == MOBILE_DE_MAKE_IDS["BMW"]
    assert _resolve_make(grafie) != ""


def test_orice_cheie_se_rezolva_in_orice_grafie():
    """Proprietatea, nu cazul: fiecare marca mapata trebuie sa se rezolve scrisa cu
    minuscule si cu majuscule, altfel bug-ul revine la urmatoarea cheie adaugata.

    TIDY-1: acopera si fostul `test_resolve_title` ("volkswagen" -> 25200), care era
    exact aceasta proprietate pe o singura cheie.
    """
    for cheie, id_ in MOBILE_DE_MAKE_IDS.items():
        assert _resolve_make(cheie.lower()) == id_, cheie
        assert _resolve_make(cheie.upper()) == id_, cheie


def test_necunoscutul_ramane_gol():
    """TIDY-1: inlocuieste si fostul `test_resolve_necunoscut` ("Dacia2000" -> ""),
    fiind varianta mai stricta — acopera si sirul gol, si None."""
    assert _resolve_make("marca-inexistenta") == ""
    assert _resolve_make("") == ""
    assert _resolve_make(None) == ""


def test_id_numeric_nu_trece_prin_resolve():
    """Contractul e ca `search_mobile_de` sare peste `_resolve_make` cand make_id e deja
    numeric (`if make_id and not make_id.isdigit()`). Functia in sine NU cunoaste
    id-uri — un "12" nu e o marca mapata, deci "". Comportament neschimbat de KA-1."""
    assert _resolve_make("12") == ""
