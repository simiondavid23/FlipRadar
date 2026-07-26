"""FASHION-1c — fluxul de variante prin backend: from-url cu marime, refresh pe
varianta, notificari etichetate.

Fara retea: extractorul e inlocuit cu un fals configurabil (ca in
test_products_from_url), iar refresh_source / coada Discord sunt stub-uite (ca in
test_retail_alerts). Regula pinuita peste tot: cu variant="" comportamentul
ramane IDENTIC cu cel dinainte de acest task — inclusiv listing_id-urile Discord.
"""
import uuid

import pytest

from app.database import SessionLocal
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services import catalog_health_watchdog
from app.services.product_page_extractor import ProductExtractionError
from app.services.scraper_service import refresh_source
from app.utils.alert_checker import _refresh_all_scrapeable_products

URL = "https://epantofi.ro/p/sneakers-nike-dunk-low-f1c"

VARIANTS = [
    {"variant": "40_5", "price": 652.0, "in_stock": False},
    {"variant": "42", "price": 699.0, "in_stock": True},
    {"variant": "44", "price": 719.0, "in_stock": True},
]


def _res(**over):
    """Rezultat de extractor in forma FASHION-1b (ProductGroup cu variante)."""
    base = {
        "name": "Sneakers Nike Dunk Low F1C",
        "price": 699.0,               # agregatul "de la" (minimul in stoc)
        "currency": "RON",
        "in_stock": True,
        "is_aggregate": True,
        "image_url": None,
        "canonical_url": URL,
        "domain": "epantofi.ro",
        "method": "jsonld",
        "override_applied": False,
        "variants": [dict(v) for v in VARIANTS],
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def fake_extract(monkeypatch):
    """Extractor fals + retea taiata din background tasks (TestClient le ruleaza
    sincron dupa raspuns)."""
    import app.routers.products as products

    state = {"result": _res()}
    monkeypatch.setattr(products, "extract_product",
                        lambda url, max_retries=3: dict(state["result"]))
    monkeypatch.setattr(products, "fetch_ean_from_url", lambda *a, **k: None)
    monkeypatch.setattr(products, "find_cross_shop_matches",
                        lambda *a, **k: {"ean_matches": [], "name_candidates": []})
    return state


@pytest.fixture(autouse=True)
def _clean_watchdog():
    catalog_health_watchdog._reset_state()


def _sources(product_id=None):
    db = SessionLocal()
    try:
        q = db.query(ProductSource)
        if product_id is not None:
            q = q.filter(ProductSource.product_id == product_id)
        return {s.variant: s for s in q.order_by(ProductSource.id).all()}
    finally:
        db.close()


def _history(product_id):
    db = SessionLocal()
    try:
        return [(h.price, h.variant) for h in db.query(PriceHistory)
                .filter(PriceHistory.product_id == product_id)
                .order_by(PriceHistory.id).all()]
    finally:
        db.close()


# ── from-url cu marime ────────────────────────────────────────────────────────

def test_from_url_cu_marime_salveaza_pretul_intrarii_nu_agregatul(auth_client):
    r = auth_client.post("/api/products/from-url", json={"url": URL, "variant": "44"})
    assert r.status_code == 200, r.text
    body = r.json()
    pid = body["product"]["id"]

    rows = _sources(pid)
    assert set(rows) == {"44"}
    assert rows["44"].current_price == 719.0      # pretul marimii, nu agregatul 699
    assert rows["44"].in_stock is True
    assert rows["44"].source == "epantofi.ro"
    assert _history(pid) == [(719.0, "44")]
    # Marimile paginii ajung in raspuns pentru UI (FASHION-1d).
    assert [v["variant"] for v in body["variants"]] == ["40_5", "42", "44"]


def test_from_url_doua_marimi_dau_doua_surse_sub_acelasi_produs(auth_client):
    r1 = auth_client.post("/api/products/from-url", json={"url": URL, "variant": "42"})
    r2 = auth_client.post("/api/products/from-url", json={"url": URL, "variant": "44"})
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["product"]["id"] == r2.json()["product"]["id"]   # dedup pe nume+sursa

    pid = r1.json()["product"]["id"]
    rows = _sources(pid)
    assert set(rows) == {"42", "44"}
    assert rows["42"].current_price == 699.0
    assert rows["44"].current_price == 719.0
    assert rows["42"].in_stock is True
    assert sorted(_history(pid)) == sorted([(699.0, "42"), (719.0, "44")])

    db = SessionLocal()
    try:
        assert db.query(Product).count() == 1
    finally:
        db.close()


def test_from_url_cu_marime_inexistenta_da_422_cu_marimile_disponibile(auth_client):
    r = auth_client.post("/api/products/from-url", json={"url": URL, "variant": "45"})

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "45" in detail
    for size in ("40_5", "42", "44"):
        assert size in detail
    db = SessionLocal()
    try:
        assert db.query(ProductSource).count() == 0   # nu s-a salvat nimic
    finally:
        db.close()


def test_from_url_cu_marime_pe_pagina_fara_variante_da_422(auth_client, fake_extract):
    fake_extract["result"] = _res(variants=None, is_aggregate=False)

    r = auth_client.post("/api/products/from-url", json={"url": URL, "variant": "42"})

    assert r.status_code == 422
    assert "mărime" in r.json()["detail"]


def test_from_url_fara_marime_ramane_exact_ca_azi(auth_client):
    """REGRESIE: fara `variant`, se salveaza randul "" cu agregatul, ca inainte."""
    r = auth_client.post("/api/products/from-url", json={"url": URL})
    assert r.status_code == 200, r.text
    pid = r.json()["product"]["id"]

    rows = _sources(pid)
    assert set(rows) == {""}
    assert rows[""].current_price == 699.0         # agregatul din extractor
    assert rows[""].in_stock is True
    assert _history(pid) == [(699.0, "")]


# ── refresh_source pe varianta ────────────────────────────────────────────────

def _stub_extract(monkeypatch, result):
    monkeypatch.setattr("app.services.scraper_service.extract_product",
                        lambda url, **kw: dict(result))


def test_refresh_source_cu_marime_citeste_intrarea_ei(monkeypatch):
    _stub_extract(monkeypatch, _res())

    out = refresh_source("epantofi.ro", URL, "Sneakers", variant="40_5")

    assert out == {"price": 652.0, "in_stock": False, "method": "url"}


def test_refresh_source_cu_marime_fara_potrivire_intoarce_none(monkeypatch, capsys):
    """Mai bine pret vechi decat pretul altei marimi: NU cade pe re-cautare."""
    _stub_extract(monkeypatch, _res())

    assert refresh_source("epantofi.ro", URL, "Sneakers", variant="45") is None
    assert "45" in capsys.readouterr().out


def test_refresh_source_cu_marime_dar_pagina_fara_variante_intoarce_none(monkeypatch):
    _stub_extract(monkeypatch, _res(variants=None))

    assert refresh_source("epantofi.ro", URL, "Sneakers", variant="42") is None


def test_refresh_source_fara_marime_ramane_pe_agregat(monkeypatch):
    """REGRESIE: variant="" pastreaza exact calea de azi (pretul product-level)."""
    _stub_extract(monkeypatch, _res())

    out = refresh_source("epantofi.ro", URL, "Sneakers")

    assert out == {"price": 699.0, "in_stock": True, "method": "url"}


# ── alert_checker: transmiterea variantei + notificari etichetate ─────────────

def _mk_user(db, with_webhook=True):
    uniq = uuid.uuid4().hex[:10]
    user = User(email=f"f1c_{uniq}@example.com", username=f"f1c_{uniq}", hashed_password="x")
    db.add(user)
    db.flush()
    if with_webhook:
        db.add(RadarSettings(user_id=user.id,
                             discord_webhook_alerts="https://discord.com/api/webhooks/t/t"))
    return user


def _seed(db, variant, *, price=699.0, in_stock=None):
    user = _mk_user(db)
    p = Product(user_id=user.id, name="Produs F1C", current_price=price, currency="RON")
    db.add(p)
    db.flush()
    db.add(ProductSource(product_id=p.id, source="epantofi.ro", source_url=URL,
                         current_price=price, currency="RON",
                         variant=variant, in_stock=in_stock))
    db.commit()
    return p.id


def _run_refresh():
    work = SessionLocal()
    try:
        return _refresh_all_scrapeable_products(work)
    finally:
        work.close()


@pytest.fixture
def sent(monkeypatch):
    """Spy pe coada Discord: (embed, listing_id) per notificare."""
    calls = []
    monkeypatch.setattr("app.utils.alert_checker.send_price_alert_notification",
                        lambda embed, settings, listing_id: calls.append((embed, listing_id)) or True)
    return calls


def test_bucla_transmite_varianta_catre_refresh_source(monkeypatch):
    db = SessionLocal()
    try:
        _seed(db, "42")
    finally:
        db.close()

    seen = {}

    def _spy(**kw):
        seen.update(kw)
        return {"price": 699.0, "in_stock": None, "method": "url"}

    monkeypatch.setattr("app.utils.alert_checker.refresh_source", _spy)
    _run_refresh()

    assert seen["variant"] == "42"


def test_restock_pe_varianta_are_lid_cu_marimea_si_field_in_embed(monkeypatch, sent):
    db = SessionLocal()
    try:
        pid = _seed(db, "42", in_stock=False)
        owner_id = db.query(Product).filter(Product.id == pid).one().user_id
    finally:
        db.close()

    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 699.0, "in_stock": True, "method": "url"})
    _run_refresh()

    embed, lid = next((e, l) for e, l in sent if l.startswith("restock-"))
    assert lid == f"restock-{pid}-{owner_id}-epantofi.ro-42"
    assert {"name": "📏 Marimea", "value": "42", "inline": True} in embed["fields"]


def test_restock_fara_varianta_pastreaza_lid_ul_de_azi(monkeypatch, sent):
    """REGRESIE PINUITA: sufixul NU apare pe randurile fara varianta, altfel s-ar
    reseta dedup-ul de 24h deja acumulat pe tot catalogul electro."""
    db = SessionLocal()
    try:
        pid = _seed(db, "", in_stock=False)
        owner_id = db.query(Product).filter(Product.id == pid).one().user_id
    finally:
        db.close()

    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 699.0, "in_stock": True, "method": "url"})
    _run_refresh()

    embed, lid = next((e, l) for e, l in sent if l.startswith("restock-"))
    assert lid == f"restock-{pid}-{owner_id}-epantofi.ro"
    assert not any(f["name"] == "📏 Marimea" for f in embed["fields"])


def test_flash_pe_varianta_are_marimea_in_embed(monkeypatch, sent):
    db = SessionLocal()
    try:
        _seed(db, "42", price=1000.0)
    finally:
        db.close()

    # -20% => trece pragul implicit de flash (15%)
    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 800.0, "in_stock": None, "method": "url"})
    _run_refresh()

    embed = next(e for e, l in sent if l.startswith("flashdeal-"))
    assert {"name": "📏 Marimea", "value": "42", "inline": True} in embed["fields"]


def test_flash_fara_varianta_nu_are_field_de_marime(monkeypatch, sent):
    db = SessionLocal()
    try:
        _seed(db, "", price=1000.0)
    finally:
        db.close()

    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 800.0, "in_stock": None, "method": "url"})
    _run_refresh()

    embed = next(e for e, l in sent if l.startswith("flashdeal-"))
    assert not any(f["name"] == "📏 Marimea" for f in embed["fields"])


# ── FASHION-1d: POST /extract-url (preview read-only) ─────────────────────────

def _nimic_in_baza():
    db = SessionLocal()
    try:
        return (db.query(Product).count(), db.query(ProductSource).count(),
                db.query(PriceHistory).count()) == (0, 0, 0)
    finally:
        db.close()


def test_extract_url_intoarce_previzualizarea_cu_variante(auth_client):
    r = auth_client.post("/api/products/extract-url", json={"url": URL})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Sneakers Nike Dunk Low F1C"
    assert body["price"] == 699.0
    assert body["currency"] == "RON"
    assert body["in_stock"] is True
    assert body["is_aggregate"] is True
    assert body["domain_validated"] is True          # epantofi.ro a intrat la FASHION-1b
    assert body["variants"] == VARIANTS
    # Esenta endpointului: previzualizarea NU scrie nimic.
    assert _nimic_in_baza()


def test_extract_url_fara_variante_da_variants_none(auth_client, fake_extract):
    fake_extract["result"] = _res(variants=None, is_aggregate=False,
                                  domain="altex.ro", price=249.99)

    r = auth_client.post("/api/products/extract-url", json={"url": URL})

    assert r.status_code == 200, r.text
    assert r.json()["variants"] is None
    assert r.json()["price"] == 249.99
    assert _nimic_in_baza()


def test_extract_url_domeniu_nepermis_da_400(auth_client, fake_extract, monkeypatch):
    """Aceeasi mapare de erori ca from-url: domeniul respins de garda SSRF -> 400."""
    import app.routers.products as products

    def _boom(url, max_retries=3):
        raise ProductExtractionError("domain_not_allowed", "nu e pe lista")

    monkeypatch.setattr(products, "extract_product", _boom)

    r = auth_client.post("/api/products/extract-url", json={"url": "https://xyz.tld/p/1"})

    assert r.status_code == 400
    assert "xyz.tld" in r.json()["detail"]
    assert _nimic_in_baza()


def test_extract_url_fara_date_de_produs_da_422(auth_client, monkeypatch):
    import app.routers.products as products

    def _boom(url, max_retries=3):
        raise ProductExtractionError("no_product_data", "pagina nu are date")

    monkeypatch.setattr(products, "extract_product", _boom)

    r = auth_client.post("/api/products/extract-url", json={"url": URL})

    assert r.status_code == 422
    assert _nimic_in_baza()


def test_extract_url_magazin_blocat_da_502(auth_client, monkeypatch):
    import app.routers.products as products

    def _boom(url, max_retries=3):
        raise ProductExtractionError("challenge", "interstitiu anti-bot")

    monkeypatch.setattr(products, "extract_product", _boom)

    assert auth_client.post("/api/products/extract-url", json={"url": URL}).status_code == 502
    assert _nimic_in_baza()


def test_extract_url_cere_autentificare(client):
    """Fara sesiune -> 401, ca restul routerului (niciun fetch nu se intampla)."""
    assert client.post("/api/products/extract-url", json={"url": URL}).status_code == 401


def test_extract_url_cere_can_use_scraping(auth_client):
    """Acelasi gard de feature ca from-url: fara can_use_scraping -> 403."""
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id.desc()).first()
        user.can_use_scraping = False
        db.commit()
    finally:
        db.close()

    r = auth_client.post("/api/products/extract-url", json={"url": URL})

    assert r.status_code == 403
    assert _nimic_in_baza()
