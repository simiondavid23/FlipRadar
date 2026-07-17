"""FB-LOGIN — contractul HTTP al fluxului Conecteaza Facebook.

Fluxul de browser (Playwright) NU se testeaza aici — sub FLIPRADAR_TESTING
(setat de conftest) endpointul /connect nu porneste niciun thread/browser, deci
testam doar contractul. /status il verificam pe un fisier de sesiune fabricat.
"""


def test_facebook_connect_returns_connecting(auth_client):
    # Guard-ul FLIPRADAR_TESTING garanteaza ca niciun thread/browser nu porneste.
    r = auth_client.post("/api/radar/facebook/connect")
    assert r.status_code == 200
    assert r.json()["status"] == "connecting"


def test_facebook_status_active_then_expired(auth_client, tmp_path):
    import json
    import os
    import time
    from app.database import SessionLocal
    from app.models.user import User
    from app.models.radar_settings import RadarSettings

    sess_file = tmp_path / "fb_session.json"
    sess_file.write_text(
        json.dumps({"cookies": [{"name": "c_user", "value": "1"}]}),
        encoding="utf-8",
    )

    # Legam fisierul de sesiune de userul de test (cel mai recent inregistrat = auth_client).
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id.desc()).first()
        s = db.query(RadarSettings).filter(RadarSettings.user_id == user.id).first()
        if s is None:
            s = RadarSettings(user_id=user.id)
            db.add(s)
        s.facebook_session_path = str(sess_file)
        db.commit()
    finally:
        db.close()

    # Fisier proaspat cu c_user -> activ, varsta sub 1h.
    r = auth_client.get("/api/radar/facebook/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["age_hours"] is not None and body["age_hours"] < 1

    # Imbatranit la ~40 de zile (peste pragul de 30) -> expirat.
    old = time.time() - 40 * 24 * 3600
    os.utime(str(sess_file), (old, old))
    r2 = auth_client.get("/api/radar/facebook/status")
    assert r2.status_code == 200
    assert r2.json()["status"] == "expired"
