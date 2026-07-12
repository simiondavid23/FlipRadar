"""GE-2 — filtrele roi_min/roi_max pe GET /api/products (ROI = (resale-curent)/curent*100)."""

import pytest


@pytest.fixture(autouse=True)
def _no_cross_shop(monkeypatch):
    """create_product programeaza _cross_shop_match (scrape live ~11s/produs) ca
    BackgroundTask, iar TestClient il ruleaza sincron dupa raspuns. Il neutralizam —
    testele nu ating reteaua. Patch pe numele din namespace-ul routerului (acelasi
    pattern ca in test_financiar.py)."""
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda product_id: None)


def _mk(auth_client, name, current, resale):
    r = auth_client.post("/api/products/", json={
        "name": name, "current_price": current, "resale_price": resale,
    })
    assert r.status_code == 200, r.text


def _names(auth_client, **params):
    r = auth_client.get("/api/products/", params=params)
    assert r.status_code == 200, r.text
    return {p["name"] for p in r.json()}


def test_roi_max_filtreaza_sub_prag(auth_client):
    _mk(auth_client, "GE2 A roi5", 100, 105)   # ROI 5%
    _mk(auth_client, "GE2 B roi50", 100, 150)  # ROI 50%
    _mk(auth_client, "GE2 C fara resale", 100, None)

    names = _names(auth_client, roi_max=10)
    assert "GE2 A roi5" in names
    assert "GE2 B roi50" not in names
    # guard: produsele fara resale_price nu au ROI si nu apar la filtrarea dupa ROI
    assert "GE2 C fara resale" not in names


def test_roi_min_exclusiv_peste_prag(auth_client):
    _mk(auth_client, "GE2 D roi5", 100, 105)   # ROI 5%
    _mk(auth_client, "GE2 E roi50", 100, 150)  # ROI 50%

    names = _names(auth_client, roi_min=10)
    assert "GE2 E roi50" in names
    assert "GE2 D roi5" not in names


def test_roi_min_max_combinate(auth_client):
    _mk(auth_client, "GE2 F roi5", 100, 105)   # ROI 5%
    _mk(auth_client, "GE2 G roi20", 100, 120)  # ROI 20%
    _mk(auth_client, "GE2 H roi80", 100, 180)  # ROI 80%

    names = _names(auth_client, roi_min=10, roi_max=60)
    assert "GE2 G roi20" in names
    assert "GE2 F roi5" not in names
    assert "GE2 H roi80" not in names
