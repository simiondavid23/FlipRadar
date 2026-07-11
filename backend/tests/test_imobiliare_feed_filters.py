"""IM-3 — filtre feed Imobiliare server-side: oraș (param DB), zonă/oraș ca opțiuni de dropdown,
camere 4+ (>=), export aliniat cu filtrele, stats total doar active.

Aceleași fixtures/stil ca test_imobiliare_feed_actions.py (auth_client din conftest, inserare
directă în DB, xlsx citit cu openpyxl).
"""
from io import BytesIO

import openpyxl

from app.database import SessionLocal
from app.models.user import User
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing

_FEED = "/api/real-estate-monitor/feed"
_EXPORT = "/api/real-estate-monitor/feed/export"
_OPTIONS = "/api/real-estate-monitor/feed/filter-options"
_STATS = "/api/real-estate-monitor/stats"


def _me_id(auth_client) -> int:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _data_rows(blob: bytes):
    """(count, titluri) — rânduri de date fără header; col 1 = Titlu în exportul RE."""
    ws = openpyxl.load_workbook(BytesIO(blob)).active
    titles = [row[0] for row in ws.iter_rows(min_row=2, values_only=True)
              if row and any(v not in (None, "") for v in row)]
    return len(titles), titles


def _mk(db, user_id, title="Anunț", status="active", city="București",
        zone=None, rooms=None, platform="olx", price=350):
    row = RealEstateListing(user_id=user_id, platform=platform, title=title, status=status,
                            price=price, currency="EUR", city=city, zone_normalized=zone, rooms=rooms)
    db.add(row); db.commit(); db.refresh(row)
    return row.id


# ── oraș server-side ─────────────────────────────────────────────────────────
def test_feed_city_server_side(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        _mk(db, uid, "Buc 1", city="București")
        _mk(db, uid, "Buc 2", city="București")
        _mk(db, uid, "Cluj 1", city="Cluj-Napoca")
    finally:
        db.close()
    r = auth_client.get(_FEED, params={"city": "Cluj-Napoca"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert {i["title"] for i in data["items"]} == {"Cluj 1"}
    assert all(i["city"] == "Cluj-Napoca" for i in data["items"])


# ── camere: exact sub 4, >= la 4+ ────────────────────────────────────────────
def test_feed_rooms_exact_sub_4(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        _mk(db, uid, "Două camere", rooms=2)
        _mk(db, uid, "Trei camere", rooms=3)
    finally:
        db.close()
    r = auth_client.get(_FEED, params={"rooms": 2})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert {i["title"] for i in data["items"]} == {"Două camere"}


def test_feed_rooms_4_plus(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        _mk(db, uid, "Trei", rooms=3)
        _mk(db, uid, "Patru", rooms=4)
        _mk(db, uid, "Cinci", rooms=5)
    finally:
        db.close()
    r = auth_client.get(_FEED, params={"rooms": 4})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2   # 4 și 5, nu 3
    assert {i["title"] for i in data["items"]} == {"Patru", "Cinci"}


# ── filter-options (distinct, scopat pe user, fără NULL, sortat) ──────────────
def test_filter_options_zones_distinct_scopate(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_im3z@example.com", username="other_im3z", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        _mk(db, uid, "A1", zone="Pipera")
        _mk(db, uid, "A2", zone="Pipera")     # duplicat -> DISTINCT
        _mk(db, uid, "A3", zone="Aviatiei")
        _mk(db, uid, "A4", zone=None)         # NULL -> exclus
        _mk(db, other.id, "B1", zone="Titan")  # alt user -> exclus
    finally:
        db.close()
    r = auth_client.get(_OPTIONS)
    assert r.status_code == 200, r.text
    assert r.json()["zones"] == ["Aviatiei", "Pipera"]   # sortate, distincte, fără NULL/Titan


def test_filter_options_cities_distinct(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_im3c@example.com", username="other_im3c", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        _mk(db, uid, "A1", city="București")
        _mk(db, uid, "A2", city="București")   # duplicat
        _mk(db, uid, "A3", city="Cluj-Napoca")
        _mk(db, other.id, "B1", city="Iași")   # alt user -> exclus
    finally:
        db.close()
    r = auth_client.get(_OPTIONS)
    assert r.status_code == 200, r.text
    assert r.json()["cities"] == ["București", "Cluj-Napoca"]   # sortate, distincte, fără Iași


# ── export aliniat cu filtrele vizibile ──────────────────────────────────────
def test_export_respecta_city_si_rooms(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        _mk(db, uid, "Buc 4cam", city="București", rooms=4)
        _mk(db, uid, "Buc 5cam", city="București", rooms=5)
        _mk(db, uid, "Buc 2cam", city="București", rooms=2)      # rooms < 4 -> exclus
        _mk(db, uid, "Cluj 4cam", city="Cluj-Napoca", rooms=4)   # alt oraș -> exclus
    finally:
        db.close()
    r = auth_client.get(_EXPORT, params={"city": "București", "rooms": 4})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 2
    assert set(titles) == {"Buc 4cam", "Buc 5cam"}


# ── stats: total doar active ─────────────────────────────────────────────────
def test_stats_total_doar_active(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        _mk(db, uid, "Activ", status="active")
        _mk(db, uid, "Ignorat", status="ignored")
    finally:
        db.close()
    r = auth_client.get(_STATS)
    assert r.status_code == 200, r.text
    assert r.json()["total_listings"] == 1
