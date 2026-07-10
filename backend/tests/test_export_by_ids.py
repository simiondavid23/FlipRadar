"""AA-5 — export .xlsx pe selectie (param ids), scopat pe user, in AMBELE routere.

Inchide bugul Radar: ids era ignorat de backend -> radar_selectie_*.xlsx continea tot feedul.
auth_client din conftest; continutul se verifica incarcand blob-ul cu openpyxl din memorie.
"""
from io import BytesIO

import openpyxl

from app.database import SessionLocal
from app.models.user import User
from app.models.auto_feed_listing import AutoFeedListing
from app.models.radar_listing import RadarListing

_AUTO_EXPORT = "/api/auto-listings/feed/export"
_RADAR_EXPORT = "/api/radar/listings/export"


def _me_id(auth_client) -> int:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _data_rows(blob: bytes):
    """(count, titluri) — randuri de date fara header; col 1 = Titlu in ambele exportere."""
    ws = openpyxl.load_workbook(BytesIO(blob)).active
    titles = [row[0] for row in ws.iter_rows(min_row=2, values_only=True)
              if row and any(v not in (None, "") for v in row)]
    return len(titles), titles


def _mk_auto(db, user_id, title, status="active"):
    row = AutoFeedListing(user_id=user_id, platform="olx_auto", title=title, price=1000, status=status)
    db.add(row); db.commit(); db.refresh(row)
    return row.id


def _radar_keyword(auth_client) -> int:
    payload = {"name": "export test", "max_price": 5000, "resale_price": 6000,
               "platform": "olx", "platforms": ["olx"]}
    r = auth_client.post("/api/radar/keywords", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_radar(db, user_id, keyword_id, external_id, title):
    row = RadarListing(user_id=user_id, keyword_id=keyword_id, external_id=external_id,
                       platform="olx", title=title, price=1234.0, url=f"https://olx.ro/{external_id}")
    db.add(row); db.commit(); db.refresh(row)
    return row.id


# ── Auto ──────────────────────────────────────────────────────────────────────────
def test_auto_export_ids_doua_din_trei(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        a = _mk_auto(db, uid, "Audi A4")
        b = _mk_auto(db, uid, "BMW 320")
        _mk_auto(db, uid, "VW Golf")          # al treilea, NEexportat
    finally:
        db.close()
    r = auth_client.get(_AUTO_EXPORT, params={"ids": f"{a},{b}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 2
    assert set(titles) == {"Audi A4", "BMW 320"}


def test_auto_export_izolare_user(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_aa5@example.com", username="other_aa5", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        mine = _mk_auto(db, uid, "Al meu")
        theirs = _mk_auto(db, other.id, "Al altui user")
    finally:
        db.close()
    # cer AMBELE id-uri, dar filtrul pe user lasa doar al meu (intersectia)
    r = auth_client.get(_AUTO_EXPORT, params={"ids": f"{mine},{theirs}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 1
    assert titles == ["Al meu"]
    assert "Al altui user" not in titles


def test_auto_export_ids_parse_tolerant(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        keep = _mk_auto(db, uid, "Pastrat")
        _mk_auto(db, uid, "Ignorat")
    finally:
        db.close()
    # "abc" + tokenul gol -> ignorate; doar id-ul valid ramane
    r = auth_client.get(_AUTO_EXPORT, params={"ids": f"abc, ,{keep}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 1
    assert titles == ["Pastrat"]


def test_auto_export_fara_ids_tot_feedul(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        for t in ("Unu", "Doi", "Trei"):
            _mk_auto(db, uid, t)
    finally:
        db.close()
    r = auth_client.get(_AUTO_EXPORT)          # fara ids -> comportamentul vechi
    assert r.status_code == 200, r.text
    n, _ = _data_rows(r.content)
    assert n == 3


# ── Radar (bugul inchis) ────────────────────────────────────────────────────────────
def test_radar_export_ids_doua_din_trei(auth_client):
    uid = _me_id(auth_client)
    kid = _radar_keyword(auth_client)
    db = SessionLocal()
    try:
        a = _mk_radar(db, uid, kid, "r1", "Radar A")
        b = _mk_radar(db, uid, kid, "r2", "Radar B")
        _mk_radar(db, uid, kid, "r3", "Radar C")   # neexportat
    finally:
        db.close()
    r = auth_client.get(_RADAR_EXPORT, params={"ids": f"{a},{b}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 2                               # inainte de fix: 3 (tot feedul, ids ignorat)
    assert set(titles) == {"Radar A", "Radar B"}
