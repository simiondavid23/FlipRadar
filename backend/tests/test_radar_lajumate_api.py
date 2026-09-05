"""LJ-1 — cautarea LaJumate pe API-ul JSON public, cu filtre server-side.

DE CE EXISTA: pagina SSR `/anunturi/c/{kw}` IGNORA `?price_min`/`?price_max`/
`?condition`/`?county` — intoarce mereu aceleasi ~28 de anunturi nefiltrate. Cu
filtrarea facuta local doar pe prima pagina, un keyword cu prag strans nu gasea
niciodata nimic ("iphone" 700-2000 RON: zero randuri in productie, ciclu de ciclu).
Testele de aici tin cablat contractul API-ului: numele exacte ale filtrelor, pagina
in PATH (nu in query), lista la `data` si metadatele de paginare.

Fara retea: `_request` e monkeypatch-uit sa intoarca textul unui fixture. LJ-2 a scos
enrichment-ul de detaliu, deci nu mai e nimic de stubuit peste el — cautarea face fix
o cerere, iar `test_search_nu_face_nicio_cerere_de_detaliu` tine asta cablat.

Fixture-urile sunt mostre REALE din sonda SONDA-LJ3 (2026-09-03), curatate: `user` e
redus la {id, name}, ca sa nu intre date de vanzatori in repo. `ad_fields` a fost pus
inapoi la LJ-2 (SONDA-LJ4): poarta starea anuntului si NU contine date personale.
"""
import json
import os
import urllib.parse
from datetime import datetime

import pytest

from app.services.radar import lajumate_scraper as ljs


_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "lajumate")


def _fixture(nume: str) -> str:
    with open(os.path.join(_FIXTURI, f"{nume}.json"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def captura(monkeypatch):
    """Prinde URL-urile cerute si serveste un fixture. Nimic de stubuit peste
    enrichment: LJ-2 l-a scos, `_request` e singura poarta ramasa."""
    stare = {"urls": [], "headers": [], "corp": ""}

    def _fals_request(url, retry_blocked=True, extra_headers=None):
        stare["urls"].append(url)
        stare["headers"].append(extra_headers)
        return stare["corp"]

    monkeypatch.setattr(ljs, "_request", _fals_request)
    return stare


@pytest.fixture
def loguri(monkeypatch):
    """Liniile emise de log_manager, ca (modul, nivel, mesaj)."""
    emise = []
    monkeypatch.setattr(ljs.log_manager, "emit",
                        lambda m, n, msg: emise.append((m, n, msg)))
    return emise


def _qs(query: str) -> dict:
    """Query decodat: parantezele sunt encodate pe fir, aici le vrem lizibile."""
    return urllib.parse.parse_qs(query)


# ── 1-3: _build_query ────────────────────────────────────────────────────────
def test_build_query_toate_cheile_in_ordine():
    q = ljs._build_query("iphone", 2000, 700, "used", "Caraș-Severin",
                         "electronice-si-electrocasnice/telefoane")
    d = _qs(q)
    assert d["filters[name][0]"] == ["iphone"]
    assert d["filters[price_min][0]"] == ["700"]
    assert d["filters[price_max][0]"] == ["2000"]
    assert d["filters[condition][0]"] == ["utilizat"]
    assert d["filters[county][0]"] == ["caras-severin"]
    assert d["parent_id"] == ["electronice-si-electrocasnice"]
    assert d["category_id"] == ["telefoane"]
    assert d["sort"] == ["date_desc"]
    assert d["currency"] == ["lei"]
    # ordinea din captura browserului, pe cheile decodate
    ordine = [urllib.parse.unquote(p.split("=")[0]) for p in q.split("&")]
    assert ordine == [
        "filters[name][0]", "filters[price_min][0]", "filters[price_max][0]",
        "filters[condition][0]", "filters[county][0]",
        "parent_id", "category_id", "sort", "currency",
    ]


def test_build_query_categorie_pe_o_parte_si_fara_categorie():
    o_parte = _qs(ljs._build_query("iphone", None, None, "all", None,
                                   "electronice-si-electrocasnice"))
    assert o_parte["parent_id"] == ["electronice-si-electrocasnice"]
    assert "category_id" not in o_parte

    fara = _qs(ljs._build_query("iphone", None, None, "all", None, None))
    assert "parent_id" not in fara and "category_id" not in fara
    # pragurile absente nu produc chei goale
    assert "filters[price_min][0]" not in fara
    assert "filters[price_max][0]" not in fara
    assert "filters[condition][0]" not in fara
    assert "filters[county][0]" not in fara


def test_pagina_e_in_path_nu_in_query(captura):
    captura["corp"] = _fixture("listing_p2")
    ljs.search_lajumate("iphone", page=2)
    url = captura["urls"][0]
    cale, _, query = url.partition("?")
    assert cale == f"{ljs._API_BASE}/listing/2"
    assert "page" not in _qs(query)


# ── 4: _fetch_page ───────────────────────────────────────────────────────────
def test_fetch_page_mapeaza_anunturile_si_metadatele(captura):
    captura["corp"] = _fixture("listing_p1")
    anunturi, meta = ljs._fetch_page("http://x")

    assert len(anunturi) == 3
    a = anunturi[0]
    assert a["external_id"] == "lajumate_17014725"
    assert a["price"] == 800.0
    assert a["currency"] == "RON"          # API-ul spune "lei"
    assert a["listed_at"] == datetime(2026, 8, 29, 6, 34, 45)
    assert a["url"] == "https://lajumate.ro/ad/clona-iphone-15-pro-max-nefolosit-17014725"
    assert a["images"] and all(u.startswith(ljs._IMG_BASE) for u in a["images"])
    assert meta == {"current_page": 1, "last_page": 2, "total": 34}
    # antetele de API ajung la poarta de retea
    assert captura["headers"][0] == {"Accept": "application/json",
                                     "Origin": "https://lajumate.ro"}


# ── 5-6: search_lajumate ─────────────────────────────────────────────────────
def test_search_pagina_2(captura):
    captura["corp"] = _fixture("listing_p2")
    rez = ljs.search_lajumate("iphone", max_price=2000, min_price=700, page=2)
    assert len(rez) == 2
    url = captura["urls"][0]
    assert "/listing/2?" in url
    assert "filters%5Bname%5D%5B0%5D=iphone" in url
    assert _qs(url.partition("?")[2])["filters[name][0]"] == ["iphone"]


def test_search_peste_ultima_pagina_da_lista_goala(captura, loguri):
    captura["corp"] = _fixture("listing_gol")
    assert ljs.search_lajumate("iphone", page=3) == []
    info = [m for mod, niv, m in loguri if niv == "INFO"]
    assert any("pagina 3 peste ultima (2)" in m for m in info)


# ── 7: corp ne-JSON ──────────────────────────────────────────────────────────
def test_corp_ne_json_da_lista_goala_si_warn(captura, loguri):
    captura["corp"] = "<html>nu e json</html>"
    assert ljs.search_lajumate("iphone") == []
    warn = [m for mod, niv, m in loguri if niv == "WARN"]
    assert any("raspuns API neasteptat" in m for m in warn)


# ── 8: plasa locala ──────────────────────────────────────────────────────────
def test_post_filter_taie_pretul_peste_prag():
    brute = [
        {"title": "ieftin", "price": 900.0},
        {"title": "scump", "price": 5000.0},
        {"title": "fara pret", "price": None},
    ]
    ramase = ljs._post_filter(brute, 2000, 700, [])
    assert [r["title"] for r in ramase] == ["ieftin"]


# ── 8b: zecimalele din pretul API-ului ───────────────────────────────────────
@pytest.mark.parametrize("brut,asteptat", [
    ("800.00", 800.0),      # forma API-ului: doua zecimale, ca string
    ("1299.00", 1299.0),
    ("800,00", 800.0),      # virgula zecimala
    ("1.299,50", 1299.5),   # mii cu punct + zecimale cu virgula
    ("1.300", 1300.0),      # punct = separator de MII (trei cifre dupa el)
    (800, 800.0),           # numar, nu string
    ("", None),
])
def test_pretul_pastreaza_zecimalele(brut, asteptat):
    """Regresie: stergerea oarba a non-cifrelor facea din "800.00" un 80000, adica
    de o suta de ori prea mult — apoi `_post_filter` arunca fiecare anunt si cautarea
    intorcea zero, exact simptomul pentru care exista runda asta."""
    assert ljs._parse_price(brut, "lei")[0] == asteptat


# ── 9 (LJ-2): skip_enrich_ids e acceptat si ignorat ──────────────────────────
def test_skip_enrich_ids_e_acceptat_si_ignorat(captura):
    """Parametrul ramane in semnatura ca `radar_scanner` sa nu aiba nevoie de nicio
    schimbare (D7). Nu mai are consumator, deci nu poate schimba rezultatul."""
    captura["corp"] = _fixture("listing_p1")
    fara = ljs.search_lajumate("iphone")
    captura["urls"].clear()
    cu = ljs.search_lajumate("iphone", skip_enrich_ids={"lajumate_17014725", "x"})
    assert [r["external_id"] for r in cu] == [r["external_id"] for r in fara]
    assert len(captura["urls"]) == 1


# ── 10 (LJ-2): cautarea face EXACT o cerere, cea de lista ────────────────────
def test_search_nu_face_nicio_cerere_de_detaliu(captura):
    """Masuratoarea din SONDA-LJ4: descrierea si imaginile din lista sunt identice cu
    cele din pagina de detaliu, deci fetch-urile per anunt au disparut. Aici se vede
    daca revin: orice cerere in plus fata de cea de lista pica testul."""
    captura["corp"] = _fixture("listing_p1")
    rezultate = ljs.search_lajumate("iphone")
    assert len(rezultate) == 3
    assert len(captura["urls"]) == 1
    assert captura["urls"][0].startswith(f"{ljs._API_BASE}/listing/1?")


# ── 11 (LJ-2): starea vine din ad_fields, cheiata pe `name` ──────────────────
def test_conditia_din_ad_fields(captura):
    """Cele doua `field_key` (`Stare` si `Starea`) poarta ACEEASI stare — SONDA-LJ4 le-a
    gasit pe 13, respectiv 10 din 28 de anunturi. Cheia e `name == "condition"`."""
    captura["corp"] = _fixture("listing_p1")
    p1 = {r["external_id"]: r["condition"] for r in ljs.search_lajumate("iphone")}
    assert p1["lajumate_17013436"] == "second hand"      # field_key "Stare",  "Utilizat"
    assert p1["lajumate_17014725"] == "nou"              # field_key "Stare",  "Nou"

    captura["corp"] = _fixture("listing_p2")
    p2 = {r["external_id"]: r["condition"] for r in ljs.search_lajumate("iphone")}
    assert p2["lajumate_16832164"] == "nou"              # field_key "Starea", "Nou"
    assert p2["lajumate_16820388"] is None               # ad_fields: []


# ── 12 (LJ-2): descrierea si imaginile vin din LISTA, fara niciun fetch ──────
def test_description_si_images_vin_din_lista(captura):
    captura["corp"] = _fixture("listing_p1")
    rezultate = ljs.search_lajumate("iphone")
    dupa_id = {r["external_id"]: r for r in rezultate}
    r = dupa_id["lajumate_17014725"]
    assert r["description"] and len(r["description"]) > 20
    assert "<p>" not in r["description"]                  # _clean_text a scos HTML-ul
    assert r["images"] and all(u.startswith(ljs._IMG_BASE) for u in r["images"])
    assert len(captura["urls"]) == 1


# ── garda: fixture-urile n-au date de vanzatori ──────────────────────────────
@pytest.mark.parametrize("nume", ["listing_p1", "listing_p2"])
def test_fixturile_sunt_curatate_de_date_personale(nume):
    date = json.loads(_fixture(nume))
    for ad in date["data"]:
        assert set(ad["user"].keys()) == {"id", "name"}
        # LJ-2: `ad_fields` e din nou in fixture (poarta starea anuntului). Nu e date
        # personale — sunt atribute de produs — dar tinem lista inchisa, ca o mostra
        # viitoare sa nu strecoare un camp de vanzator pe canalul asta.
        assert isinstance(ad["ad_fields"], list)
        for camp in ad["ad_fields"]:
            assert set(camp.keys()) <= {"id", "ad_id", "field_key", "name",
                                        "value", "original_value", "frontEndSearch"}
            assert camp["name"] in {"condition", "color", "size", "brand",
                                    "currency", "negotiable_price", "person_type"}
    assert "@" not in _fixture(nume)
