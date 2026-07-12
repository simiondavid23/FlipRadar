"""MON-3 — POST /api/logs/test-emit e doar pentru admini.

is_admin nu e setabil prin API; il setam direct in DB pe userul creat de
auth_client (acelasi pattern ca in test_alerts_rearm).
"""


def _set_admin(is_admin=True):
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).first()
        user.is_admin = is_admin
        db.commit()
    finally:
        db.close()


def test_test_emit_user_normal_403(auth_client):
    # user proaspat -> is_admin False implicit -> acces interzis
    r = auth_client.post("/api/logs/test-emit")
    assert r.status_code == 403


def test_test_emit_admin_200_cu_buffere(auth_client):
    # get_current_user reciteste userul din DB, deci setarea is_admin=True e vazuta.
    _set_admin(True)
    r = auth_client.post("/api/logs/test-emit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "buffer_sizes" in body
    assert isinstance(body["buffer_sizes"], dict) and len(body["buffer_sizes"]) > 0
