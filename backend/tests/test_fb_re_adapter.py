"""FB-4 — Imobiliare Marketplace pe nucleul logat-out, sub comutatorul FB_MOD.

Totul offline: nucleul e inlocuit pe `facebook_real_estate.nucleu_search`, deci nu
pleaca nicio cerere. Anunturile mock sunt dicturi CANONICE, in forma pe care o emite
`parse.canonic` din nucleu (external_id/title/price/currency/location/image_url/
listed_at/category_id/source_url).

Cifrele fixate aici sunt masurate, nu alese: categoria dominanta a chiriilor
(`1468271819871448`, 80.7% la FB-4b, identica cu categoryIDArray-ul paginii
propertyrentals) si zgomotul cert de langa ea (`1583634935226685` = canapele).
"""
from datetime import datetime, timezone

import pytest

from app.services.log_manager import log_manager
from app.scrapers.real_estate import facebook_real_estate as fb

CAT_CHIRII = "1468271819871448"
CAT_CANAPEA = "1583634935226685"
_ACUM = datetime(2026, 8, 15, 9, 30, 0, tzinfo=timezone.utc)


def _canonic(ext_id, *, category_id=CAT_CHIRII, price=1500.0, title="Apartament 2 camere",
             listed_at=_ACUM, location="București", image_url="https://x.invalid/1.jpg",
             currency="RON"):
    """Un anunt in forma emisa de `parse.canonic`."""
    return {
        "external_id": ext_id, "title": title, "price": price, "currency": currency,
        "location": location, "image_url": image_url, "listed_at": listed_at,
        "category_id": category_id,
        "source_url": f"https://www.facebook.com/marketplace/item/{ext_id}/",
    }


@pytest.fixture(autouse=True)
def _env_curat(monkeypatch):
    """Niciun test nu trebuie sa depinda de mediul masinii."""
    for v in ("FB_MOD", "FB_IMOBILIARE_TERMENI_GOL", "FB_IMOBILIARE_CATEGORII",
              "FB_IMOBILIARE_ANCORA"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def warns(monkeypatch):
    mesaje = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda modul, nivel, mesaj: mesaje.append((modul, nivel, mesaj)))
    return mesaje


@pytest.fixture
def nucleu(monkeypatch):
    """Inlocuieste nucleul si jurnalizeaza apelurile. `raspunsuri` = per termen."""
    apeluri = []
    raspunsuri = {}

    def fals(query, lat, lon, *, raza_km=65, city_page_id=None):
        apeluri.append({"query": query, "lat": lat, "lon": lon, "raza_km": raza_km,
                        "city_page_id": city_page_id})
        return raspunsuri.get(query, [])

    monkeypatch.setattr(fb, "nucleu_search", fals)
    fals.apeluri = apeluri
    fals.raspunsuri = raspunsuri
    return fals


# ── 1. dispecerul FB_MOD ─────────────────────────────────────────────────────
def test_fb_mod_logout_merge_pe_nucleu(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspunsuri["chirie"] = [_canonic("1")]

    rez = fb.search_facebook_real_estate("chirie", {})

    assert len(nucleu.apeluri) == 1
    assert len(rez) == 1


def test_fb_mod_sesiune_nu_atinge_nucleul(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "sesiune")

    # fara session_path calea de sesiune se opreste devreme, fara Playwright
    rez = fb.search_facebook_real_estate("chirie", {})

    assert nucleu.apeluri == []
    assert rez == []


def test_fb_mod_absent_inseamna_sesiune(nucleu):
    """Implicitul e DELIBERAT `sesiune`: dupa FB-4 productia se comporta ca azi."""
    rez = fb.search_facebook_real_estate("chirie", {})

    assert nucleu.apeluri == []
    assert rez == []


def test_fb_mod_necunoscut_cade_pe_sesiune_cu_warn(monkeypatch, nucleu, warns):
    monkeypatch.setenv("FB_MOD", "hibrid")

    rez = fb.search_facebook_real_estate("chirie", {})

    assert nucleu.apeluri == [], "o valoare necunoscuta nu are voie sa deschida calea noua"
    assert rez == []
    assert any("hibrid" in m for _, niv, m in warns if niv == "WARN"), warns


# ── 2. expandarea keyword-ului gol ───────────────────────────────────────────
def test_keyword_gol_se_expandeaza_in_cei_opt_termeni(nucleu):
    fb._search_logout("", {})

    assert [a["query"] for a in nucleu.apeluri] == [
        "chirie", "inchiriez", "de inchiriat", "apartament",
        "garsoniera", "casa", "camera", "regim hotelier"]


def test_keyword_nevid_da_un_singur_termen(nucleu):
    fb._search_logout("  garsoniera Cluj  ", {})

    assert [a["query"] for a in nucleu.apeluri] == ["garsoniera Cluj"]


def test_termenii_pentru_gol_sunt_configurabili(monkeypatch, nucleu):
    monkeypatch.setenv("FB_IMOBILIARE_TERMENI_GOL", "chirie, casa ")

    fb._search_logout("", {})

    assert [a["query"] for a in nucleu.apeluri] == ["chirie", "casa"]


# ── 3. filtrul de categorie ──────────────────────────────────────────────────
def test_filtrul_de_categorie_taie_zgomotul_si_pastreaza_necunoscutul(nucleu):
    """Canapeaua (zgomotul masurat la FB-4b pe `casa`/`camera`) e respinsa;
    anuntul FARA categorie se pastreaza — lipsa campului nu e dovada de zgomot."""
    nucleu.raspunsuri["chirie"] = [
        _canonic("1", category_id=CAT_CHIRII),
        _canonic("2", category_id=CAT_CANAPEA, title="Canapea extensibila"),
        _canonic("3", category_id=None),
    ]

    rez = fb._search_logout("chirie", {})

    assert {r["external_id"] for r in rez} == {"1", "3"}


def test_categoriile_permise_sunt_configurabile(monkeypatch, nucleu):
    monkeypatch.setenv("FB_IMOBILIARE_CATEGORII", f"{CAT_CHIRII},{CAT_CANAPEA}")
    nucleu.raspunsuri["chirie"] = [
        _canonic("1", category_id=CAT_CHIRII),
        _canonic("2", category_id=CAT_CANAPEA),
        _canonic("3", category_id=None),
    ]

    rez = fb._search_logout("chirie", {})

    assert {r["external_id"] for r in rez} == {"1", "2", "3"}


def test_sumarul_de_filtrare_ajunge_in_jurnal(nucleu, warns):
    nucleu.raspunsuri["chirie"] = [
        _canonic("1"), _canonic("2", category_id=CAT_CANAPEA), _canonic("3", category_id=None)]

    fb._search_logout("chirie", {})

    sumar = [m for _, niv, m in warns if niv == "OK"]
    assert sumar and "respinse" in sumar[-1]


# ── 4. listed_at: string ISO care se intoarce aware ──────────────────────────
def test_listed_at_e_string_iso_care_supravietuieste_lui_fromisoformat(nucleu):
    """Paritatea promisa la FB-1: `canonic` da datetime UTC AWARE, iar
    `_seed_from_raw` face `datetime.fromisoformat` pe string. Stringul ISO poarta
    offsetul, deci nu se pierde fusul (SQLite ar fi intors naiv un datetime brut)."""
    nucleu.raspunsuri["chirie"] = [_canonic("1", listed_at=_ACUM)]

    rez = fb._search_logout("chirie", {})

    brut = rez[0]["listed_at"]
    assert isinstance(brut, str)
    intors = datetime.fromisoformat(brut)
    assert intors.tzinfo is not None
    assert intors == _ACUM


def test_listed_at_lipsa_ramane_none(nucleu):
    nucleu.raspunsuri["chirie"] = [_canonic("1", listed_at=None)]

    assert fb._search_logout("chirie", {})[0]["listed_at"] is None


# ── 5. maparea campurilor pe contractul _seed_from_raw ───────────────────────
def test_maparea_campurilor_pentru_seed_from_raw(nucleu):
    nucleu.raspunsuri["chirie"] = [_canonic(
        "998877", title="Garsoniera Centru", price=1234.5, currency="EUR",
        location="Cluj-Napoca", image_url="https://x.invalid/p.jpg")]

    r = fb._search_logout("chirie", {})[0]

    assert r["external_id"] == "998877" and isinstance(r["external_id"], str)
    assert r["title"] == "Garsoniera Centru"
    assert r["price"] == 1234.5
    assert r["currency"] == "EUR"
    assert r["location"] == "Cluj-Napoca"
    assert r["image_url"] == "https://x.invalid/p.jpg"
    assert r["url"] == "https://www.facebook.com/marketplace/item/998877/"
    assert r["source_url"] == r["url"]
    assert r["platform"] == "facebook_marketplace"
    # descrierea NU exista pe calea de lista — o aduce fetch_detail in fluxul
    # scanner-ului, exact ca la cardurile fara descriere de pe sesiune
    assert not r.get("description")


def test_seed_from_raw_digera_dictul_produs(nucleu):
    """Contractul e verificat contra consumatorului REAL, nu contra unei liste
    copiate in test."""
    from app.services.real_estate_scanner import _seed_from_raw

    nucleu.raspunsuri["chirie"] = [_canonic("55", price=900.0, currency="RON",
                                            location="Brasov")]
    r = fb._search_logout("chirie", {})[0]

    seed = _seed_from_raw(r)

    assert seed["title"] == "Apartament 2 camere"
    assert seed["price"] == 900.0
    assert seed["currency"] == "RON"
    assert seed["zone_hint"] == "Brasov"
    assert seed["listed_at"] == _ACUM


# ── 6. filtrul de pret si dedup ──────────────────────────────────────────────
def test_pretul_respecta_marginile_keyword_ului(nucleu):
    nucleu.raspunsuri["chirie"] = [
        _canonic("1", price=500.0), _canonic("2", price=1500.0), _canonic("3", price=5000.0)]

    rez = fb._search_logout("chirie", {"pret_min": 1000, "pret_max": 2000})

    assert {r["external_id"] for r in rez} == {"2"}


def test_anuntul_fara_pret_e_sarit(nucleu):
    nucleu.raspunsuri["chirie"] = [_canonic("1", price=None), _canonic("2", price=0.0),
                                   _canonic("3", price=1200.0)]

    assert {r["external_id"] for r in fb._search_logout("chirie", {})} == {"3"}


def test_dedup_intre_termeni(nucleu):
    """Nucleul dedupe doar in interiorul unui apel; peste termeni e treaba noastra."""
    nucleu.raspunsuri["chirie"] = [_canonic("100"), _canonic("101")]
    nucleu.raspunsuri["inchiriez"] = [_canonic("100"), _canonic("102")]
    import os
    os.environ["FB_IMOBILIARE_TERMENI_GOL"] = "chirie,inchiriez"
    try:
        rez = fb._search_logout("", {})
    finally:
        del os.environ["FB_IMOBILIARE_TERMENI_GOL"]

    assert [r["external_id"] for r in rez] == ["100", "101", "102"]


# ── 7. ancora ────────────────────────────────────────────────────────────────
def test_ancora_implicita_e_bucuresti(nucleu):
    fb._search_logout("chirie", {})

    a = nucleu.apeluri[0]
    assert (a["lat"], a["lon"]) == (44.4325, 26.1025)
    assert a["city_page_id"] == "114304211920174"
    assert a["raza_km"] == 65.0


def test_ancora_se_poate_schimba_din_env(monkeypatch, nucleu):
    monkeypatch.setenv("FB_IMOBILIARE_ANCORA", "cluj-napoca")

    fb._search_logout("chirie", {})

    a = nucleu.apeluri[0]
    assert (a["lat"], a["lon"]) == (46.7712, 23.6236)
    assert a["city_page_id"] == "109529709065736", \
        "Cluj are ID masurat ca ancoreaza corect (FBS-0b)"


def test_ancora_necunoscuta_cade_pe_bucuresti_cu_warn(monkeypatch, nucleu, warns):
    monkeypatch.setenv("FB_IMOBILIARE_ANCORA", "atlantida")

    fb._search_logout("chirie", {})

    assert (nucleu.apeluri[0]["lat"], nucleu.apeluri[0]["lon"]) == (44.4325, 26.1025)
    assert any("atlantida" in m for _, niv, m in warns if niv == "WARN"), warns


# ── 8. guard-ul de categorie, identic pe ambele cai ──────────────────────────
@pytest.mark.parametrize("cale", ["_search_logout", "_search_sesiune"])
def test_guardul_de_categorie_respinge_la_fel_pe_ambele_cai(nucleu, warns, cale):
    """`vanzare` (propertyforsale) e NECONFIRMATA — ambele cai se opresc inainte de
    orice cerere sau browser. Calea de sesiune nu ajunge la Playwright: guard-ul e
    primul lucru din corp."""
    fn = getattr(fb, cale)
    rez = fn("chirie", {"tip_anunt": "vanzare"})

    assert rez == []
    assert nucleu.apeluri == []
    assert any("neconfirmata" in m for _, niv, m in warns if niv == "WARN"), warns


def test_guardul_lasa_sa_treaca_inchirierea(nucleu):
    nucleu.raspunsuri["chirie"] = [_canonic("1")]

    assert len(fb._search_logout("chirie", {"tip_anunt": "inchiriere"})) == 1
