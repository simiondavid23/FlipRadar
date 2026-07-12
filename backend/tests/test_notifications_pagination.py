"""MON-2 — paginare GET /api/notifications/ (skip/limit, default 50, max 100).

Insert direct in DB + acces la userul creat de auth_client (ca in test_alerts_rearm).
Controlam created_at ca ordinea desc sa fie deterministica (n6 cea mai noua).
"""
from datetime import datetime, timedelta


def _user_id():
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        return db.query(User).first().id
    finally:
        db.close()


def _seed(user_id, n=7):
    from app.database import SessionLocal
    from app.models.notification import Notification

    base = datetime(2026, 1, 1, 0, 0, 0)
    db = SessionLocal()
    try:
        for i in range(n):
            db.add(Notification(
                user_id=user_id,
                title=f"n{i}",
                message="m",
                notification_type="info",
                created_at=base + timedelta(minutes=i),
            ))
        db.commit()
    finally:
        db.close()


def test_paginare_skip_limit(auth_client):
    uid = _user_id()
    _seed(uid, 7)

    r = auth_client.get("/api/notifications/", params={"limit": 3})
    assert r.status_code == 200, r.text
    assert [x["title"] for x in r.json()] == ["n6", "n5", "n4"]  # cele mai noi 3, desc

    r = auth_client.get("/api/notifications/", params={"skip": 3, "limit": 3})
    assert r.status_code == 200, r.text
    assert [x["title"] for x in r.json()] == ["n3", "n2", "n1"]

    r = auth_client.get("/api/notifications/", params={"skip": 6, "limit": 3})
    assert r.status_code == 200, r.text
    assert [x["title"] for x in r.json()] == ["n0"]


def test_fara_parametri_toate_7_desc(auth_client):
    uid = _user_id()
    _seed(uid, 7)

    r = auth_client.get("/api/notifications/")
    assert r.status_code == 200, r.text
    assert [x["title"] for x in r.json()] == ["n6", "n5", "n4", "n3", "n2", "n1", "n0"]


def test_limit_peste_100_da_422(auth_client):
    r = auth_client.get("/api/notifications/", params={"limit": 101})
    assert r.status_code == 422
