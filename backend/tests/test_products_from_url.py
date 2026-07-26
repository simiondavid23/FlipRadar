"""RETAIL-2 — POST /api/products/from-url (adaugare produs prin link).

Zero retea: extractorul e inlocuit cu un fals configurabil per test, iar cele
doua functii de scraping apelate din BackgroundTasks (backfill EAN + cross-shop)
sunt neutralizate — TestClient EXECUTA background task-urile sincron dupa
raspuns, deci fara stub-uri suita ar iesi pe internet.

Acopera: salvarea delegata catre create_product (produs nou / re-paste / pret
schimbat), alegerea source_url-ului fata de canonical, maparea erorilor de
extractie pe status-uri HTTP, gardul de feature, izolarea per user, stocul
tri-state pe sursa si migratia portabila a celor doua coloane noi.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.user import User
from app.services.product_page_extractor import ProductExtractionError

URL = "https://www.emag.ro/casti-sony-wh1000/pd/ABC123/"


def _res(**over):
    """Rezultat de extractor — exact cheile garantate de parse_product_html."""
    base = {
        "name": "Casti Sony WH-1000XM4",
        "price": 899.0,
        "currency": "RON",
        "in_stock": True,
        "is_aggregate": False,
        "image_url": "https://cdn.emag.ro/casti.jpg",
        "canonical_url": URL,
        "domain": "emag.ro",
        "method": "jsonld",
        "override_applied": False,
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def fake_extract(monkeypatch):
    """Controleaza ce intoarce (sau arunca) extractorul + taie reteaua din
    background tasks. Testele muteaza `state["result"]` / `state["error"]`."""
    import app.routers.products as products

    state = {"result": _res(), "error": None, "urls": []}

    def _extract(url, max_retries=3):
        state["urls"].append(url)
        if state["error"] is not None:
            raise state["error"]
        return dict(state["result"])

    monkeypatch.setattr(products, "extract_product", _extract)
    monkeypatch.setattr(products, "fetch_ean_from_url", lambda *a, **k: None)
    monkeypatch.setattr(products, "find_cross_shop_matches",
                        lambda *a, **k: {"ean_matches": [], "name_candidates": []})
    return state


def _db_rows():
    """(produse, surse, istoric) citite direct din baza de test."""
    db = SessionLocal()
    try:
        return (db.query(Product).all(),
                db.query(ProductSource).all(),
                db.query(PriceHistory).order_by(PriceHistory.id).all())
    finally:
        db.close()


def _new_user_client():
    """Client NOU (cookie jar propriu) cu user inregistrat + logat — `auth_client`
    refoloseste acelasi TestClient, deci un al doilea login i-ar suprascrie sesiunea."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    uniq = uuid.uuid4().hex[:12]
    payload = {
        "email": f"retail2_{uniq}@example.com",
        "username": f"retail2_{uniq}",
        "password": "testpass123",
        "full_name": "RETAIL2 User",
        "security_question": "Care e culoarea preferata?",
        "security_answer": "albastru",
    }
    assert c.post("/api/auth/register", json=payload).status_code == 200
    assert c.post("/api/auth/login", json={
        "email": payload["email"], "password": payload["password"]}).status_code == 200
    return c


# ── salvare ───────────────────────────────────────────────────────────────────

def test_produs_nou_din_link(auth_client, fake_extract):
    r = auth_client.post("/api/products/from-url", json={"url": URL})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["is_new"] is True
    assert body["previous_price"] is None
    assert body["price_changed"] is False
    # emag.ro a intrat in VALIDATED_DOMAINS la RETAIL-3a (sonda FAZA A: 5/5 pagini
    # extrase corect prin JSON-LD). Ramura False e pinuita separat, mai jos.
    assert body["domain_validated"] is True
    assert body["extraction"] == {
        "method": "jsonld", "override_applied": False, "in_stock": True, "is_aggregate": False,
    }
    assert body["product"]["name"] == "Casti Sony WH-1000XM4"
    assert body["product"]["source"] == "emag.ro"
    assert body["product"]["current_price"] == 899.0
    assert body["product"]["currency"] == "RON"
    assert len(body["price_history"]) == 1

    products, sources, history = _db_rows()
    assert len(products) == 1 and len(sources) == 1 and len(history) == 1
    assert sources[0].source == "emag.ro"
    assert sources[0].in_stock is True
    assert sources[0].current_price == 899.0
    assert history[0].price == 899.0


def test_domeniu_nevalidat_are_domain_validated_false(auth_client, fake_extract):
    """Flag-ul chiar reflecta apartenenta la VALIDATED_DOMAINS, nu e mereu True:
    pe un domeniu care n-a trecut prin nicio sonda, UI-ul trebuie sa stie ca
    extractia e neverificata."""
    fake_extract["result"] = _res(domain="magazin-fictiv.ro",
                                  canonical_url="https://magazin-fictiv.ro/p/1")

    body = auth_client.post("/api/products/from-url",
                            json={"url": "https://magazin-fictiv.ro/p/1"}).json()

    assert body["domain_validated"] is False
    assert body["product"]["source"] == "magazin-fictiv.ro"


def test_repaste_acelasi_url_pret_neschimbat(auth_client, fake_extract):
    assert auth_client.post("/api/products/from-url", json={"url": URL}).status_code == 200
    r = auth_client.post("/api/products/from-url", json={"url": URL})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["is_new"] is False
    assert body["price_changed"] is False

    products, sources, history = _db_rows()
    assert len(products) == 1 and len(sources) == 1
    # Comportament documentat si acceptat: attach_source_to_product scrie PriceHistory
    # necondiționat cand primeste pret -> re-lipirea adauga un punct plat in istoric.
    assert len(history) == 2
    assert [h.price for h in history] == [899.0, 899.0]


def test_repaste_cu_pret_schimbat(auth_client, fake_extract):
    assert auth_client.post("/api/products/from-url", json={"url": URL}).status_code == 200
    fake_extract["result"] = _res(price=749.5)

    r = auth_client.post("/api/products/from-url", json={"url": URL})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["is_new"] is False
    assert body["price_changed"] is True
    assert body["previous_price"] == 899.0
    assert body["product"]["current_price"] == 749.5

    products, sources, history = _db_rows()
    assert len(products) == 1
    assert sources[0].current_price == 749.5
    assert history[-1].price == 749.5


def test_in_stock_none_ramane_null_pe_sursa(auth_client, fake_extract):
    fake_extract["result"] = _res(in_stock=None)

    body = auth_client.post("/api/products/from-url", json={"url": URL}).json()

    assert body["extraction"]["in_stock"] is None
    assert body["product"]["sources"][0]["in_stock"] is None
    _, sources, _ = _db_rows()
    assert sources[0].in_stock is None


# ── alegerea source_url ───────────────────────────────────────────────────────

def test_canonical_pe_acelasi_domeniu_e_preferat(auth_client, fake_extract):
    canonical = "https://www.emag.ro/casti-sony-wh1000/pd/ABC123/"
    fake_extract["result"] = _res(canonical_url=canonical)

    auth_client.post("/api/products/from-url", json={"url": URL + "?utm_source=x#tab"})

    _, sources, _ = _db_rows()
    assert sources[0].source_url == canonical


def test_canonical_pe_alt_domeniu_e_ignorat(auth_client, fake_extract):
    fake_extract["result"] = _res(canonical_url="https://alt-magazin.example.com/produs")

    auth_client.post("/api/products/from-url", json={"url": URL + "#reviews"})

    _, sources, _ = _db_rows()
    assert sources[0].source_url == URL  # URL-ul de intrare, fara fragment


# ── maparea erorilor ──────────────────────────────────────────────────────────

def test_domain_not_allowed_400_cu_hostname(auth_client, fake_extract):
    fake_extract["error"] = ProductExtractionError("domain_not_allowed", "blocat")

    r = auth_client.post("/api/products/from-url",
                         json={"url": "https://magazin-necunoscut.ro/produs/1"})

    assert r.status_code == 400
    assert "magazin-necunoscut.ro" in r.json()["detail"]
    assert _db_rows()[0] == []


def test_no_product_data_422(auth_client, fake_extract):
    fake_extract["error"] = ProductExtractionError("no_product_data", "pagina goala")

    r = auth_client.post("/api/products/from-url", json={"url": URL})

    assert r.status_code == 422
    assert "extrage datele produsului" in r.json()["detail"]


def test_invalid_price_422(auth_client, fake_extract):
    fake_extract["error"] = ProductExtractionError("invalid_price", "pret 0")

    assert auth_client.post("/api/products/from-url", json={"url": URL}).status_code == 422


def test_fetch_failed_502(auth_client, fake_extract):
    fake_extract["error"] = ProductExtractionError("fetch_failed", "status 502")

    r = auth_client.post("/api/products/from-url", json={"url": URL})

    assert r.status_code == 502
    assert "Magazinul nu a răspuns" in r.json()["detail"]


def test_challenge_502(auth_client, fake_extract):
    fake_extract["error"] = ProductExtractionError("challenge", "cloudflare")

    assert auth_client.post("/api/products/from-url", json={"url": URL}).status_code == 502


# ── autorizare & izolare ──────────────────────────────────────────────────────

def test_fara_can_use_scraping_e_refuzat(auth_client, fake_extract):
    db = SessionLocal()
    try:
        user = db.query(User).first()  # clean_db goleste baza -> exista un singur user
        user.can_use_scraping = False
        db.commit()
    finally:
        db.close()

    r = auth_client.post("/api/products/from-url", json={"url": URL})

    assert r.status_code == 403
    assert _db_rows()[0] == []  # nimic salvat


def test_acelasi_link_la_doi_useri_da_produse_separate(auth_client, fake_extract):
    client_b = _new_user_client()

    body_a = auth_client.post("/api/products/from-url", json={"url": URL}).json()
    body_b = client_b.post("/api/products/from-url", json={"url": URL}).json()

    assert body_a["is_new"] is True
    assert body_b["is_new"] is True                      # nu vede produsul lui A
    assert body_a["product"]["id"] != body_b["product"]["id"]

    products, sources, _ = _db_rows()
    assert len(products) == 2 and len(sources) == 2
    assert len({p.user_id for p in products}) == 2

    # Fiecare user vede doar produsul lui.
    assert len(auth_client.get("/api/products/").json()) == 1
    assert len(client_b.get("/api/products/").json()) == 1


# ── migratia portabila ────────────────────────────────────────────────────────

def test_migratie_portabila_adauga_coloanele_si_e_idempotenta(tmp_path):
    """Baza noua, tabele fara coloanele noi -> _portable_migrations le adauga;
    a doua rulare nu mai face nimic (garda de introspectie + schema_migrations)."""
    from sqlalchemy import create_engine, inspect, text

    from app.utils.db_migrate import _column_exists, _portable_migrations

    engine = create_engine(f"sqlite:///{(tmp_path / 'retail2.db').as_posix()}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE product_sources (id INTEGER PRIMARY KEY, source TEXT)"))
        conn.execute(text("CREATE TABLE alerts (id INTEGER PRIMARY KEY, target_price FLOAT)"))
        conn.execute(text("CREATE TABLE schema_migrations ("
                          "migration_name TEXT UNIQUE NOT NULL, applied_at TIMESTAMP)"))
        conn.commit()
        _portable_migrations(conn, inspect(engine))

    inspector = inspect(engine)
    assert _column_exists(inspector, "product_sources", "in_stock")
    assert _column_exists(inspector, "alerts", "drop_pct")

    with engine.connect() as conn:
        _portable_migrations(conn, inspect(engine))  # no-op, fara exceptii
        applied = conn.execute(text(
            "SELECT count(*) FROM schema_migrations WHERE migration_name IN "
            "('add_product_sources_in_stock', 'add_alerts_drop_pct')")).scalar()
    assert applied == 2
    engine.dispose()
