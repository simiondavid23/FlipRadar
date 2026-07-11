"""IM-2 — feed Imobiliare: bulk-action + export pe selecție (param ids), scopate pe user.

Mirror pe testele AA-2/AA-5 (auto/radar): auth_client din conftest, listingurile se inserează
direct în DB (nu există API de creare — vin din scanner), conținutul xlsx se verifică cu openpyxl.
"""
from io import BytesIO

import openpyxl

from app.database import SessionLocal
from app.models.user import User
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing

_BULK = "/api/real-estate-monitor/feed/bulk-action"
_EXPORT = "/api/real-estate-monitor/feed/export"


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


def _mk(db, user_id, title="Garsonieră", status="active", platform="olx", price=350):
    row = RealEstateListing(user_id=user_id, platform=platform, title=title,
                            status=status, price=price, currency="EUR")
    db.add(row); db.commit(); db.refresh(row)
    return row.id


# ── bulk-action ────────────────────────────────────────────────────────────────
def test_bulk_saved_scopat_pe_user(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_im2@example.com", username="other_im2", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        a, b = _mk(db, uid, "A"), _mk(db, uid, "B")
        theirs = _mk(db, other.id, "Al altui user")
    finally:
        db.close()

    # trimit AMBII useri, dar filtrul pe user_id lasă doar ale mele să fie atinse
    r = auth_client.post(_BULK, json={"listing_ids": [a, b, theirs], "action": "saved"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    db = SessionLocal()
    try:
        mine = db.query(RealEstateListing).filter(RealEstateListing.id.in_([a, b])).all()
        assert {x.status for x in mine} == {"saved"}
        assert db.query(RealEstateListing).filter(RealEstateListing.id == theirs).first().status == "active"  # neatins
    finally:
        db.close()


def test_bulk_deleted_sterge_fizic(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        a, b = _mk(db, uid, "A"), _mk(db, uid, "B")
    finally:
        db.close()

    r = auth_client.post(_BULK, json={"listing_ids": [a, b], "action": "deleted"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    db = SessionLocal()
    try:
        assert db.query(RealEstateListing).filter(RealEstateListing.id.in_([a, b])).count() == 0
    finally:
        db.close()


def test_bulk_actiune_invalida_400(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        lid = _mk(db, uid)
    finally:
        db.close()
    r = auth_client.post(_BULK, json={"listing_ids": [lid], "action": "xxx"})
    assert r.status_code == 400


def test_bulk_ids_inexistente_updated_0(auth_client):
    _me_id(auth_client)  # asigură user autentificat
    r = auth_client.post(_BULK, json={"listing_ids": [999999, 888888], "action": "saved"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 0


# ── export pe selecție ───────────────────────────────────────────────────────────
def test_export_ids_doar_selectia(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        a = _mk(db, uid, "Garsonieră Militari")
        b = _mk(db, uid, "Apartament Tei")
        _mk(db, uid, "Studio Centru")   # al treilea, NEexportat
    finally:
        db.close()
    r = auth_client.get(_EXPORT, params={"ids": f"{a},{b}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 2
    assert set(titles) == {"Garsonieră Militari", "Apartament Tei"}


def test_export_ids_scopat_si_tolerant(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_im2exp@example.com", username="other_im2exp", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        mine = _mk(db, uid, "Al meu")
        theirs = _mk(db, other.id, "Al altui user")
    finally:
        db.close()
    # ids conține id-ul altui user + un token non-numeric ("abc") -> străinul lipsește, "abc" ignorat
    r = auth_client.get(_EXPORT, params={"ids": f"abc,{mine},{theirs}"})
    assert r.status_code == 200, r.text
    n, titles = _data_rows(r.content)
    assert n == 1
    assert titles == ["Al meu"]
    assert "Al altui user" not in titles
