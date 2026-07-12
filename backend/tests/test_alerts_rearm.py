"""MON-1 — rearmarea alertelor declansate via PUT /api/alerts/{id}/toggle.

is_triggered NU e setabil prin API (nu e in AlertCreate); il setam direct in
DB-ul de test inainte de a apela toggle-ul. Produsul e creat prin API (acelasi
pattern ca in test_products_roi_filter), cu _cross_shop_match neutralizat
(altfel create_product ar face scrape live ca BackgroundTask).
"""
from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def _no_cross_shop(monkeypatch):
    # create_product programeaza _cross_shop_match (scrape live) ca BackgroundTask,
    # rulat sincron de TestClient dupa raspuns. Il neutralizam — testele nu ating reteaua.
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda product_id: None)


def _mk_alert(auth_client, target_price=100, alert_type="price_drop"):
    """Creeaza un produs + o alerta prin API si intoarce id-ul alertei."""
    rp = auth_client.post("/api/products/", json={"name": "MON1 produs", "current_price": 150})
    assert rp.status_code == 200, rp.text
    product_id = rp.json()["id"]
    ra = auth_client.post("/api/alerts/", json={
        "product_id": product_id,
        "target_price": target_price,
        "currency": "EUR",
        "alert_type": alert_type,
    })
    assert ra.status_code == 200, ra.text
    return ra.json()["id"]


def _set_state(alert_id, **fields):
    """Seteaza direct in DB campuri ce nu sunt setabile prin API (is_triggered etc.)."""
    from app.database import SessionLocal
    from app.models.alert import Alert

    db = SessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        for key, value in fields.items():
            setattr(alert, key, value)
        db.commit()
    finally:
        db.close()


def _state(alert_id):
    """Citeste starea alertei din DB (valori simple, in sesiune) dupa toggle."""
    from app.database import SessionLocal
    from app.models.alert import Alert

    db = SessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        return {
            "is_active": alert.is_active,
            "is_triggered": alert.is_triggered,
            "triggered_at": alert.triggered_at,
        }
    finally:
        db.close()


def test_toggle_rearmeaza_alerta_declansata(auth_client):
    # Declansata: is_triggered=True, triggered_at setat, is_active=False.
    alert_id = _mk_alert(auth_client)
    _set_state(alert_id, is_triggered=True, triggered_at=datetime(2026, 7, 1, 10, 0, 0), is_active=False)

    r = auth_client.put(f"/api/alerts/{alert_id}/toggle")
    assert r.status_code == 200, r.text

    st = _state(alert_id)
    assert st["is_triggered"] is False
    assert st["triggered_at"] is None
    assert st["is_active"] is True


def test_toggle_dezactiveaza_alerta_activa(auth_client):
    # Activa, nedeclansata (starea implicita dupa creare) -> toggle o dezactiveaza.
    alert_id = _mk_alert(auth_client)

    r = auth_client.put(f"/api/alerts/{alert_id}/toggle")
    assert r.status_code == 200, r.text

    st = _state(alert_id)
    assert st["is_active"] is False
    assert st["is_triggered"] is False


def test_toggle_activeaza_alerta_inactiva(auth_client):
    # Inactiva, nedeclansata -> toggle o (re)activeaza; is_triggered ramane False.
    alert_id = _mk_alert(auth_client)
    _set_state(alert_id, is_active=False)

    r = auth_client.put(f"/api/alerts/{alert_id}/toggle")
    assert r.status_code == 200, r.text

    st = _state(alert_id)
    assert st["is_active"] is True
    assert st["is_triggered"] is False
