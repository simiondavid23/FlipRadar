"""RETAIL-3b — restock, prag procentual per alerta (Alert.drop_pct) si minimul
pe 30 de zile in Flash Deal.

Fara retea: refresh_source, coada Discord si emailul sunt stub-uite. Testele
merg pe fluxul real (_refresh_all_scrapeable_products / check_alerts), nu pe
functii izolate, fiindca exact interactiunea lor e ce s-a schimbat.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.radar_settings import RadarSettings
from app.models.tracked_product import TrackedProduct
from app.models.user import User
from app.services import catalog_health_watchdog
from app.services.discord_service import RESTOCK_COLOR
from app.utils.alert_checker import _refresh_all_scrapeable_products, check_alerts

URL = "https://www.emag.ro/produs-3b/pd/XYZ/"
URL_B = "https://altex.ro/produs-3b/cpd/ABC/"


@pytest.fixture(autouse=True)
def _clean_watchdog():
    catalog_health_watchdog._reset_state()


@pytest.fixture
def sent(monkeypatch):
    """Spy pe coada Discord: (embed, listing_id) per notificare pusa in coada."""
    calls = []

    def _send(embed, settings, listing_id):
        calls.append((embed, listing_id))
        return True

    monkeypatch.setattr("app.utils.alert_checker.send_price_alert_notification", _send)
    return calls


@pytest.fixture
def emails(monkeypatch):
    """Spy pe emailul de alerta + SMTP raportat ca fiind configurat."""
    calls = []
    monkeypatch.setattr("app.utils.alert_checker.email_is_configured", lambda: True)
    monkeypatch.setattr("app.utils.alert_checker.send_alert_email",
                        lambda **kw: calls.append(kw) or True)
    return calls


def _stub_refresh(monkeypatch, by_url=None, price=None, in_stock=None):
    """refresh_source fals: pret fix, sau per source_url cand sunt mai multe surse."""
    def _refresh(**kw):
        if by_url is not None:
            value = by_url[kw["source_url"]]
            if isinstance(value, dict):
                return value
            return {"price": value, "in_stock": in_stock, "method": "url"}
        return {"price": price, "in_stock": in_stock, "method": "url"}

    monkeypatch.setattr("app.utils.alert_checker.refresh_source", _refresh)


def _mk_user(db, with_webhook=True):
    uniq = uuid.uuid4().hex[:10]
    user = User(email=f"r3b_{uniq}@example.com", username=f"r3b_{uniq}", hashed_password="x")
    db.add(user)
    db.flush()
    if with_webhook:
        db.add(RadarSettings(user_id=user.id,
                             discord_webhook_alerts="https://discord.com/api/webhooks/t/t"))
    return user


def _run_refresh():
    work = SessionLocal()
    try:
        return _refresh_all_scrapeable_products(work)
    finally:
        work.close()


def _alert_row(alert_id):
    db = SessionLocal()
    try:
        return db.query(Alert).filter(Alert.id == alert_id).one()
    finally:
        db.close()


# ── restock ───────────────────────────────────────────────────────────────────

def test_restock_notifica_ownerul_si_watcherul_activ(monkeypatch, sent):
    db = SessionLocal()
    try:
        owner, watcher = _mk_user(db), _mk_user(db)
        p = Product(user_id=owner.id, name="Produs 3b", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", in_stock=False))
        db.add(TrackedProduct(user_id=watcher.id, product_id=p.id, monitoring_active=True))
        db.commit()
        pid, owner_id, watcher_id = p.id, owner.id, watcher.id
    finally:
        db.close()

    # Pret neschimbat: izoleaza restock-ul de flash deal.
    _stub_refresh(monkeypatch, price=100.0, in_stock=True)
    _run_refresh()

    assert {lid for _, lid in sent} == {
        f"restock-{pid}-{owner_id}-emag.ro",
        f"restock-{pid}-{watcher_id}-emag.ro",
    }
    embed = sent[0][0]
    assert embed["color"] == RESTOCK_COLOR
    assert "Din nou in stoc" in embed["title"]
    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["💰 Pret"] == "100.00 RON"
    assert by_name["🏪 Sursa"] == "EMAG.RO"


@pytest.mark.parametrize("old_stock, new_stock", [
    (None, True),    # necunoscut -> cunoscut, NU e revenire
    (False, False),
    (True, True),
    (True, False),   # iesire din stoc: alta poveste, nu notificam aici
])
def test_fara_restock_pe_celelalte_tranzitii(monkeypatch, sent, old_stock, new_stock):
    db = SessionLocal()
    try:
        owner = _mk_user(db)
        p = Product(user_id=owner.id, name="Produs 3b", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", in_stock=old_stock))
        db.commit()
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=100.0, in_stock=new_stock)
    _run_refresh()

    assert sent == []


def test_watcher_inactiv_nu_primeste_restock(monkeypatch, sent):
    db = SessionLocal()
    try:
        owner, watcher = _mk_user(db), _mk_user(db)
        p = Product(user_id=owner.id, name="Produs 3b", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", in_stock=False))
        db.add(TrackedProduct(user_id=watcher.id, product_id=p.id, monitoring_active=False))
        db.commit()
        owner_id = owner.id
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=100.0, in_stock=True)
    _run_refresh()

    assert [lid.split("-")[2] for _, lid in sent] == [str(owner_id)]


# ── price_drops ───────────────────────────────────────────────────────────────

def test_price_drops_pastreaza_scaderea_maxima_si_ignora_cresterile(monkeypatch):
    db = SessionLocal()
    try:
        p = Product(name="Doua surse", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON"))
        db.add(ProductSource(product_id=p.id, source="altex.ro", source_url=URL_B,
                             current_price=100.0, currency="RON"))
        scump = Product(name="Produs in crestere", current_price=100.0, currency="RON")
        db.add(scump)
        db.flush()
        db.add(ProductSource(product_id=scump.id, source="emag.ro",
                             source_url="https://www.emag.ro/altul/pd/Q/",
                             current_price=100.0, currency="RON"))
        db.commit()
        pid, scump_id = p.id, scump.id
    finally:
        db.close()

    _stub_refresh(monkeypatch, by_url={
        URL: 80.0,                                    # -20%
        URL_B: 95.0,                                  # -5%
        "https://www.emag.ro/altul/pd/Q/": 120.0,     # +20%
    })
    refreshed, price_drops = _run_refresh()

    assert refreshed == 3
    assert price_drops == {pid: pytest.approx(0.20)}   # max-ul, si nicio crestere
    assert scump_id not in price_drops


def test_refresh_fara_schimbari_intoarce_tuplu_gol(monkeypatch):
    db = SessionLocal()
    try:
        p = Product(name="Neschimbat", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON"))
        db.commit()
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=100.0)

    assert _run_refresh() == (0, {})


# ── Alert.drop_pct in check_alerts ────────────────────────────────────────────

def _seed_alert(target_price=50.0, drop_pct=0.10, alert_type="price_drop",
                start_price=100.0, with_webhook=True):
    db = SessionLocal()
    try:
        user = _mk_user(db, with_webhook=with_webhook)
        p = Product(user_id=user.id, name="Produs alerta 3b",
                    current_price=start_price, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=start_price, currency="RON"))
        a = Alert(user_id=user.id, product_id=p.id, target_price=target_price,
                  currency="RON", alert_type=alert_type, drop_pct=drop_pct)
        db.add(a)
        db.commit()
        return a.id
    finally:
        db.close()


def test_drop_pct_declanseaza_fara_tinta_atinsa(monkeypatch, sent):
    monkeypatch.setattr("app.utils.alert_checker.email_is_configured", lambda: False)
    alert_id = _seed_alert(target_price=50.0, drop_pct=0.10)
    _stub_refresh(monkeypatch, price=88.0)  # 100 -> 88 = -12%, tinta 50 neatinsa

    assert check_alerts() == 1
    assert _alert_row(alert_id).is_triggered is True


def test_scadere_sub_prag_nu_declanseaza(monkeypatch, sent):
    monkeypatch.setattr("app.utils.alert_checker.email_is_configured", lambda: False)
    alert_id = _seed_alert(target_price=50.0, drop_pct=0.10)
    _stub_refresh(monkeypatch, price=92.0)  # -8% < 10%

    assert check_alerts() == 0
    assert _alert_row(alert_id).is_triggered is False


def test_drop_pct_ignorat_pe_price_rise(monkeypatch, sent):
    monkeypatch.setattr("app.utils.alert_checker.email_is_configured", lambda: False)
    alert_id = _seed_alert(target_price=999.0, drop_pct=0.10, alert_type="price_rise")
    _stub_refresh(monkeypatch, price=88.0)  # scadere de 12%, dar alerta e de crestere

    assert check_alerts() == 0
    assert _alert_row(alert_id).is_triggered is False


def test_declansare_pe_prag_foloseste_embed_de_scadere_si_nu_trimite_email(monkeypatch, sent, emails):
    alert_id = _seed_alert(target_price=50.0, drop_pct=0.10)
    _stub_refresh(monkeypatch, price=88.0)

    assert check_alerts() == 1

    assert emails == [], "emailul e construit pe tinta atinsa — nu se trimite pe drop pur"
    embed = next(e for e, lid in sent if lid.startswith(f"alert-{alert_id}-"))
    assert "scadere brusca" in embed["title"]
    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["📉 Scadere"] == "-12.0%"
    assert by_name["💰 Pret curent"] == "88.00 RON"
    assert "🎯 Tinta" not in by_name


def test_tinta_atinsa_pastreaza_embedul_clasic_si_trimite_email(monkeypatch, sent, emails):
    alert_id = _seed_alert(target_price=90.0, drop_pct=0.10)
    _stub_refresh(monkeypatch, price=88.0)  # tinta 90 atinsa SI scadere de 12%

    assert check_alerts() == 1

    assert len(emails) == 1
    embed = next(e for e, lid in sent if lid.startswith(f"alert-{alert_id}-"))
    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["🎯 Tinta"] == "90.00 RON"
    assert by_name["💰 Pret curent"] == "88.00 RON"


# ── minimul pe 30 de zile in Flash Deal ───────────────────────────────────────

def test_flash_deal_cu_minim_30_zile(monkeypatch, sent):
    """Minimul se ia doar de pe ACEEASI sursa si doar din ultimele 30 de zile."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        owner = _mk_user(db)
        p = Product(user_id=owner.id, name="Produs flash", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON"))
        db.add(PriceHistory(product_id=p.id, price=90.0, currency="RON", source="emag.ro",
                            recorded_at=now - timedelta(days=3)))
        # Zgomot care NU trebuie sa intre in minim:
        db.add(PriceHistory(product_id=p.id, price=10.0, currency="RON", source="altex.ro",
                            recorded_at=now - timedelta(days=3)))    # alta sursa
        db.add(PriceHistory(product_id=p.id, price=5.0, currency="RON", source="emag.ro",
                            recorded_at=now - timedelta(days=40)))   # prea vechi
        db.commit()
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=80.0)  # -20% => trece pragul implicit de flash (15%)
    _run_refresh()

    embed = next(e for e, lid in sent if lid.startswith("flashdeal-"))
    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["📊 Minim 30 zile"] == "90.0 RON"
    # 80 <= 90 -> pretul nou e cel mai mic din fereastra.
    assert by_name["🏆 Minim istoric"] == "Cel mai mic pret din ultimele 30 de zile"


def test_minim_30_zile_exclude_scaderea_curenta(monkeypatch, sent):
    """Randul inserat de scaderea curenta nu intra in propriul minim — altfel
    marcajul de minim istoric ar fi mereu adevarat."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        owner = _mk_user(db)
        p = Product(user_id=owner.id, name="Produs flash", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON"))
        db.add(PriceHistory(product_id=p.id, price=70.0, currency="RON", source="emag.ro",
                            recorded_at=now - timedelta(days=2)))
        db.commit()
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=80.0)  # peste minimul de 70 din fereastra
    _run_refresh()

    embed = next(e for e, lid in sent if lid.startswith("flashdeal-"))
    by_name = {f["name"]: f["value"] for f in embed["fields"]}
    assert by_name["📊 Minim 30 zile"] == "70.0 RON"
    assert "🏆 Minim istoric" not in by_name


def test_flash_deal_fara_istoric_nu_are_campul_de_minim(monkeypatch, sent):
    db = SessionLocal()
    try:
        owner = _mk_user(db)
        p = Product(user_id=owner.id, name="Produs flash", current_price=100.0, currency="RON")
        db.add(p)
        db.flush()
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON"))
        db.commit()
    finally:
        db.close()

    _stub_refresh(monkeypatch, price=80.0)
    _run_refresh()

    embed = next(e for e, lid in sent if lid.startswith("flashdeal-"))
    assert "📊 Minim 30 zile" not in {f["name"] for f in embed["fields"]}


# ── API ───────────────────────────────────────────────────────────────────────

def _api_product(auth_client, monkeypatch):
    monkeypatch.setattr("app.routers.products._cross_shop_match", lambda product_id: None)
    r = auth_client.post("/api/products/", json={
        "name": "Produs API 3b", "current_price": 100.0, "currency": "RON"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_api_creeaza_alerta_cu_drop_pct(auth_client, monkeypatch):
    product_id = _api_product(auth_client, monkeypatch)

    r = auth_client.post("/api/alerts/", json={
        "product_id": product_id, "target_price": 50.0, "currency": "RON",
        "alert_type": "price_drop", "drop_pct": 0.2})

    assert r.status_code == 200, r.text
    assert r.json()["drop_pct"] == 0.2
    assert _alert_row(r.json()["id"]).drop_pct == 0.2


@pytest.mark.parametrize("bad", [1.5, 0, -0.1, 1])
def test_api_drop_pct_in_afara_intervalului_e_422(auth_client, monkeypatch, bad):
    product_id = _api_product(auth_client, monkeypatch)

    r = auth_client.post("/api/alerts/", json={
        "product_id": product_id, "target_price": 50.0, "drop_pct": bad})

    assert r.status_code == 422


def test_api_alerta_fara_drop_pct_ramane_pe_tinta(auth_client, monkeypatch):
    product_id = _api_product(auth_client, monkeypatch)

    r = auth_client.post("/api/alerts/", json={
        "product_id": product_id, "target_price": 50.0})

    assert r.status_code == 200, r.text
    assert r.json()["drop_pct"] is None


def test_api_toggle_rearmeaza_alerta_declansata_prin_drop(auth_client, monkeypatch):
    product_id = _api_product(auth_client, monkeypatch)
    created = auth_client.post("/api/alerts/", json={
        "product_id": product_id, "target_price": 50.0, "drop_pct": 0.1})
    alert_id = created.json()["id"]

    db = SessionLocal()
    try:
        a = db.query(Alert).filter(Alert.id == alert_id).one()
        a.is_triggered = True
        a.triggered_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    r = auth_client.put(f"/api/alerts/{alert_id}/toggle")

    assert r.status_code == 200, r.text
    rearmed = _alert_row(alert_id)
    assert rearmed.is_triggered is False
    assert rearmed.triggered_at is None
    assert rearmed.is_active is True
    assert rearmed.drop_pct == 0.1  # rearmarea nu pierde pragul
