"""AA-6 — rezolvarea marcii mobile.de (functia pura _resolve_make cu aliase) + endpoint
read-only cu marcile mapate (/makes/mobile-de). auth_client din conftest pentru endpoint.
"""
from app.scrapers.auto.listings.mobile_de_scraper import _resolve_make, MOBILE_DE_MAKE_IDS


def test_resolve_exact():
    assert _resolve_make("Volkswagen") == "25200"


def test_resolve_title():
    assert _resolve_make("volkswagen") == "25200"


def test_resolve_alias_vw():
    assert _resolve_make("vw") == "25200"


def test_resolve_alias_strip():
    assert _resolve_make("  vw  ") == "25200"


def test_resolve_necunoscut():
    assert _resolve_make("Dacia2000") == ""


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
