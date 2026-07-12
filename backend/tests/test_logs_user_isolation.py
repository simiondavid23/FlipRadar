"""MON-4 — Jurnale Live izolate per user (contextvars).

Unit pe set_log_user/reset_log_user + izolare/system prin stats (auth_client + emit
direct, ca in test_alerts_rearm). Stats se citeste ca delta before/after fiindca
buffer-ul log_manager e un singleton in-memory partajat intre teste (nu-l curata clean_db).
"""


def test_set_reset_log_user_ataseaza_user_id():
    from app.services.log_manager import log_manager, set_log_user, reset_log_user

    token = set_log_user(7)
    try:
        log_manager.emit("radar", "INFO", "mesaj user 7")
        assert log_manager.buffers["radar"][-1]["user_id"] == 7
    finally:
        reset_log_user(token)
    log_manager.emit("radar", "INFO", "mesaj system")
    assert log_manager.buffers["radar"][-1]["user_id"] is None


def _user_id():
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        return db.query(User).first().id
    finally:
        db.close()


def _radar_new_hour(auth_client):
    r = auth_client.get("/api/logs/stats")
    assert r.status_code == 200, r.text
    return r.json()["radar"]["new_hour"]


def test_stats_izolate_pe_user(auth_client):
    from app.services.log_manager import log_manager, set_log_user

    a_id = _user_id()          # userul auth_client (are sesiune)
    other_id = a_id + 4242     # alt user, fara sesiune aici

    before = _radar_new_hour(auth_client)
    # 1 OK pentru A, 2 OK pentru alt user, pe acelasi modul
    set_log_user(a_id)
    log_manager.emit("radar", "OK", "al lui A")
    set_log_user(other_id)
    log_manager.emit("radar", "OK", "al altcuiva 1")
    log_manager.emit("radar", "OK", "al altcuiva 2")
    set_log_user(None)

    after = _radar_new_hour(auth_client)
    # A vede DOAR emit-ul lui (+1), NU si cele 2 ale altui user.
    assert after == before + 1


def test_emit_fara_context_nu_apare_in_stats(auth_client):
    from app.services.log_manager import log_manager, set_log_user

    def catalog_new_hour():
        r = auth_client.get("/api/logs/stats")
        assert r.status_code == 200, r.text
        return r.json()["catalog"]["new_hour"]

    set_log_user(None)  # fara context = system
    before = catalog_new_hour()
    log_manager.emit("catalog", "OK", "system, fara user")  # user_id=None
    after = catalog_new_hour()
    # Emit-ul system (user_id None) NU se potriveste cu niciun user -> nu apare.
    assert after == before
