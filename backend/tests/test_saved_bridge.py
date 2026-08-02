"""SAVED-BRIDGE + MKT-CLEAN — puntea salvate -> monitorizare si curatarea
alertelor marketplace moarte.

SAVED-BRIDGE: un anunt deja vazut care reapare in cautare actualizeaza randul
existent (pret + scor + last_checked_at) si notifica scaderile de pret >=5%
pe anunturile SALVATE (Radar). Auto: pretul si gradul se actualizeaza la
reaparitie. Imobiliare avea deja acest comportament — a fost modelul.

MKT-CLEAN: endpoint-urile /api/marketplace/keyword-alerts si modelul
MarketplaceKeywordAlert au fost eliminate (cod mort: fara UI, fara evaluator;
functionalitatea e acoperita de Radar keywords).
"""
import json
import types
import uuid
from datetime import datetime, timezone

import pytest

from app.utils import radar_scanner as rs


# ── infrastructura comuna ────────────────────────────────────────────────────────

class _KwStub:
    """Stub minimal pentru RadarKeyword — doar atributele citite de punte."""
    def __init__(self, resale_price=500.0, notify_discord=False):
        self.resale_price = resale_price
        self.min_margin_pct = 10.0
        self.grade_a_min = None
        self.grade_b_min = None
        self.grade_c_min = None
        self.notify_discord = notify_discord
        self.name = "kw-test"


def _mk_radar_row(auth_client, price=200.0, currency="RON", status="active"):
    """Creeaza un keyword real (FK) si un rand RadarListing; intoarce (uid, row_id, ext)."""
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    me = auth_client.get("/api/auth/me").json()["id"]
    r = auth_client.post("/api/radar/keywords", json={
        "name": f"kw {uuid.uuid4().hex[:6]}", "max_price": 1000.0,
        "resale_price": 500.0, "platforms": ["vinted"]})
    kid = r.json()["id"]
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        row = RadarListing(user_id=me, keyword_id=kid, external_id=ext,
                           platform="vinted", title="Geaca de test", price=price,
                           currency=currency, url="https://vinted.ro/x",
                           images=json.dumps(["https://img/x.jpg"]),
                           score="B", margin_pct=50.0, status=status)
        db.add(row); db.commit(); db.refresh(row)
        return me, row.id, ext
    finally:
        db.close()


def _row(row_id):
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    db = SessionLocal()
    try:
        return db.query(RadarListing).get(row_id)
    finally:
        db.close()


def _refresh(uid, ext, listing_over=None, kw=None, monkeypatch=None,
             notif_calls=None, push_calls=None):
    from app.database import SessionLocal
    listing = {"external_id": ext, "price": 100.0, "currency": "RON"}
    listing.update(listing_over or {})
    if monkeypatch is not None:
        monkeypatch.setattr(rs, "send_radar_notification",
                            lambda **kwargs: (notif_calls.append(kwargs) or 1)
                            if notif_calls is not None else 1)
        monkeypatch.setattr(rs, "is_push_configured",
                            lambda: push_calls is not None)
        if push_calls is not None:
            monkeypatch.setattr(rs, "notify_user_push",
                                lambda *a, **kw2: push_calls.append(kw2))
        monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    db = SessionLocal()
    try:
        return rs._refresh_seen_listing(
            db, types.SimpleNamespace(id=uid), kw or _KwStub(), "vinted",
            listing, settings=None)
    finally:
        db.close()


# ── Radar: puntea propriu-zisa ───────────────────────────────────────────────────

def test_reaparitia_fara_rand_in_feed_nu_face_nimic(auth_client, monkeypatch):
    me = auth_client.get("/api/auth/me").json()["id"]
    out = _refresh(me, f"vinted_{uuid.uuid4().hex[:10]}", monkeypatch=monkeypatch)
    assert out is None


def test_pret_neschimbat_face_doar_bump(auth_client, monkeypatch):
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0)
    out = _refresh(uid, ext, {"price": 200.0}, monkeypatch=monkeypatch)
    assert out == "bumped"
    row = _row(rid)
    assert row.price == 200.0 and row.last_checked_at is not None


def test_pretul_nou_actualizeaza_pret_si_scor(auth_client, monkeypatch):
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0)
    out = _refresh(uid, ext, {"price": 100.0}, monkeypatch=monkeypatch)
    assert out == "updated"                       # activ, nu salvat -> fara notificare
    row = _row(rid)
    assert row.price == 100.0
    assert row.score == "A"                       # marja 80% fata de resale 500
    assert abs(row.margin_pct - 80.0) < 0.01


def test_moneda_diferita_nu_se_compara(auth_client, monkeypatch):
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0, currency="RON")
    out = _refresh(uid, ext, {"price": 100.0, "currency": "EUR"},
                   monkeypatch=monkeypatch)
    assert out == "bumped"
    assert _row(rid).price == 200.0               # pretul NU s-a atins


def test_scadere_pe_salvat_notifica_discord_si_push(auth_client, monkeypatch):
    notif, push = [], []
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0, status="saved")
    out = _refresh(uid, ext, {"price": 180.0},    # -10% >= pragul de 5%
                   kw=_KwStub(notify_discord=True), monkeypatch=monkeypatch,
                   notif_calls=notif, push_calls=push)
    assert out == "notified"
    assert len(notif) == 1
    assert notif[0]["listing_id"] == f"pricedrop-{rid}-180"   # dedup pe nivel de pret
    assert "Pret scazut" in notif[0]["listing"]["title"]
    assert len(push) == 1
    assert _row(rid).price == 180.0


def test_scadere_pe_activ_nu_notifica(auth_client, monkeypatch):
    notif = []
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0, status="active")
    out = _refresh(uid, ext, {"price": 180.0}, kw=_KwStub(notify_discord=True),
                   monkeypatch=monkeypatch, notif_calls=notif)
    assert out == "updated" and notif == []


def test_scadere_sub_prag_pe_salvat_nu_notifica(auth_client, monkeypatch):
    notif = []
    uid, rid, ext = _mk_radar_row(auth_client, price=200.0, status="saved")
    out = _refresh(uid, ext, {"price": 195.0},    # -2.5% < 5%
                   kw=_KwStub(notify_discord=True), monkeypatch=monkeypatch,
                   notif_calls=notif)
    assert out == "updated" and notif == []
    assert _row(rid).price == 195.0               # pretul tot se actualizeaza


def test_call_site_ul_din_bucla_apeleaza_puntea():
    import inspect
    src = inspect.getsource(rs)
    i_seen = src.index("if _already_seen(db, user.id, platform, ext_id):")
    i_call = src.index("_refresh_seen_listing(db, user, kw, platform, listing, settings)")
    i_cont = src.index("continue", i_seen)
    assert i_seen < i_call < i_cont + len(src)    # puntea ruleaza inainte de continue


# ── Auto: pretul si gradul se actualizeaza la reaparitie ─────────────────────────

def _mk_auto_row(auth_client, price=200.0, currency="RON"):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    me = auth_client.get("/api/auth/me").json()["id"]
    ext = f"a{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        row = AutoFeedListing(user_id=me, keyword_id=None, platform="autovit",
                              external_id=ext, title="BMW test", price=price,
                              currency=currency, status="active")
        db.add(row); db.commit(); db.refresh(row)
        return me, row.id, ext
    finally:
        db.close()


def _auto_kw(uid):
    return types.SimpleNamespace(user_id=uid, platform="autovit",
                                 min_margin_pct=None, grade_a_min=None,
                                 grade_b_min=None, grade_c_min=None)


def test_auto_reaparitia_actualizeaza_pret_si_grad(auth_client):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    from app.services.auto_listings_scanner import _save_listing
    uid, rid, ext = _mk_auto_row(auth_client, price=400.0)
    db = SessionLocal()
    try:
        out = _save_listing(db, _auto_kw(uid),
                            {"external_id": ext, "price": 100.0, "currency": "RON"},
                            resale_price_ron=500.0)
        assert out is False                        # nu e nou
        row = db.query(AutoFeedListing).get(rid)
        assert row.price == 100.0
        assert row.grade == "A" and row.score == 80
    finally:
        db.close()


def test_auto_moneda_diferita_nu_atinge_pretul(auth_client):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    from app.services.auto_listings_scanner import _save_listing
    uid, rid, ext = _mk_auto_row(auth_client, price=400.0, currency="RON")
    db = SessionLocal()
    try:
        _save_listing(db, _auto_kw(uid),
                      {"external_id": ext, "price": 100.0, "currency": "EUR"},
                      resale_price_ron=500.0)
        row = db.query(AutoFeedListing).get(rid)
        assert row.price == 400.0                  # neschimbat
    finally:
        db.close()


# ── MKT-CLEAN: alertele marketplace au disparut ──────────────────────────────────

def test_endpointurile_keyword_alerts_nu_mai_exista(auth_client):
    assert auth_client.get("/api/marketplace/keyword-alerts").status_code == 404
    # POST poate intoarce 405 (path-ul mai exista doar ca prefix pentru alte metode
    # in routerul starlette) — esentialul e ca NU exista handler care sa raspunda 2xx.
    assert auth_client.post("/api/marketplace/keyword-alerts",
                            json={"platform": "olx", "keyword": "x"}).status_code in (404, 405)


def test_modelul_alertelor_nu_mai_e_inregistrat():
    from app.database import Base
    names = {m.class_.__name__ for m in Base.registry.mappers}
    assert "MarketplaceKeywordAlert" not in names


def test_cautarile_live_marketplace_raman(auth_client):
    # Garda de regresie: curatarea a atins DOAR alertele, nu si restul routerului.
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/marketplace/search-all" in paths
    assert "/api/marketplace/saved" in paths
    assert not any("keyword-alerts" in p for p in paths)
