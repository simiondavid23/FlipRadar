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


def test_pcgarage_ramane_pe_fetch_direct(spy_extract, monkeypatch):
    # Pin explicit: pcgarage n-a fost validat la FAZA A (fara URL-uri de produs),
    # deci ramane pe parserul dedicat, nu pe extractorul generic.
    assert "pcgarage.ro" not in VALIDATED_DOMAINS
    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url", lambda url, **kw: 1499.0)

    res = ss.refresh_source("pcgarage.ro", PCG_URL, "Placa video", None)

    assert res == {"price": 1499.0, "in_stock": None, "method": "pcgarage"}
    assert spy_extract["calls"] == []


def test_pcgarage_fara_pret_intoarce_none(monkeypatch):
    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url", lambda url, **kw: None)

    assert ss.refresh_source("pcgarage.ro", PCG_URL, "Placa video", None) is None


def test_sursa_sau_url_lipsa_intoarce_none(spy_extract):
    assert ss.refresh_source(None, EMAG_URL, "x", None) is None
    assert ss.refresh_source("emag.ro", None, "x", None) is None
    assert spy_extract["calls"] == []


def test_wrapper_back_compat_intoarce_doar_pretul(spy_extract, monkeypatch):
    assert ss.refresh_price_from_source("emag.ro", EMAG_URL, "Produs test") == 249.99

    monkeypatch.setattr(ss, "fetch_pcgarage_price_from_url", lambda url, **kw: None)
    assert ss.refresh_price_from_source("pcgarage.ro", PCG_URL, "x") is None


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
