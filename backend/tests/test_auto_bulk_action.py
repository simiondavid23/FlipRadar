"""AA-2 — endpoint bulk-action pentru feed-ul Auto (POST /api/auto-listings/feed/bulk-action).

Scopat pe user (mirror pe radar.py::bulk_listing_action). Foloseste fixture-ul auth_client
din conftest; listingurile se insereaza direct in DB (nu exista API de creare — vin din scanner).
"""
from app.database import SessionLocal
from app.models.user import User
from app.models.auto_feed_listing import AutoFeedListing

_URL = "/api/auto-listings/feed/bulk-action"


def _me_id(auth_client) -> int:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk(db, user_id, status="active", platform="olx_auto", title="Test auto"):
    row = AutoFeedListing(user_id=user_id, platform=platform, title=title, status=status)
    db.add(row); db.commit(); db.refresh(row)
    return row.id


def test_bulk_saved_updates_two(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        id1, id2 = _mk(db, uid), _mk(db, uid)
    finally:
        db.close()

    r = auth_client.post(_URL, json={"listing_ids": [id1, id2], "action": "saved"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2
    assert r.json()["action"] == "saved"

    db = SessionLocal()
    try:
        rows = db.query(AutoFeedListing).filter(AutoFeedListing.id.in_([id1, id2])).all()
        assert {x.status for x in rows} == {"saved"}
    finally:
        db.close()


def test_bulk_deleted_removes_rows(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        id1, id2 = _mk(db, uid), _mk(db, uid)
    finally:
        db.close()

    r = auth_client.post(_URL, json={"listing_ids": [id1, id2], "action": "deleted"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    db = SessionLocal()
    try:
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id.in_([id1, id2])).count() == 0
    finally:
        db.close()


def test_invalid_action_400(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        lid = _mk(db, uid)
    finally:
        db.close()
    r = auth_client.post(_URL, json={"listing_ids": [lid], "action": "foo"})
    assert r.status_code == 400


def test_empty_ids_zero_updated(auth_client):
    r = auth_client.post(_URL, json={"listing_ids": [], "action": "saved"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 0


def test_user_isolation(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        # Al doilea user + listingul lui — NU trebuie atins de userul curent.
        other = User(email="other_aa2@example.com", username="other_aa2", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        mine = _mk(db, uid)
        theirs = _mk(db, other.id)
    finally:
        db.close()

    # Trimit AMBELE ID-uri, dar filtrarea pe user_id lasa doar al meu sa fie atins.
    r = auth_client.post(_URL, json={"listing_ids": [mine, theirs], "action": "ignored"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1  # doar al userului curent

    db = SessionLocal()
    try:
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id == mine).first().status == "ignored"
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id == theirs).first().status == "active"  # neatins
    finally:
        db.close()


def test_active_moves_back_from_saved(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        lid = _mk(db, uid, status="saved")
    finally:
        db.close()

    r = auth_client.post(_URL, json={"listing_ids": [lid], "action": "active"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1

    db = SessionLocal()
    try:
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id == lid).first().status == "active"
    finally:
        db.close()
