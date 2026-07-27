"""FASHION-3a — referinta de revanzare + profilul de taxe.

Fara retea: BNR e monkeypatchat pe get_all_rates (cheile reale sunt
"EUR_RON"/"USD_RON"). Rate fixe in toate testele: EUR=5.0, USD=4.5 — alese
rotund ca aserttiile sa fie verificabile cu mana.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.product import Product
from app.models.resale_fee_profile import ResaleFeeProfile
from app.models.resale_reference import ResaleReference
from app.models.user import User
from app.services import resale_service

RATES = {"EUR_RON": 5.0, "USD_RON": 4.5}


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setattr(resale_service, "get_all_rates", lambda: dict(RATES))


class _Profile:
    """Profil minim pentru testele pure (fara DB)."""

    def __init__(self, commission=0.0, processing=0.0, extra=0.0,
                 fixed=0.0, shipping=0.0, currency="EUR"):
        self.commission_pct = commission
        self.processing_pct = processing
        self.extra_pct = extra
        self.fixed_fee = fixed
        self.shipping_cost = shipping
        self.currency = currency


# ── calculul net (pur) ────────────────────────────────────────────────────────

def test_net_doar_procente():
    """200 EUR = 1000 RON; 12.5% taxe -> 875 RON."""
    net = resale_service.compute_net_ron(200.0, "EUR", _Profile(commission=9.5, processing=3.0))

    assert net == pytest.approx(875.0)
    assert resale_service.net_in(net, "EUR") == 175.0


def test_net_cu_fixe_in_alta_valuta_decat_referinta():
    """Referinta EUR, taxe fixe in USD: fiecare se converteste separat prin RON.
    200 EUR = 1000 RON; -12.4% -> 876 RON; fix 10 USD + transport 5 USD = 15 USD
    = 67.5 RON -> 808.5 RON."""
    profile = _Profile(commission=9.5, extra=2.9, fixed=10.0, shipping=5.0, currency="USD")

    net = resale_service.compute_net_ron(200.0, "EUR", profile)

    assert net == pytest.approx(808.5)
    assert resale_service.net_in(net, "EUR") == 161.7
    assert resale_service.net_in(net, "USD") == 179.67   # 808.5 / 4.5


def test_net_in_ron_e_identitate():
    net = resale_service.compute_net_ron(1000.0, "RON", _Profile(commission=10.0, fixed=50.0, currency="RON"))

    assert net == pytest.approx(850.0)
    assert resale_service.net_in(net, "RON") == 850.0


def test_valuta_necunoscuta_arunca_valueerror():
    with pytest.raises(ValueError) as exc:
        resale_service.compute_net_ron(100.0, "GBP", _Profile())
    assert "GBP" in str(exc.value)


def test_fara_profil_netul_e_referinta_convertita():
    """Profil neconfigurat = toate taxele zero, vizibil ca net == brut."""
    assert resale_service.compute_net_ron(100.0, "EUR", None) == pytest.approx(500.0)


# ── profiluri de taxe (API) ───────────────────────────────────────────────────

def test_seed_creeaza_cele_doua_profiluri_si_nu_le_dubleaza(auth_client):
    r = auth_client.get("/api/resale/fee-profiles")
    assert r.status_code == 200, r.text
    by_platform = {p["platform"]: p for p in r.json()}

    assert set(by_platform) == {"stockx", "goat"}
    sx, gt = by_platform["stockx"], by_platform["goat"]
    assert (sx["label"], sx["commission_pct"], sx["processing_pct"], sx["extra_pct"]) == \
        ("StockX", 9.5, 3.0, 0.0)
    assert (gt["label"], gt["commission_pct"], gt["processing_pct"], gt["extra_pct"]) == \
        ("GOAT", 9.5, 0.0, 2.9)
    assert (sx["currency"], gt["currency"]) == ("EUR", "USD")
    # Fixele si transportul raman de completat de user.
    for p in (sx, gt):
        assert (p["fixed_fee"], p["shipping_cost"]) == (0.0, 0.0)
        assert p["verified_at"] == "2026-07-26"
        assert "contului tau" in p["note"]

    assert len(auth_client.get("/api/resale/fee-profiles").json()) == 2


def test_put_pe_profilul_altui_user_da_404(auth_client):
    """Profilul lui A, editat de B (client separat) -> 404."""
    auth_client.get("/api/resale/fee-profiles")          # seed pentru A
    db = SessionLocal()
    try:
        pid = db.query(ResaleFeeProfile).order_by(ResaleFeeProfile.id).first().id
    finally:
        db.close()

    other = _new_user_client()
    r = other.put(f"/api/resale/fee-profiles/{pid}", json={"commission_pct": 0.0})

    assert r.status_code == 404
    db = SessionLocal()
    try:
        assert db.query(ResaleFeeProfile).filter_by(id=pid).one().commission_pct == 9.5
    finally:
        db.close()


def test_profil_custom_duplicat_da_400(auth_client):
    payload = {"platform": "vinted", "label": "Vinted", "commission_pct": 5.0}
    assert auth_client.post("/api/resale/fee-profiles", json=payload).status_code == 200

    r = auth_client.post("/api/resale/fee-profiles", json=payload)

    assert r.status_code == 400
    assert "vinted" in r.json()["detail"]


# ── referinte (API) ───────────────────────────────────────────────────────────

def _new_user_client():
    """Client NOU cu user propriu (auth_client refoloseste acelasi cookie jar)."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    uniq = uuid.uuid4().hex[:12]
    payload = {
        "email": f"resale_{uniq}@example.com", "username": f"resale_{uniq}",
        "password": "testpass123", "full_name": "Resale User",
        "security_question": "Care e culoarea preferata?", "security_answer": "albastru",
    }
    assert c.post("/api/auth/register", json=payload).status_code == 200
    assert c.post("/api/auth/login", json={
        "email": payload["email"], "password": payload["password"]}).status_code == 200
    return c


def _mk_product(client, price=100.0, currency="EUR"):
    r = client.post("/api/products/", json={
        "name": f"Produs resale {uuid.uuid4().hex[:6]}",
        "current_price": price, "currency": currency})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _product_row(pid):
    db = SessionLocal()
    try:
        return db.query(Product).filter(Product.id == pid).one()
    finally:
        db.close()


def test_referinta_pe_produsul_altui_user_da_404(auth_client):
    pid = _mk_product(auth_client)
    other = _new_user_client()

    r = other.post(f"/api/products/{pid}/resale-references",
                   json={"platform": "stockx", "ref_price": 200.0})

    assert r.status_code == 404
    db = SessionLocal()
    try:
        assert db.query(ResaleReference).count() == 0
    finally:
        db.close()


def test_referinta_duplicata_pe_acelasi_triplet_da_400(auth_client):
    pid = _mk_product(auth_client)
    body = {"platform": "stockx", "variant": "42", "ref_price": 200.0}
    assert auth_client.post(f"/api/products/{pid}/resale-references", json=body).status_code == 200

    r = auth_client.post(f"/api/products/{pid}/resale-references", json=body)

    assert r.status_code == 400
    assert "42" in r.json()["detail"]


def test_prima_referinta_devine_primara_si_scrie_resale_price(auth_client):
    """Produs in EUR, profil StockX (9.5+3%): 200 EUR -> 1000 RON -> 875 RON net
    -> 175 EUR scris pe produs."""
    auth_client.get("/api/resale/fee-profiles")          # seed
    pid = _mk_product(auth_client, price=100.0, currency="EUR")

    r = auth_client.post(f"/api/products/{pid}/resale-references",
                         json={"platform": "stockx", "ref_price": 200.0, "ref_currency": "EUR"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_primary"] is True
    assert body["net"] == 175.0
    assert body["net_currency"] == "EUR"
    assert _product_row(pid).resale_price == 175.0


def test_set_primary_muta_flagul_si_recalculeaza(auth_client):
    auth_client.get("/api/resale/fee-profiles")
    pid = _mk_product(auth_client, currency="EUR")
    first = auth_client.post(f"/api/products/{pid}/resale-references",
                             json={"platform": "stockx", "ref_price": 200.0}).json()
    # GOAT in USD: 300 USD = 1350 RON; -12.4% -> 1182.6 RON -> 236.52 EUR.
    second = auth_client.post(f"/api/products/{pid}/resale-references",
                              json={"platform": "goat", "ref_price": 300.0,
                                    "ref_currency": "USD"}).json()
    assert second["is_primary"] is False
    assert _product_row(pid).resale_price == 175.0

    r = auth_client.post(f"/api/resale/references/{second['id']}/set-primary")

    assert r.status_code == 200, r.text
    assert r.json()["is_primary"] is True
    refs = {x["id"]: x for x in auth_client.get(f"/api/products/{pid}/resale-references").json()}
    assert refs[first["id"]]["is_primary"] is False
    assert _product_row(pid).resale_price == 236.52


def test_stergerea_primarei_lasa_resale_price_none(auth_client):
    auth_client.get("/api/resale/fee-profiles")
    pid = _mk_product(auth_client)
    ref = auth_client.post(f"/api/products/{pid}/resale-references",
                           json={"platform": "stockx", "ref_price": 200.0}).json()
    assert _product_row(pid).resale_price == 175.0

    assert auth_client.delete(f"/api/resale/references/{ref['id']}").status_code == 200

    assert _product_row(pid).resale_price is None


def test_referinta_pe_marime_coexista_cu_cea_de_produs(auth_client):
    """Acelasi produs, aceeasi platforma, marimi diferite — unicitatea e pe triplet."""
    pid = _mk_product(auth_client)
    a = auth_client.post(f"/api/products/{pid}/resale-references",
                         json={"platform": "stockx", "ref_price": 200.0})
    b = auth_client.post(f"/api/products/{pid}/resale-references",
                         json={"platform": "stockx", "variant": "42", "ref_price": 240.0})

    assert (a.status_code, b.status_code) == (200, 200), b.text
    refs = auth_client.get(f"/api/products/{pid}/resale-references").json()
    assert sorted(x["variant"] for x in refs) == ["", "42"]
    # Doar prima e primara; a doua e o marime urmarita in plus.
    assert [x["is_primary"] for x in sorted(refs, key=lambda x: x["id"])] == [True, False]


def test_referinta_aprinde_filtrarea_roi_existenta(auth_client):
    """E2E: masinaria veche de ROI se aprinde fara cod nou. Produs la 100 EUR +
    referinta cu net 175 EUR -> ROI 75% -> apare la roi_min=40."""
    auth_client.get("/api/resale/fee-profiles")
    pid = _mk_product(auth_client, price=100.0, currency="EUR")

    inainte = auth_client.get("/api/products/", params={"roi_min": 40}).json()
    assert pid not in [p["id"] for p in inainte]

    auth_client.post(f"/api/products/{pid}/resale-references",
                     json={"platform": "stockx", "ref_price": 200.0})

    dupa = auth_client.get("/api/products/", params={"roi_min": 40}).json()
    assert pid in [p["id"] for p in dupa]
    assert next(p for p in dupa if p["id"] == pid)["resale_price"] == 175.0


def test_editarea_taxelor_se_vede_imediat_in_net(auth_client):
    """Netul nu e stocat: dupa ce comisionul devine 0, aceeasi referinta raporteaza
    brutul, iar resale_price se actualizeaza la urmatoarea recalculare."""
    profiles = {p["platform"]: p for p in auth_client.get("/api/resale/fee-profiles").json()}
    pid = _mk_product(auth_client)
    ref = auth_client.post(f"/api/products/{pid}/resale-references",
                           json={"platform": "stockx", "ref_price": 200.0}).json()
    assert ref["net"] == 175.0

    assert auth_client.put(f"/api/resale/fee-profiles/{profiles['stockx']['id']}",
                           json={"commission_pct": 0.0, "processing_pct": 0.0}).status_code == 200

    refs = auth_client.get(f"/api/products/{pid}/resale-references").json()
    assert refs[0]["net"] == 200.0
