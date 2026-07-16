"""CAT-3a — Produse Urmarite pe modelul unificat TrackedProduct.

Acopera fixul IDOR din PATCH /monitoring (endpoint-ul vechi crea randul fara sa
verifice proprietarul produsului) si legarea pragului de alerta de modelul Alert
(inainte, pragul era acceptat de API dar niciodata persistat: setattr pe un
atribut nemapat). Produsele se creeaza prin API, cu _cross_shop_match neutralizat
(altfel create_product ar face scrape live ca BackgroundTask) — acelasi pattern
ca in test_alerts_rearm.
"""
import uuid

import pytest


@pytest.fixture(autouse=True)
def _no_cross_shop(monkeypatch):
    # create_product programeaza _cross_shop_match (scrape live) ca BackgroundTask,
    # rulat sincron de TestClient dupa raspuns. Il neutralizam — testele nu ating reteaua.
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda product_id: None)


def _new_user_client():
    """Client NOU (cookie jar propriu) cu user inregistrat + logat. Necesar pentru
    testul IDOR: `auth_client` refolosesc acelasi TestClient, deci un al doilea
    login pe el ar suprascrie sesiunea primului user."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    uniq = uuid.uuid4().hex[:12]
    payload = {
        "email": f"cat3a_{uniq}@example.com",
        "username": f"cat3a_{uniq}",
        "password": "testpass123",
        "full_name": "CAT3a User",
        "security_question": "Care e culoarea preferata?",
        "security_answer": "albastru",
    }
    r = c.post("/api/auth/register", json=payload)
    assert r.status_code == 200, f"register a esuat: {r.status_code} {r.text}"
    r = c.post("/api/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert r.status_code == 200, f"login a esuat: {r.status_code} {r.text}"
    return c


def _mk_product(client, name="CAT3a produs", price=150):
    r = client.post("/api/products/", json={"name": name, "current_price": price})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _tracked_rows(product_id):
    """Randurile de tracking pentru un produs, citite direct din DB-ul de test."""
    from app.database import SessionLocal
    from app.models.tracked_product import TrackedProduct

    db = SessionLocal()
    try:
        return [
            {"user_id": t.user_id, "product_id": t.product_id,
             "monitoring_active": t.monitoring_active}
            for t in db.query(TrackedProduct).filter(
                TrackedProduct.product_id == product_id
            ).all()
        ]
    finally:
        db.close()


def _price_drop_alerts(product_id):
    """Alertele price_drop pe un produs, citite direct din DB-ul de test."""
    from app.database import SessionLocal
    from app.models.alert import Alert

    db = SessionLocal()
    try:
        return [
            {"id": a.id, "target_price": a.target_price, "is_active": a.is_active,
             "is_triggered": a.is_triggered, "currency": a.currency}
            for a in db.query(Alert).filter(
                Alert.product_id == product_id,
                Alert.alert_type == "price_drop",
            ).order_by(Alert.id).all()
        ]
    finally:
        db.close()


def _item_in_feed(client, product_id):
    r = client.get("/api/tracked-products/")
    assert r.status_code == 200, r.text
    for item in r.json():
        if item["id"] == product_id:
            return item
    return None


# ── t1 — IDOR: produsul altui user nu poate fi monitorizat ───────────────────────
def test_patch_monitoring_pe_produsul_altui_user_da_404_si_nu_creeaza_rand(auth_client):
    product_id = _mk_product(auth_client, name="Produsul lui A")

    atacator = _new_user_client()
    r = atacator.patch(
        f"/api/tracked-products/{product_id}/monitoring",
        json={"active": True, "alert_threshold": 50},
    )
    assert r.status_code == 404, r.text
    assert _tracked_rows(product_id) == []


# ── t2 — pragul ajunge in modelul Alert si se vede in feed ───────────────────────
def test_patch_activ_cu_prag_creeaza_alerta_price_drop(auth_client):
    product_id = _mk_product(auth_client)

    r = auth_client.patch(
        f"/api/tracked-products/{product_id}/monitoring",
        json={"active": True, "alert_threshold": 90},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok", "monitoring_active": True}

    alerts = _price_drop_alerts(product_id)
    assert len(alerts) == 1
    assert alerts[0]["target_price"] == 90
    assert alerts[0]["is_active"] is True
    assert alerts[0]["is_triggered"] is False

    item = _item_in_feed(auth_client, product_id)
    assert item is not None
    assert item["alert_threshold"] == 90
    assert item["monitoring_active"] is True


# ── t3 — al doilea prag actualizeaza aceeasi alerta, nu creeaza a doua ───────────
def test_al_doilea_prag_actualizeaza_aceeasi_alerta(auth_client):
    product_id = _mk_product(auth_client)

    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": True, "alert_threshold": 90})
    r = auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                          json={"active": True, "alert_threshold": 80})
    assert r.status_code == 200, r.text

    alerts = _price_drop_alerts(product_id)
    assert len(alerts) == 1
    assert alerts[0]["target_price"] == 80
    assert _item_in_feed(auth_client, product_id)["alert_threshold"] == 80


# ── t4 — prag invalid ────────────────────────────────────────────────────────────
def test_prag_zero_da_400(auth_client):
    product_id = _mk_product(auth_client)

    r = auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                          json={"active": True, "alert_threshold": 0})
    assert r.status_code == 400, r.text
    assert _price_drop_alerts(product_id) == []


# ── t5 — DELETE scoate din tracking, alerta ramane ───────────────────────────────
def test_delete_scoate_din_tracking_dar_pastreaza_alerta(auth_client):
    product_id = _mk_product(auth_client)
    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": True, "alert_threshold": 90})

    r = auth_client.delete(f"/api/tracked-products/{product_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}

    assert _tracked_rows(product_id) == []
    assert _item_in_feed(auth_client, product_id) is None
    assert len(_price_drop_alerts(product_id)) == 1


# ── t8 (rescris de C-18) — toggle OFF dezactiveaza alerta price_drop ─────────────
def test_patch_inactiv_dezactiveaza_alerta_price_drop(auth_client):
    product_id = _mk_product(auth_client)
    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": True, "alert_threshold": 90})

    r = auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                          json={"active": False})
    assert r.status_code == 200, r.text

    item = _item_in_feed(auth_client, product_id)
    assert item is not None
    assert item["monitoring_active"] is False
    # GET citeste pragul doar din alerte active -> dupa OFF nu mai exista prag.
    assert item["alert_threshold"] is None

    alerts = _price_drop_alerts(product_id)
    assert len(alerts) == 1
    assert alerts[0]["is_active"] is False


def test_patch_inactiv_nu_atinge_price_rise(auth_client):
    """C-18 stinge DOAR price_drop; o alerta price_rise pe acelasi produs ramane activa."""
    from app.database import SessionLocal
    from app.models.alert import Alert

    product_id = _mk_product(auth_client)
    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": True, "alert_threshold": 90})
    owner_id = _tracked_rows(product_id)[0]["user_id"]

    db = SessionLocal()
    try:
        db.add(Alert(user_id=owner_id, product_id=product_id, target_price=999,
                     currency="EUR", alert_type="price_rise",
                     is_active=True, is_triggered=False))
        db.commit()
    finally:
        db.close()

    r = auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                          json={"active": False})
    assert r.status_code == 200, r.text

    assert _price_drop_alerts(product_id)[0]["is_active"] is False

    db = SessionLocal()
    try:
        rise = db.query(Alert).filter(Alert.product_id == product_id,
                                      Alert.alert_type == "price_rise").one()
        assert rise.is_active is True
    finally:
        db.close()


def test_reactivare_dupa_off_rearmeaza_aceeasi_alerta(auth_client):
    """OFF -> ON cu prag nou: aceeasi alerta (fara duplicat) revine activa, ne-declansata."""
    product_id = _mk_product(auth_client)
    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": True, "alert_threshold": 90})
    auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                      json={"active": False})

    r = auth_client.patch(f"/api/tracked-products/{product_id}/monitoring",
                          json={"active": True, "alert_threshold": 75})
    assert r.status_code == 200, r.text

    alerts = _price_drop_alerts(product_id)
    assert len(alerts) == 1
    assert alerts[0]["is_active"] is True
    assert alerts[0]["is_triggered"] is False
    assert float(alerts[0]["target_price"]) == 75.0
    assert _item_in_feed(auth_client, product_id)["alert_threshold"] == 75.0
