"""MAG-1 — stergerea unui produs, provenienta (`origin`) si lista imbogatita.

DE CE EXISTA. Pana la MAG-1 nu exista NICIUN test care sa stearga un produs prin API
(sonda MAG-0, §5.5), iar bug-ul raportat de David era exact acolo: un produs promovat
dintr-un deal nu putea fi sters. Cauza — `deals.promoted_product_id` e cheie straina
spre `products` cu `ON DELETE NO ACTION`, iar `PRAGMA foreign_keys=ON` (database.py)
o aplica; `Product` nu avea nicio relatie catre `Deal`, deci SQLAlchemy emitea un
DELETE simplu si SQLite il refuza cu `FOREIGN KEY constraint failed`.

Fixul e o relatie ORM FARA cascada de stergere (anuleaza FK-ul pe copii inainte de
DELETE). De aici si garda de la fiecare test: daca `PRAGMA foreign_keys` ar fi 0,
testele ar trece si fara fix, deci n-ar dovedi nimic.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.product import Product
from app.models.resale_reference import ResaleReference


@pytest.fixture(autouse=True)
def _fara_retea(monkeypatch):
    """Promovarea trece prin extractorul live (`creeaza_din_link`); il alimentam cu un
    rezultat sintetic, ca testele sa masoare stergerea, nu disponibilitatea magazinului.
    Acelasi tipar ca fixture-ul omonim din test_authorization.py."""
    monkeypatch.setattr("app.routers.products.extract_product", lambda url, **kw: {
        "name": "MAG1 produs", "price": 100.0, "currency": "EUR", "in_stock": True,
        "is_aggregate": False, "variants": None, "image_url": None,
        "canonical_url": "https://asphaltgold.com/products/x",
        "domain": "asphaltgold.com", "method": "shopify", "override_applied": False,
    })
    monkeypatch.setattr("app.routers.products._backfill_ean", lambda *a, **k: None)
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda *a, **k: None)


def _pragma_fk_activ() -> int:
    """Valoarea PRAGMA foreign_keys pe o conexiune din ACELASI engine ca aplicatia.
    Fara ea, testele de mai jos ar fi fals-verzi: un DELETE nu poate incalca o
    constrangere care nu se aplica."""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        return int(db.execute(text("PRAGMA foreign_keys")).scalar())
    finally:
        db.close()


def _client_nou():
    """Client cu jar propriu de cookie-uri, user inregistrat + logat, cu
    `can_use_scraping` pornit (promovarea si /from-url sunt in spatele acelui flag)."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.user import User

    c = TestClient(app)
    uniq = uuid.uuid4().hex[:12]
    payload = {
        "email": f"mag1_{uniq}@example.com",
        "username": f"mag1_{uniq}",
        "password": "testpass123",
        "full_name": "MAG1 User",
        "security_question": "Care e culoarea preferata?",
        "security_answer": "albastru",
    }
    r = c.post("/api/auth/register", json=payload)
    assert r.status_code == 200, f"register a esuat: {r.status_code} {r.text}"
    r = c.post("/api/auth/login",
               json={"email": payload["email"], "password": payload["password"]})
    assert r.status_code == 200, f"login a esuat: {r.status_code} {r.text}"

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == payload["email"]).one()
        u.can_use_scraping = True
        db.commit()
        return c, u.id
    finally:
        db.close()


def _origin(product_id: int):
    """Provenienta CITITA DIN BAZA. Raspunsul lui /promote nu are `response_model`, deci
    cheia "product" e serializata brut din `__dict__`-ul obiectului ORM si nu poarta
    garantat coloanele neaccesate — baza e sursa de adevar, nu acel camp netipat."""
    db = SessionLocal()
    try:
        return db.query(Product).filter(Product.id == product_id).one().origin
    finally:
        db.close()


def _deal_nou(**kw) -> int:
    db = SessionLocal()
    try:
        d = Deal(shop_domain="asphaltgold.com", external_id=uuid.uuid4().hex[:16],
                 title="MAG1 deal", url="https://asphaltgold.com/products/x",
                 currency="EUR", price=100.0, discount_pct=50.0,
                 reason="compare_at", **kw)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


# ── T1 — produsul promovat dintr-un deal se sterge, deal-ul supravietuieste ──────
def test_stergerea_produsului_promovat_reuseste_si_coboara_dealul_in_vazut():
    assert _pragma_fk_activ() == 1, (
        "PRAGMA foreign_keys e 0 pe engine-ul de test: fara el, testul ar trece si "
        "fara fix, deci n-ar dovedi nimic (vezi raport MAG-0 §5.2c)")

    client, _uid = _client_nou()
    deal_id = _deal_nou()

    r = client.post(f"/api/deals/{deal_id}/promote")
    assert r.status_code == 200, r.text
    product_id = r.json()["product_id"]

    db = SessionLocal()
    try:
        d = db.query(Deal).filter(Deal.id == deal_id).one()
        assert d.state == "promovat"
        assert d.promoted_product_id == product_id, "premisa testului: FK-ul e pus"
    finally:
        db.close()

    r = client.delete(f"/api/products/{product_id}")
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.id == product_id).first() is None, \
            "produsul trebuia sters"
        d = db.query(Deal).filter(Deal.id == deal_id).one()
        assert d.promoted_product_id is None, "legatura trebuia anulata, nu lasata"
        assert d.state == "vazut", "deal-ul coboara din `promovat`, dar ramane in feed"
    finally:
        db.close()


# ── T2 — referintele de revanzare mor odata cu produsul ─────────────────────────
def test_stergerea_produsului_duce_si_referintele_de_revanzare():
    assert _pragma_fk_activ() == 1, (
        "PRAGMA foreign_keys e 0 pe engine-ul de test: fara el, testul ar trece si "
        "fara fix, deci n-ar dovedi nimic (vezi raport MAG-0 §5.2c)")

    client, uid = _client_nou()
    r = client.post("/api/products/", json={"name": "MAG1 cu referinta",
                                            "current_price": 150})
    assert r.status_code == 200, r.text
    product_id = r.json()["id"]

    db = SessionLocal()
    try:
        db.add(ResaleReference(product_id=product_id, platform="stockx",
                               variant="", ref_price=210.0))
        db.commit()
        assert db.query(ResaleReference).filter(
            ResaleReference.product_id == product_id).count() == 1
    finally:
        db.close()

    r = client.delete(f"/api/products/{product_id}")
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.id == product_id).first() is None
        assert db.query(ResaleReference).filter(
            ResaleReference.product_id == product_id).count() == 0, \
            "referinta de revanzare a ramas orfana"
    finally:
        db.close()


# ── T3 — control de ownership: produsul altui user nu se sterge ─────────────────
def test_stergerea_produsului_altui_user_da_404():
    client_a, _ = _client_nou()
    client_b, _ = _client_nou()

    r = client_a.post("/api/products/", json={"name": "Produsul lui A",
                                              "current_price": 10})
    assert r.status_code == 200, r.text
    product_id = r.json()["id"]

    r = client_b.delete(f"/api/products/{product_id}")
    assert r.status_code == 404, r.text

    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.id == product_id).first() is not None, \
            "produsul lui A a fost sters de B"
    finally:
        db.close()


# ── T4 — `origin` la creare: implicit, explicit, invalid ────────────────────────
def test_origin_la_creare_implicit_explicit_si_invalid():
    client, _ = _client_nou()

    r = client.post("/api/products/", json={"name": "Fara origin"})
    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "manual", "absenta inseamna `manual`"

    r = client.post("/api/products/", json={"name": "Cu origin scan",
                                            "origin": "scan"})
    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "scan"

    r = client.post("/api/products/", json={"name": "Origin inventat",
                                            "origin": "xyz"})
    assert r.status_code == 422, r.text


# ── T5 — adaugarea prin link scrie `link` ──────────────────────────────────────
def test_origin_din_link_e_link():
    client, _ = _client_nou()

    r = client.post("/api/products/from-url",
                    json={"url": "https://asphaltgold.com/products/x"})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["origin"] == "link"


# ── T6 — promovarea scrie `deal`, iar dedup-ul NU rescrie provenienta ──────────
def test_origin_din_promovare_e_deal_si_dedupul_nu_il_rescrie():
    client, _ = _client_nou()

    deal_id = _deal_nou()
    r = client.post(f"/api/deals/{deal_id}/promote")
    assert r.status_code == 200, r.text
    product_id = r.json()["product_id"]
    assert _origin(product_id) == "deal"

    # Al doilea deal pe ACELASI URL, promovat de acelasi user -> create_product cade pe
    # ramura de dedup (acelasi nume + aceeasi sursa) si intoarce produsul existent.
    al_doilea = _deal_nou()
    r = client.post(f"/api/deals/{al_doilea}/promote")
    assert r.status_code == 200, r.text
    assert r.json()["product_id"] == product_id, "premisa testului: s-a facut dedup"
    assert _origin(product_id) == "deal"

    # Simetric, pe direcţia care conteaza cu adevarat: un produs intrat prin LINK si
    # reintalnit intr-un deal ramane `link` — provenienta descrie prima intrare.
    client2, _ = _client_nou()
    r = client2.post("/api/products/from-url",
                     json={"url": "https://asphaltgold.com/products/x"})
    assert r.status_code == 200, r.text
    pid2 = r.json()["product"]["id"]

    al_treilea = _deal_nou()
    r = client2.post(f"/api/deals/{al_treilea}/promote")
    assert r.status_code == 200, r.text
    assert r.json()["product_id"] == pid2, "premisa testului: s-a facut dedup"
    assert _origin(pid2) == "link", (
        "promovarea a rescris provenienta unui produs adaugat prin link")


# ── T7 — filtrul `origin` pe listare ───────────────────────────────────────────
def test_filtrul_origin_partitioneaza_lista():
    client, _ = _client_nou()

    client.post("/api/products/", json={"name": "Manual A"})
    client.post("/api/products/", json={"name": "Scan B", "origin": "scan"})
    deal_id = _deal_nou()
    assert client.post(f"/api/deals/{deal_id}/promote").status_code == 200

    toate = client.get("/api/products/").json()
    assert len(toate) == 3

    doar_deal = client.get("/api/products/?origin=deal").json()
    assert [p["name"] for p in doar_deal] == ["MAG1 produs"]

    doar_scan = client.get("/api/products/?origin=scan").json()
    assert [p["name"] for p in doar_scan] == ["Scan B"]

    assert client.get("/api/products/?origin=inventat").status_code == 422


# ── T8 — lista poarta starea de urmarire (fuziunea paginilor) ──────────────────
def test_lista_de_produse_poarta_monitorizarea_pragul_si_istoricul():
    from app.models.price_history import PriceHistory

    client, _ = _client_nou()
    r = client.post("/api/products/", json={"name": "Monitorizat", "current_price": 100})
    assert r.status_code == 200, r.text
    product_id = r.json()["id"]

    # 10 puncte de istoric: raspunsul trebuie sa intoarca DOAR ultimele 7, cronologic.
    # (create_product a scris deja unul, deci in total 11 — taierea ramane la 7.)
    db = SessionLocal()
    try:
        for pret in range(1, 11):
            db.add(PriceHistory(product_id=product_id, price=float(pret),
                                currency="EUR", source="test"))
        db.commit()
    finally:
        db.close()

    assert client.patch(f"/api/tracked-products/{product_id}/monitoring",
                        json={"active": True, "alert_threshold": 80}).status_code == 200

    rand = next(p for p in client.get("/api/products/").json() if p["id"] == product_id)
    assert rand["monitoring_active"] is True
    assert rand["alert_threshold"] == 80

    istoric = rand["price_history"]
    assert len(istoric) == 7, "sparkline-ul e taiat la 7 puncte"
    assert [p["price"] for p in istoric] == [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], \
        "ordinea e cronologica, iar taierea pastreaza cele mai RECENTE puncte"

    # Acelasi contract ca pagina veche: cele doua endpointuri nu pot devia.
    din_tracked = next(p for p in client.get("/api/tracked-products/").json()
                       if p["id"] == product_id)
    assert din_tracked["alert_threshold"] == rand["alert_threshold"]
    assert din_tracked["price_history"] == istoric


# ── T9 — filtrul `monitored` partitioneaza lista ───────────────────────────────
def test_filtrul_monitored_partitioneaza_lista():
    client, _ = _client_nou()

    r = client.post("/api/products/", json={"name": "Cu monitorizare"})
    monitorizat = r.json()["id"]
    r = client.post("/api/products/", json={"name": "Fara monitorizare"})
    nemonitorizat = r.json()["id"]

    assert client.patch(f"/api/tracked-products/{monitorizat}/monitoring",
                        json={"active": True}).status_code == 200

    da = client.get("/api/products/?monitored=true").json()
    assert [p["id"] for p in da] == [monitorizat]

    nu = client.get("/api/products/?monitored=false").json()
    assert [p["id"] for p in nu] == [nemonitorizat]

    # Fara parametru, lista e reuniunea celor doua — filtrul nu are efect implicit.
    assert {p["id"] for p in client.get("/api/products/").json()} == {
        monitorizat, nemonitorizat}
