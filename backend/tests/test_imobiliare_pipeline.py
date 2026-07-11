"""IM-1 — pipeline de filtrare Imobiliare Monitor (functii PURE, fara retea, fara DB).

Acopera:
  - _seed_from_raw           (mapare chei RO/EN -> seed canonic)
  - _matches_re_keyword      (filtru criterii + normalizare EUR/RON cu curs)
  - _matches_query_local     (cautare libera locala, diacritice)
  - _olx_build_url           (oras ca path, camere deconectate, q- pentru query)
  - _passes_imob_filters     (suprafata_max nou)

Nu se testeaza _save_listing / _save_fb_group_post (ating DB) — doar functiile pure de mai sus.
"""
from types import SimpleNamespace

from app.services.real_estate_scanner import (
    _seed_from_raw, _matches_re_keyword, _matches_query_local,
)
from app.scrapers.real_estate.olx_real_estate import _olx_build_url
from app.scrapers.real_estate.imobiliare_ro_scraper import _passes_imob_filters


def _kw(**over):
    """Keyword minimal (SimpleNamespace) cu atributele citite de _matches_re_keyword."""
    base = dict(price_currency="EUR", price_min=None, price_max=None, rooms=None,
                area_min=None, area_max=None, floor_min=None, floor_max=None,
                furnished=None, zone=None)
    base.update(over)
    return SimpleNamespace(**base)


# ── _seed_from_raw ────────────────────────────────────────────────────────────

def test_seed_din_chei_romanesti():
    # scraperele .ro (make_re_listing) emit chei romanesti
    raw = {"titlu": "Garsoniera Militari", "descriere": "zona buna", "camere": 2,
           "suprafata_mp": 55, "etaj": "3", "pret": "350", "moneda": "RON",
           "tip_proprietate": "apartament", "locatie_oras": "Cluj"}
    seed = _seed_from_raw(raw)
    assert seed["title"] == "Garsoniera Militari"
    assert seed["description"] == "zona buna"
    assert seed["rooms"] == 2
    assert seed["area_sqm"] == 55
    assert seed["floor"] == "3"
    assert seed["price"] == 350.0          # convertit la float
    assert seed["currency"] == "RON"       # bugul vechi: se pierdea -> RON salvat ca EUR
    assert seed["property_type"] == "apartament"
    assert seed["zone_hint"] == "Cluj"


def test_seed_din_chei_englezesti():
    # scraperul Facebook emite variante englezesti (title/price/currency/location)
    raw = {"title": "Apartment 2 rooms", "description": "nice", "price": 400.0,
           "currency": "EUR", "location": "Bucuresti", "property_type": "apartament"}
    seed = _seed_from_raw(raw)
    assert seed["title"] == "Apartment 2 rooms"
    assert seed["price"] == 400.0
    assert seed["currency"] == "EUR"
    assert seed["zone_hint"] == "Bucuresti"


def test_seed_valori_lipsa_raman_none():
    # dict gol -> toate cheile None, fara exceptii
    seed = _seed_from_raw({})
    assert set(seed.keys()) == {"title", "description", "rooms", "area_sqm", "floor",
                                "price", "currency", "property_type", "zone_hint", "listed_at"}
    assert all(v is None for v in seed.values())
    # "" e tratat ca None (nu ca valoare)
    seed2 = _seed_from_raw({"titlu": "", "pret": "", "moneda": ""})
    assert seed2["title"] is None
    assert seed2["price"] is None
    assert seed2["currency"] is None


# ── _matches_re_keyword (pret + monede) ───────────────────────────────────────

def test_match_pret_monede_identice():
    kw = _kw(price_currency="EUR", price_max=400)
    assert _matches_re_keyword({"price": 500, "currency": "EUR"}, kw) is False   # max depasit
    assert _matches_re_keyword({"price": 350, "currency": "EUR"}, kw) is True


def test_match_pret_ron_vs_eur_cu_curs():
    kw = _kw(price_currency="EUR", price_max=400)
    # 1750 RON / 5.0 = 350 EUR <= 400 -> trece
    assert _matches_re_keyword({"price": 1750, "currency": "RON"}, kw, 5.0) is True
    # 2500 RON / 5.0 = 500 EUR > 400 -> respins
    assert _matches_re_keyword({"price": 2500, "currency": "RON"}, kw, 5.0) is False


def test_match_pret_monede_diferite_fara_curs():
    kw = _kw(price_currency="EUR", price_max=400)
    # monede diferite si fara curs (eur_ron None) -> tolerant, nu respinge
    assert _matches_re_keyword({"price": 2500, "currency": "RON"}, kw, None) is True


def test_match_toleranta_valori_necunoscute():
    # criterii setate dar valori extrase necunoscute (None) -> nu se poate verifica -> trece
    kw = _kw(rooms=3, area_min=50, area_max=80, price_max=400)
    assert _matches_re_keyword({"price": None, "rooms": None, "area_sqm": None}, kw) is True


# ── _matches_query_local ──────────────────────────────────────────────────────

def test_query_local_and_diacritice():
    txt = "Garsonieră mobilată Crângași"
    assert _matches_query_local(txt, "crangasi, mobilat") is True    # AND, fara diacritice
    assert _matches_query_local(txt, "crangasi, parcare") is False   # "parcare" lipseste


def test_query_local_gol_trece():
    assert _matches_query_local("orice text", None) is True
    assert _matches_query_local("orice text", "") is True
    assert _matches_query_local("orice text", "   ") is True


# ── _olx_build_url ────────────────────────────────────────────────────────────

def test_olx_build_url_oras_slug():
    url, params = _olx_build_url({"tip_anunt": "inchiriere", "tip_proprietate": "apartament",
                                  "locatie": "București", "camere_min": 2})
    assert "/bucuresti/" in url            # oras normalizat ca segment de path
    assert "-camere" not in url            # camerele NU mai sunt segment de path (deconectate)
    assert params["search[order]"] == "created_at:desc"


def test_olx_build_url_query():
    url, params = _olx_build_url({"locatie": "Cluj-Napoca", "query": "garsoniera"})
    assert "/cluj-napoca/q-garsoniera/" in url   # ordinea oras -> q- (sonda T8)
    assert "search[order]" in params


def test_olx_build_url_fara_locatie():
    url, params = _olx_build_url({"tip_anunt": "inchiriere"})
    assert url.endswith("/imobiliare/apartamente-garsoniere-de-inchiriat/")
    assert "q-" not in url


# ── _passes_imob_filters (suprafata_max nou) ──────────────────────────────────

def test_imob_suprafata_max():
    assert _passes_imob_filters({"suprafata_mp": 90}, {"suprafata_max": 80}) is False
    assert _passes_imob_filters({"suprafata_mp": 90}, {"suprafata_max": 100}) is True
    assert _passes_imob_filters({"suprafata_mp": None}, {"suprafata_max": 80}) is True  # necunoscut -> trece
