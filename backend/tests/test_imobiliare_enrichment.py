"""IMO-1 — enrichment de detaliu OLX Imobiliare + rooms_max + zona in q-.

Toate testele sunt PURE: fara retea, fara DB. Fixture-ul de detaliu e un dict inline
pe forma /api/v1/offers/{id} (fixture-ul existent tests/fixtures/olx_offer.json e cel
de Radar — trimis, fara photos/location/params — deci nu acopera mapările de aici).
"""
import json
from types import SimpleNamespace

from bs4 import BeautifulSoup

from app.scrapers.real_estate.olx_real_estate import (
    _extract_numeric_ids, _map_offer_details, _pick_thumb,
)
from app.services.real_estate_scanner import _matches_re_keyword, _olx_query_with_zone


_CDN = "https://frankfurt.apollo.olxcdn.com:443/v1/files"


def _offer():
    """Raspuns (data) de la /api/v1/offers/{id} — forma REALA, capturata live de
    sonda IMO-DIAG (07.2026) pe un anunt din categoria 1165 (real_estate).

    Ce e captura fidela: `params` (cheile reale compartimentare/price/m/constructie/
    floor si forma lor de `value`), `photos[].link` cu placeholder-ul {width}x{height},
    `location` (orasul vine FARA diacritice din API), `created_time` cu offset.
    Descrierea e reprezentativa (sonda a confirmat maparea, nu i-am dumpat HTML-ul brut).
    """
    return {
        "id": 305879807,
        "description": "<p>Apartament <b>renovat</b>,\n\n  zona linistita.</p>",
        "created_time": "2026-06-25T13:00:34+03:00",
        "photos": [
            {"link": f"{_CDN}/98eleil3zi6m3-RO/image;s={{width}}x{{height}}"},
            {"link": f"{_CDN}/gppfm2zyo2601-RO/image;s={{width}}x{{height}}"},
            {"link": f"{_CDN}/c3-RO/image;s={{width}}x{{height}}"},
            {"link": f"{_CDN}/d4-RO/image;s={{width}}x{{height}}"},
            {"link": f"{_CDN}/e5-RO/image;s={{width}}x{{height}}"},
            {"link": f"{_CDN}/f6-RO/image;s={{width}}x{{height}}"},  # al 6-lea — taiat
        ],
        "location": {
            "city": {"id": 1, "name": "Bucuresti", "normalized_name": "bucuresti"},
            "district": {"id": 9, "name": "Sectorul 5"},
            "region": {"id": 46, "name": "Bucuresti - Ilfov"},
        },
        # Cheile REALE. NU exista `rooms` — vezi test_camere_nu_vine_din_params_reale.
        "params": [
            {"key": "compartimentare", "name": "Compartimentare",
             "value": {"key": "decomandat", "label": "Decomandat"}},
            {"key": "price", "name": "Pret",
             "value": {"value": 121000, "type": "arranged", "currency": "EUR", "negotiable": True}},
            {"key": "m", "name": "Suprafata utila", "value": {"key": "62", "label": "62 m²"}},
            {"key": "constructie", "name": "An constructie",
             "value": {"key": "dupa-2000", "label": "Dupa 2000"}},
            {"key": "floor", "name": "Etaj", "value": {"key": "parter", "label": "Parter"}},
        ],
    }


# ── _map_offer_details ──────────────────────────────────────────────────────────
def test_descriere_fara_html_si_whitespace_colapsat():
    out = _map_offer_details(_offer())
    assert "<p>" not in out["descriere"] and "<b>" not in out["descriere"]
    # Tag-urile devin spatii (identic cu radar._map_olx_offer), deci ramane un spatiu
    # inainte de virgula; newline-urile si spatiile multiple se colapseaza.
    assert out["descriere"] == "Apartament renovat , zona linistita."
    assert "\n" not in out["descriere"] and "  " not in out["descriere"]


def test_poze_maxim_5_cu_placeholder_inlocuit():
    out = _map_offer_details(_offer())
    assert len(out["images"]) == 5
    assert out["images"][0] == f"{_CDN}/98eleil3zi6m3-RO/image;s=1000x700"
    assert all("{width}" not in u for u in out["images"])


def test_cartierul_devine_zone():
    # location.district = intrarea directa in normalize_zone (mai specific decat orasul).
    # Pe Bucuresti districtul e SECTORUL; orasul vine fara diacritice din API.
    out = _map_offer_details(_offer())
    assert out["zone"] == "Sectorul 5"
    assert out["locatie_oras"] == "Bucuresti"


def test_params_mapate():
    """Doar ce vine REAL din params: suprafata (key="m") si etajul (key="floor").
    Etajul e un LABEL text ("Parter"/"Demisol"), nu un numar — asa il trimite OLX."""
    out = _map_offer_details(_offer())
    assert out["suprafata_mp"] == 62.0
    assert out["etaj"] == "Parter"


def test_camere_nu_vine_din_params_reale():
    """SANTINELA (sonda IMO-DIAG, 07.2026): OLX Imobiliare NU expune numarul de camere
    in `params` — cheile reale sunt compartimentare/price/m/constructie/floor, iar
    `key_params` e ["m"]. Camerele traiesc doar in titlu/descriere, de unde le ia
    extract_rooms. Daca testul asta pica, OLX a schimbat API-ul (vezi ramura-plasa)."""
    out = _map_offer_details(_offer())
    assert "camere" not in out
    chei = [p["key"] for p in _offer()["params"]]
    assert "rooms" not in chei
    assert not any("camere" in p["name"].lower() for p in _offer()["params"])


def test_params_nemapate_sunt_ignorate():
    # price/compartimentare/constructie exista in raspuns, dar nu au corespondent la noi.
    out = _map_offer_details(_offer())
    assert set(out) == {"descriere", "images", "zone", "locatie_oras",
                        "suprafata_mp", "etaj", "listed_at"}


def test_listed_at_e_string_iso_naiv():
    out = _map_offer_details(_offer())
    # Acelasi format ca cel emis din card: string ISO naiv local (fara offset).
    assert isinstance(out["listed_at"], str)
    assert "+" not in out["listed_at"] and out["listed_at"].startswith("2026-06-25")


def test_dict_gol_da_dict_gol():
    assert _map_offer_details({}) == {}


def test_tip_gresit_nu_crapa():
    assert _map_offer_details(None) == {}
    assert _map_offer_details("nu-i dict") == {}


def test_ramura_plasa_rooms_daca_olx_o_adauga():
    """FIXTURE SINTETIC — forma pe care OLX NU o trimite azi (confirmat de sonda
    IMO-DIAG). Testeaza PLASA DE SIGURANTA din _map_offer_details, nu realitatea:
    daca OLX adauga vreodata `rooms` in params, maparea se auto-activeaza."""
    out = _map_offer_details({"params": [
        {"key": "rooms", "name": "Numar camere", "value": {"key": "3", "label": "3 camere"}},
    ]})
    assert out["camere"] == 3


def test_ramura_plasa_rooms_dupa_nume():
    """Idem — varianta pe nume ("camere" in name), tot sintetica."""
    out = _map_offer_details({"params": [
        {"key": "altceva", "name": "Număr camere", "value": {"key": "2", "label": "2 camere"}},
    ]})
    assert out["camere"] == 2


def test_params_corupte_sunt_tolerate():
    data = {"params": [
        {"key": "m", "value": {"key": None, "label": None}},      # fara valoare
        {"key": "rooms", "value": "nu-i dict"},                   # value de alt tip
        "nu-i dict",                                               # element de alt tip
        {"key": "floor", "value": {"label": "Parter"}},           # doar label -> merge
    ]}
    out = _map_offer_details(data)
    assert "suprafata_mp" not in out and "camere" not in out
    assert out["etaj"] == "Parter"


def test_chei_lipsa_nu_apar_in_dict():
    # Caller-ul pastreaza ce are pe card pentru cheile absente.
    out = _map_offer_details({"description": "doar descriere"})
    assert out == {"descriere": "doar descriere"}


def test_poze_fara_placeholder_raman_neatinse():
    out = _map_offer_details({"photos": [{"link": "https://img.olx.ro/x.jpg"}, {"nu_e_link": 1}]})
    assert out["images"] == ["https://img.olx.ro/x.jpg"]


def test_created_time_corupt_nu_da_listed_at():
    assert "listed_at" not in _map_offer_details({"created_time": "maine"})


# ── _extract_numeric_ids ────────────────────────────────────────────────────────
def _html_cu_state(ads):
    """HTML sintetic: __PRERENDERED_STATE__ = "<json escapat>" (dublu json.dumps)."""
    state = {"listing": {"listing": {"ads": ads}}}
    return f"<script>window.__PRERENDERED_STATE__ = {json.dumps(json.dumps(state))};</script>"


def test_extrage_maparea_token_la_numeric():
    html = _html_cu_state([
        {"id": 111, "url": "https://www.olx.ro/d/oferta/apartament-IDabc123.html"},
        {"id": 222, "url": "/d/oferta/garsoniera-IDxyz789.html"},
    ])
    assert _extract_numeric_ids(html) == {"abc123": 111, "xyz789": 222}


def test_accepta_si_urlpath():
    html = _html_cu_state([{"id": 333, "urlPath": "/d/oferta/casa-IDqwe456.html"}])
    assert _extract_numeric_ids(html) == {"qwe456": 333}


def test_html_fara_state_da_dict_gol():
    assert _extract_numeric_ids("<html><body>nimic</body></html>") == {}


def test_state_corupt_da_dict_gol():
    assert _extract_numeric_ids('<script>window.__PRERENDERED_STATE__ = "{nu e json}";</script>') == {}


def test_ads_fara_id_sau_url_sunt_sarite():
    html = _html_cu_state([
        {"url": "/d/oferta/x-IDaaa.html"},          # fara id
        {"id": 444, "url": "/d/oferta/fara-token"},  # fara -ID<token>.html
        {"id": 555, "url": "/d/oferta/ok-IDbbb.html"},
    ])
    assert _extract_numeric_ids(html) == {"bbb": 555}


# ── _pick_thumb (fallback srcset) ───────────────────────────────────────────────
def _img(html):
    return BeautifulSoup(html, "html.parser").find("img")


def test_srcset_cand_src_e_placeholder_data_uri():
    img = _img('<img src="data:image/gif;base64,R0lGOD" '
               'srcset="https://img.olx.ro/mic.jpg 200w, https://img.olx.ro/mare.jpg 800w">')
    assert _pick_thumb(img) == "https://img.olx.ro/mare.jpg"  # ultimul = rezolutia maxima


def test_srcset_cand_src_lipseste():
    img = _img('<img srcset="https://img.olx.ro/a.jpg 200w, https://img.olx.ro/b.jpg 800w">')
    assert _pick_thumb(img) == "https://img.olx.ro/b.jpg"


def test_src_real_are_prioritate_peste_srcset():
    img = _img('<img src="https://img.olx.ro/real.jpg" srcset="https://img.olx.ro/alt.jpg 800w">')
    assert _pick_thumb(img) == "https://img.olx.ro/real.jpg"


def test_fara_img_da_none():
    assert _pick_thumb(None) is None


def test_data_uri_fara_srcset_ramane_cum_e():
    img = _img('<img src="data:image/gif;base64,R0lGOD">')
    assert _pick_thumb(img).startswith("data:")


# ── rooms_max in _matches_re_keyword ────────────────────────────────────────────
def _kw(**over):
    base = dict(price_currency="EUR", price_min=None, price_max=None, rooms=None,
                rooms_max=None, area_min=None, area_max=None, floor_min=None,
                floor_max=None, furnished=None, zone=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_rooms_max_respinge_peste_plafon():
    assert _matches_re_keyword({"rooms": 2}, _kw(rooms_max=1)) is False


def test_rooms_max_accepta_pe_plafon():
    # Garsoniera: min 1 + max 1.
    assert _matches_re_keyword({"rooms": 1}, _kw(rooms=1, rooms_max=1)) is True


def test_rooms_max_fara_camere_extrase_e_tolerant():
    assert _matches_re_keyword({"rooms": None}, _kw(rooms_max=1)) is True


def test_fara_rooms_max_totul_trece():
    assert _matches_re_keyword({"rooms": 5}, _kw()) is True


def test_semantica_de_minim_ramane_neschimbata():
    assert _matches_re_keyword({"rooms": 3}, _kw(rooms=2)) is True
    assert _matches_re_keyword({"rooms": 1}, _kw(rooms=2)) is False


def test_min_si_max_impreuna_definesc_un_interval():
    kw = _kw(rooms=2, rooms_max=3)
    assert _matches_re_keyword({"rooms": 1}, kw) is False
    assert _matches_re_keyword({"rooms": 2}, kw) is True
    assert _matches_re_keyword({"rooms": 3}, kw) is True
    assert _matches_re_keyword({"rooms": 4}, kw) is False


# ── _olx_query_with_zone ────────────────────────────────────────────────────────
def test_query_si_zona_se_concateneaza():
    assert _olx_query_with_zone("garsoniera", "crangasi") == "garsoniera crangasi"


def test_doar_zona():
    assert _olx_query_with_zone(None, "crangasi") == "crangasi"


def test_doar_query():
    assert _olx_query_with_zone("garsoniera", None) == "garsoniera"


def test_ambele_goale_dau_none():
    assert _olx_query_with_zone(None, None) is None


def test_stringuri_goale_sunt_ignorate():
    assert _olx_query_with_zone("", "  ") is None
    assert _olx_query_with_zone("  garsoniera  ", "") == "garsoniera"
