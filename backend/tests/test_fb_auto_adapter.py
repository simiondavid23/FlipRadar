"""FB-5 — Auto pe nucleul logat-out, sub comutatorul FB_MOD.

Offline: nucleul e inlocuit pe `facebook_auto_scraper.nucleu_search`; calea de
sesiune se stubueaza la nivelul lui `_fetch`/`_iter_listing_objects`, ca in
test_fb_category_filter.

Supapa de model (A5.1) e testata pe AMBELE cai prin helperul comun — e
comportamentul care deosebeste un feed util de unul gol si tacut.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.scrapers.auto.listings import facebook_auto_scraper as fa

VEH = fa._vehicles_category_id()
_AWARE = datetime(2026, 8, 15, 6, 30, 0, tzinfo=timezone.utc)


def _canonic(ext_id="1", *, title="BMW 320d Touring 2015 150000 km", price=8000.0,
             category_id=VEH, listed_at=_AWARE, image_url="https://x.invalid/1.jpg",
             currency="EUR", location="Cluj-Napoca"):
    return {
        "external_id": ext_id, "title": title, "price": price, "currency": currency,
        "location": location, "image_url": image_url, "listed_at": listed_at,
        "category_id": category_id,
        "source_url": f"https://www.facebook.com/marketplace/item/{ext_id}/",
    }


def _brut(oid="1", *, title="BMW 320d Touring 2015 150000 km", pret="8000",
          category_id=VEH):
    """Obiect BRUT de Facebook, pentru calea de sesiune."""
    o = {"id": oid, "marketplace_listing_title": title,
         "listing_price": {"amount": pret, "formatted_amount": f"€{pret}"}}
    if category_id is not None:
        o["marketplace_listing_category_id"] = category_id
    return o


@pytest.fixture(autouse=True)
def _env_curat(monkeypatch):
    for v in ("FB_MOD", "FB_AUTO_ANCORA"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    capturate = []
    monkeypatch.setattr(fa.log_manager, "emit",
                        lambda modul, nivel, mesaj: capturate.append((nivel, mesaj)))
    return capturate


@pytest.fixture
def nucleu(monkeypatch):
    apeluri, raspuns = [], []

    def fals(query, lat, lon, *, raza_km=65, fb_slug=None):
        apeluri.append({"query": query, "lat": lat, "lon": lon, "raza_km": raza_km,
                        "fb_slug": fb_slug})
        return list(raspuns)

    monkeypatch.setattr(fa, "nucleu_search", fals)
    fals.apeluri, fals.raspuns = apeluri, raspuns
    return fals


@pytest.fixture
def sesiune(monkeypatch):
    """Calea de sesiune, stubuita pana la lista de obiecte brute."""
    obiecte = []
    monkeypatch.setattr(fa, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fa, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fa, "_fetch", lambda url, c: (
        "<html></html>", "https://www.facebook.com/marketplace/search/"))
    monkeypatch.setattr(fa, "_iter_listing_objects", lambda h: list(obiecte))
    return obiecte


def _warn(logs):
    return [m for niv, m in logs if niv == "WARN"]


# ── 6. dispecerul ────────────────────────────────────────────────────────────
def test_logout_merge_pe_nucleu(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic())

    rez = fa.search_facebook_auto("bmw", {})

    assert len(nucleu.apeluri) == 1 and len(rez) == 1


def test_sesiune_nu_atinge_nucleul(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "sesiune")

    assert fa.search_facebook_auto("bmw", {}) == []      # fara session_path
    assert nucleu.apeluri == []


def test_fb_mod_absent_inseamna_sesiune(nucleu):
    assert fa.search_facebook_auto("bmw", {}) == []
    assert nucleu.apeluri == []


def test_fb_mod_necunoscut_cade_pe_sesiune_cu_warn(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "hibrid")

    fa.search_facebook_auto("bmw", {})

    assert nucleu.apeluri == []
    assert any("hibrid" in m for m in _warn(logs)), _warn(logs)


@pytest.mark.parametrize("mod", ["logout", "sesiune"])
def test_pagina_peste_1_si_query_gol(monkeypatch, nucleu, mod):
    monkeypatch.setenv("FB_MOD", mod)
    nucleu.raspuns.append(_canonic())

    assert fa.search_facebook_auto("bmw", {}, page=2) == []
    assert fa.search_facebook_auto("  ", {}) == []
    assert nucleu.apeluri == []


# ── 7. filtrele pe calea logout ──────────────────────────────────────────────
def test_categoria_de_vehicule(monkeypatch, nucleu):
    """Regula PROPRIE a modulului Auto: categoria absenta se pastreaza, una prezenta
    si diferita exclude. E alta decat A6/A7 de la Radar, deliberat."""
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([
        _canonic("1", category_id=VEH),
        _canonic("2", category_id="999", title="BMW jante aliaj"),
        _canonic("3", category_id=None, title="BMW 318i"),
    ])

    rez = fa.search_facebook_auto("bmw", {})

    assert {r["external_id"] for r in rez} == {"fb_1", "fb_3"}


def test_marca_e_filtru_dur(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([_canonic("1", title="BMW 320d"),
                           _canonic("2", title="Opel Mokka")])

    rez = fa.search_facebook_auto("bmw", {"make": "BMW"})

    assert {r["external_id"] for r in rez} == {"fb_1"}


def test_pretul_maxim(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([_canonic("1", price=5000.0), _canonic("2", price=20000.0)])

    rez = fa.search_facebook_auto("bmw", {"price_max": "10000"})

    assert {r["external_id"] for r in rez} == {"fb_1"}


def test_year_si_km_din_titlu(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("1", title="BMW 320d Touring 2015 150000 km"))

    r = fa.search_facebook_auto("bmw", {})[0]

    assert r["year"] == 2015
    assert r["km"] == 150000


def test_dedup_pe_external_id(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.extend([_canonic("5"), _canonic("5"), _canonic("6")])

    assert [r["external_id"] for r in fa.search_facebook_auto("bmw", {})] == ["fb_5", "fb_6"]


# ── 8. SUPAPA de model (A5.1), pe AMBELE cai ────────────────────────────────
def _ruleaza(cale, monkeypatch, nucleu, sesiune, titluri, filters):
    if cale == "logout":
        monkeypatch.setenv("FB_MOD", "logout")
        nucleu.raspuns.extend(_canonic(str(i), title=t) for i, t in enumerate(titluri, 1))
        return fa.search_facebook_auto("bmw", filters)
    sesiune.extend(_brut(str(i), title=t) for i, t in enumerate(titluri, 1))
    return fa.search_facebook_auto("bmw", filters, session_path="s.json")


@pytest.mark.parametrize("cale", ["logout", "sesiune"])
def test_supapa_pastreaza_anunturile_marcii_cand_modelul_ar_goli(
        monkeypatch, nucleu, sesiune, logs, cale):
    """Cazul care conteaza: titlurile FB scriu „320d", nu „Seria 3". Fara supapa,
    feed-ul ar fi gol si tacut."""
    rez = _ruleaza(cale, monkeypatch, nucleu, sesiune,
                   ["BMW 320d Touring", "BMW 318i"], {"make": "BMW", "model": "Seria 3"})

    assert len(rez) == 2, "modelul ar fi golit lista -> supapa il ignora"
    assert any("nu apare in niciun titlu" in m for m in _warn(logs)), _warn(logs)


@pytest.mark.parametrize("cale", ["logout", "sesiune"])
def test_modelul_taie_cand_are_pe_ce(monkeypatch, nucleu, sesiune, logs, cale):
    rez = _ruleaza(cale, monkeypatch, nucleu, sesiune,
                   ["BMW 320d Touring", "BMW 118i"], {"make": "BMW", "model": "320d"})

    assert [r["title"] for r in rez] == ["BMW 320d Touring"]
    assert not any("nu apare in niciun titlu" in m for m in _warn(logs))


@pytest.mark.parametrize("cale", ["logout", "sesiune"])
def test_lista_goala_ramane_goala_fara_warn(monkeypatch, nucleu, sesiune, logs, cale):
    """Supapa nu inventeaza rezultate."""
    rez = _ruleaza(cale, monkeypatch, nucleu, sesiune, [], {"make": "BMW", "model": "Seria 3"})

    assert rez == []
    assert not any("nu apare in niciun titlu" in m for m in _warn(logs))


def test_helperul_de_supapa_e_pur():
    """Contractul helperului comun, direct."""
    r = [{"title": "BMW 320d"}, {"title": "BMW 118i"}]

    pastrate, sarite = fa._aplica_model_supapa(r, "320d", "320d", "BMW")
    assert [x["title"] for x in pastrate] == ["BMW 320d"] and sarite == 1

    pastrate, sarite = fa._aplica_model_supapa(r, "seria 3", "Seria 3", "BMW")
    assert pastrate == r and sarite == 0

    assert fa._aplica_model_supapa([], "seria 3", "Seria 3", "BMW") == ([], 0)


# ── 9. maparea ───────────────────────────────────────────────────────────────
def test_maparea_campurilor(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    nucleu.raspuns.append(_canonic("77", title="BMW 320d 2015", price=9500.0,
                                   currency="EUR", location="Brasov"))

    r = fa.search_facebook_auto("bmw", {})[0]

    assert set(r) == {"external_id", "platform", "title", "price", "currency", "year",
                      "km", "location", "url", "source_url", "thumbnail_url",
                      "image_url", "seller_name", "listed_at", "description"}
    assert r["external_id"] == "fb_77"
    assert r["platform"] == "facebook_auto"
    assert r["url"] == r["source_url"] == "https://www.facebook.com/marketplace/item/77/"
    assert r["thumbnail_url"] == r["image_url"] == "https://x.invalid/1.jpg"
    assert r["seller_name"] is None, "vanzatorul nu exista logat-out"
    assert r["description"] is None


def test_listed_at_naiv_local(monkeypatch, nucleu):
    monkeypatch.setenv("FB_MOD", "logout")
    aware = datetime.now(timezone.utc) - timedelta(hours=5)
    nucleu.raspuns.append(_canonic("1", listed_at=aware))

    r = fa.search_facebook_auto("bmw", {})[0]

    assert r["listed_at"].tzinfo is None
    varsta_naiva = datetime.now() - r["listed_at"]
    varsta_utc = datetime.now(timezone.utc) - aware
    assert abs((varsta_naiva - varsta_utc).total_seconds()) < 5


def test_ancora_implicita_si_configurabila(monkeypatch, nucleu, logs):
    monkeypatch.setenv("FB_MOD", "logout")
    fa.search_facebook_auto("bmw", {})
    a = nucleu.apeluri[0]
    assert (a["lat"], a["lon"], a["fb_slug"]) == (44.4325, 26.1025, "bucharest")

    monkeypatch.setenv("FB_AUTO_ANCORA", "timisoara")
    fa.search_facebook_auto("bmw", {})
    assert (nucleu.apeluri[1]["lat"], nucleu.apeluri[1]["lon"]) == (45.7489, 21.2087)

    monkeypatch.setenv("FB_AUTO_ANCORA", "atlantida")
    fa.search_facebook_auto("bmw", {})
    assert (nucleu.apeluri[2]["lat"], nucleu.apeluri[2]["lon"]) == (44.4325, 26.1025)
    assert any("atlantida" in m for m in _warn(logs))
