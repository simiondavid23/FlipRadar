"""RETAIL-3a — refresh pe URL direct (refresh_source) + persistarea stocului.

Fara retea: extractorul, scraperele de cautare si fetch-ul PCGarage sunt stub-uite.
Acopera cele trei cai ale lui refresh_source (url / pcgarage / search), fallback-ul
de pe pagina de produs pe cautare, wrapper-ul back-compat, regula "None nu
suprascrie stocul cunoscut" in ambele consumatoare (alert_checker + refresh manual)
si o santinela pe continutul VALIDATED_DOMAINS.
"""
import pytest

from app.database import SessionLocal
from app.models.product import Product
from app.models.product_source import ProductSource
from app.services import catalog_health_watchdog, scraper_service as ss
from app.services.product_page_extractor import VALIDATED_DOMAINS, ProductExtractionError
from app.utils.alert_checker import _refresh_all_scrapeable_products

EMAG_URL = "https://www.emag.ro/produs-test/pd/XYZ/"
SOLE_URL = "https://sole.ro/ten/produs-test-f1"
PCG_URL = "https://www.pcgarage.ro/placi-video/test/"


def _extracted(**over):
    base = {
        "name": "Produs test", "price": 249.99, "currency": "RON", "in_stock": True,
        "is_aggregate": False, "image_url": None, "canonical_url": EMAG_URL,
        "domain": "emag.ro", "method": "jsonld", "override_applied": False,
    }
    base.update(over)
    return base


def _fake_search(price=88.0, url=EMAG_URL, name="Produs test"):
    """Scraper de cautare fals, cu semnatura (query, max_results) ca cele reale."""
    def _scraper(query, max_results=20):
        return [{"source_url": url, "price": price, "name": name, "currency": "RON"}]
    return _scraper


@pytest.fixture
def spy_extract(monkeypatch):
    """Inregistreaza apelurile catre extractor si intoarce/arunca ce vrea testul."""
    state = {"calls": [], "result": _extracted(), "error": None}

    def _extract(url, max_retries=3):
        state["calls"].append(url)
        if state["error"] is not None:
            raise state["error"]
        return dict(state["result"])

    monkeypatch.setattr(ss, "extract_product", _extract)
    return state


# ── refresh_source: cele trei cai ─────────────────────────────────────────────

def test_domeniu_validat_merge_pe_pagina_de_produs(spy_extract):
    res = ss.refresh_source("emag.ro", EMAG_URL, "Produs test", None)

    assert res == {"price": 249.99, "in_stock": True, "method": "url"}
    assert spy_extract["calls"] == [EMAG_URL]


def test_domeniu_validat_cu_stoc_epuizat(spy_extract):
    spy_extract["result"] = _extracted(in_stock=False, price=99.0)

    res = ss.refresh_source("emag.ro", EMAG_URL, "Produs test", None)

    assert res["in_stock"] is False
    assert res["price"] == 99.0


def test_extractie_esuata_cade_pe_cautare(spy_extract, monkeypatch):
    spy_extract["error"] = ProductExtractionError("challenge", "cloudflare")
    monkeypatch.setitem(ss._SCRAPERS_BY_SOURCE, "emag.ro", _fake_search(price=77.5))

    res = ss.refresh_source("emag.ro", EMAG_URL, "Produs test", None)

    assert spy_extract["calls"] == [EMAG_URL]          # s-a incercat pagina...
    assert res == {"price": 77.5, "in_stock": None, "method": "search"}  # ...apoi cautarea


def test_pret_invalid_din_extractor_cade_pe_cautare(spy_extract, monkeypatch):
    """Extractorul a intors 0 (structura schimbata) -> nu scriem 0 in istoric."""
    spy_extract["result"] = _extracted(price=0)
    monkeypatch.setitem(ss._SCRAPERS_BY_SOURCE, "emag.ro", _fake_search(price=120.0))

    res = ss.refresh_source("emag.ro", EMAG_URL, "Produs test", None)

    assert res == {"price": 120.0, "in_stock": None, "method": "search"}


def test_domeniu_nevalidat_nu_atinge_extractorul(spy_extract, monkeypatch):
    monkeypatch.setitem(ss._SCRAPERS_BY_SOURCE, "sole.ro", _fake_search(price=45.0, url=SOLE_URL))

    res = ss.refresh_source("sole.ro", SOLE_URL, "Produs test", None)

    assert res == {"price": 45.0, "in_stock": None, "method": "search"}
    assert spy_extract["calls"] == []  # sole.ro nu e validat -> zero fetch pe pagina


def test_pcgarage_pe_cale_generica(spy_extract, monkeypatch):
    """LOT1 a INVERSAT pin-ul de aici, deliberat.

    Vechiul `test_pcgarage_ramane_pe_fetch_direct` documenta o LIPSA: pcgarage n-a
    fost validat la FAZA A (n-a avut URL-uri de produs la RETAIL-3a), deci refresh-ul
    ramanea pe parserul dedicat. Sonda LOT1 l-a validat pe pagini reale, iar
    scoparea nested a deblocat microdata — asa ca acum calea (a) a domeniilor
    validate intercepteaza prima, iar (b) devine fallback istoric.
    """
    assert "pcgarage.ro" in VALIDATED_DOMAINS
    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url",
                        lambda url, **kw: pytest.fail("calea dedicata nu trebuie atinsa"))

    res = ss.refresh_source("pcgarage.ro", PCG_URL, "Placa video", None)

    assert res == {"price": 249.99, "in_stock": True, "method": "url"}
    assert spy_extract["calls"] == [PCG_URL]


def test_pcgarage_fara_pret_intoarce_none(spy_extract, monkeypatch):
    # Ramura (b) ramane plasa: cand extractia esueaza, calea (a) cade mai jos.
    # `spy_extract` e OBLIGATORIU aici de la LOT1 — fara el, pcgarage fiind acum
    # validat, calea (a) ar chema extractorul REAL si testul ar iesi pe retea,
    # contrar contractului din docstring-ul fisierului.
    spy_extract["error"] = ProductExtractionError("fetch_failed", "pagina indisponibila")
    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url", lambda url, **kw: None)

    assert ss.refresh_source("pcgarage.ro", PCG_URL, "Placa video", None) is None


def test_sursa_sau_url_lipsa_intoarce_none(spy_extract):
    assert ss.refresh_source(None, EMAG_URL, "x", None) is None
    assert ss.refresh_source("emag.ro", None, "x", None) is None
    assert spy_extract["calls"] == []


def test_wrapper_back_compat_intoarce_doar_pretul(spy_extract, monkeypatch):
    assert ss.refresh_price_from_source("emag.ro", EMAG_URL, "Produs test") == 249.99

    # LOT1: pcgarage trece acum prin calea generica, deci wrapper-ul intoarce
    # pretul extras. Inainte cadea pe parserul dedicat, stub-uit aici cu None.
    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url",
                        lambda url, **kw: pytest.fail("calea dedicata nu trebuie atinsa"))
    assert ss.refresh_price_from_source("pcgarage.ro", PCG_URL, "x") == 249.99


def test_validated_domains_santinela():
    """Continutul e decis de sonda live, nu de intuitie: orice adaugare trece prin
    FAZA A a unui task RETAIL si actualizeaza explicit acest test."""
    assert VALIDATED_DOMAINS == {
        "altex.ro", "emag.ro",                        # RETAIL-3a
        "cel.ro", "vexio.ro", "mediagalaxy.ro",       # RETAIL-5c
        "answear.ro", "fashiondays.ro",               # FASHION-1b
        "epantofi.ro", "modivo.ro",                   # FASHION-1b
        "bstn.com", "en.afew-store.com",              # FASHION-2
        "prm.com", "sneakersnstuff.com",              # FASHION-2b
        "aboutyou.ro", "trendyol.com",                # FASHION-4
        "endclothing.com", "zalando.ro",              # ACCESS-2
        "43einhalb.com",                              # ACCESS-2
        "flanco.ro", "evomag.ro",                     # CONTENT-2
        "footshop.ro", "asos.com",                    # DISCOVERY-2
        "asphaltgold.com", "footdistrict.com",        # SHOP-1a
        "overkillshop.com", "nakedcph.com",           # SHOP-1a
        "caliroots.com", "patta.nl", "slamjam.com",   # SHOP-1a
        "redgoblin.ro", "ada-shoes.ro",               # SHOP-1a
        "rocashoes.ro", "shopium.ro", "sosukicks.ro", # SHOP-1a
        "itgalaxy.ro", "carrefour.ro", "flip.ro",     # LOT1
        "usedproducts.ro", "senetic.ro", "pcgarage.ro",  # LOT1
        "computeruniverse.net", "jb-spielwaren.de",   # LOT2
        "caseking.de", "bergfreunde.eu",              # LOT2b
        "alternate.de", "foto-erhardt.com",           # LOT2b
        "buzzsneakers.ro", "officeshoes.ro",          # LOT3
        "otter.ro", "spartoo.ro",                     # LOT3b
        "boozt.com", "booztlet.com",                  # LOT3b
        "marionnaud.ro", "notino.ro",                 # LOT4
        "parfumdreams.de", "douglas.ro",              # LOT4 / LOT4b
        "orange.ro", "makeup.ro",                     # BR-1 (G4/G4b)
        "hhv.de", "sephora.ro",                       # BR-1 (G4/G4b)
        "noriel.ro", "regatuljocurilor.ro",           # LOT5
        "jucarii-vorbarete.ro",                       # LOT5
        "nichiduta.ro", "brickdepot.ro",              # LOT5b
        "f64.ro",                                     # VTX-2
        "elefant.ro",                                 # ELF-2
        "sivasdescalzo.com",                          # G1-2
        "tezyo.ro",                                   # G1-2
        "powerup.ro",                                 # G2A-2
        "cyberport.at",                               # G2B-2
        "sportvision.ro",                             # G2C-2
        "sizeer.ro",                                  # G2C-2
        "intersport.ro",                              # G2F-2
        "toolnation.nl",                              # G2F-2
        "direct-running.com",                         # G2F-2
        "zooplus.ro",                                 # G2F-4
        "hornbach.ro",                                # G2F-6
        "bonami.ro",                                  # G2F-6
        "action.com",                                 # G2F-6
        "ro.vivre.eu",                                # G2F-6
        "biciclop.eu",                                # G2F-8
        "cellini.ro",                                 # G2F-8
    }


# ── alert_checker: persistarea stocului ───────────────────────────────────────

def _seed_source(in_stock=None, price=100.0):
    """Product + ProductSource in baza de test; intoarce id-ul sursei."""
    db = SessionLocal()
    try:
        p = Product(name="RETAIL3 produs", current_price=price, currency="RON")
        db.add(p)
        db.flush()
        ps = ProductSource(product_id=p.id, source="emag.ro", source_url=EMAG_URL,
                           current_price=price, currency="RON", in_stock=in_stock)
        db.add(ps)
        db.commit()
        return ps.id
    finally:
        db.close()


def _run_refresh():
    work = SessionLocal()
    try:
        _refresh_all_scrapeable_products(work)
    finally:
        work.close()


def _source_row(source_id):
    db = SessionLocal()
    try:
        return db.query(ProductSource).filter(ProductSource.id == source_id).one()
    finally:
        db.close()


def test_alert_checker_persista_in_stock(monkeypatch):
    catalog_health_watchdog._reset_state()
    source_id = _seed_source(in_stock=None)
    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 100.0, "in_stock": True, "method": "url"})

    _run_refresh()

    assert _source_row(source_id).in_stock is True


def test_alert_checker_in_stock_none_nu_suprascrie_starea_cunoscuta(monkeypatch):
    """NULL inseamna «necunoscut», nu «a iesit din stoc» — calea "search" nu are
    de unde sti stocul si nu trebuie sa stearga ce stim deja."""
    catalog_health_watchdog._reset_state()
    source_id = _seed_source(in_stock=False)
    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 100.0, "in_stock": None, "method": "search"})

    _run_refresh()

    assert _source_row(source_id).in_stock is False


def test_alert_checker_rezultat_none_e_esec_la_watchdog(monkeypatch):
    catalog_health_watchdog._reset_state()
    _seed_source(in_stock=True)
    monkeypatch.setattr("app.utils.alert_checker.refresh_source", lambda **kw: None)

    seen = []
    monkeypatch.setattr(catalog_health_watchdog, "note_refresh",
                        lambda source, success: seen.append((source, success)))

    _run_refresh()

    assert seen == [("emag.ro", False)]


# ── refresh manual (HTTP) ─────────────────────────────────────────────────────

def test_refresh_product_price_persista_in_stock(auth_client, monkeypatch):
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda product_id: None)
    monkeypatch.setattr("app.routers.products._backfill_ean", lambda *a, **kw: None)

    created = auth_client.post("/api/products/", json={
        "name": "RETAIL3 refresh manual", "current_price": 100.0, "currency": "RON",
        "source": "emag.ro", "source_url": EMAG_URL,
    })
    assert created.status_code == 200, created.text
    product_id = created.json()["id"]

    monkeypatch.setattr("app.routers.products.refresh_source",
                        lambda **kw: {"price": 79.99, "in_stock": True, "method": "url"})

    r = auth_client.post(f"/api/products/{product_id}/refresh-price")
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["new_price"] == 79.99
    assert r.json()["results"][0]["changed"] is True

    db = SessionLocal()
    try:
        ps = db.query(ProductSource).filter(ProductSource.product_id == product_id).one()
        assert ps.in_stock is True
        assert ps.current_price == 79.99
    finally:
        db.close()
