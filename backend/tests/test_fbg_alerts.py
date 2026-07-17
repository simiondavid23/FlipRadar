"""FBG-1 — alerta de sesiune Facebook expirata + santinela pipeline-ului imobiliare.

Teste la nivel de serviciu (baza de test din conftest: SessionLocal + clean_db autouse),
fara retea — scraperul FB, decriptarea cookie-urilor si livrarea pe Discord sunt stubuite.

Tinta de monkeypatch difera dupa cum e facut importul in codul testat:
  - `send_system_alert` / `scrape_facebook_group` / `decrypt_cookies` sunt importate
    TOP-LEVEL in facebook_group_service -> se patch-uieste modulul CONSUMATOR (fbs);
  - `send_imob_notification` e importat LOCAL, in corpul lui _notify_re -> se
    patch-uieste modulul-SURSA (app.services.discord_service).
"""
import asyncio
from datetime import datetime

import app.services.facebook_group_service as fbs
from app.services.facebook_group_service import (
    _alert_webhook_for,
    _process_config,
    check_cookie_expiry,
)


def _user(db, email):
    from app.models.user import User

    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _settings(db, user_id, alerts=None, all_wh=None):
    from app.models.radar_settings import RadarSettings

    s = RadarSettings(user_id=user_id, discord_webhook_alerts=alerts,
                      discord_webhook_all=all_wh)
    db.add(s)
    db.flush()
    return s


def _config(db, user_id, name, status="ok"):
    from app.models.facebook_group_config import FacebookGroupConfig

    c = FacebookGroupConfig(user_id=user_id, group_name=name,
                            group_url="https://facebook.com/groups/test",
                            is_active=True, cookies_encrypted="x",
                            last_run_status=status)
    db.add(c)
    db.flush()
    return c


def _spy_discord(monkeypatch):
    """Inregistreaza (url, text) in loc sa atinga reteaua."""
    apeluri = []
    monkeypatch.setattr(fbs, "send_system_alert",
                        lambda url, text: apeluri.append((url, text)) or True)
    return apeluri


def _scraper_cu_cookies_expirate(monkeypatch):
    """decrypt_cookies neutralizat (Fernet ar crapa pe cookie-ul fals din fixture),
    scraperul ridica exact eroarea pe care _process_config o mapeaza la statusul
    "cookies_expirate"."""
    monkeypatch.setattr(fbs, "decrypt_cookies", lambda enc: [])

    async def _fail(**kwargs):
        raise Exception("COOKIES_EXPIRATE")

    monkeypatch.setattr(fbs, "scrape_facebook_group", _fail)


# ── Alerta la tranzitie (_process_config) ───────────────────────────────────────
def test_tranzitia_in_cookies_expirate_alerteaza(monkeypatch):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbg_tranzitie@example.com")
        _settings(db, user.id, alerts="https://discord.test/alerts")
        cfg = _config(db, user.id, "Chirii Bucuresti", status="ok")
        db.commit()
        spy = _spy_discord(monkeypatch)
        _scraper_cu_cookies_expirate(monkeypatch)

        asyncio.run(_process_config(db, cfg))

        db.refresh(cfg)
        assert cfg.last_run_status == "cookies_expirate"
        assert len(spy) == 1, f"asteptam exact o alerta, avem: {spy}"
        url, text = spy[0]
        assert url == "https://discord.test/alerts"
        assert "Chirii Bucuresti" in text
    finally:
        db.close()


def test_repetitia_nu_re_alerteaza(monkeypatch):
    # Alerta e la INTRAREA in stare: a doua rulare esuata consecutiv tace, iar
    # reminder-ul zilnic preia de acolo.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbg_repetitie@example.com")
        _settings(db, user.id, alerts="https://discord.test/alerts")
        cfg = _config(db, user.id, "Chirii Cluj", status="ok")
        db.commit()
        spy = _spy_discord(monkeypatch)
        _scraper_cu_cookies_expirate(monkeypatch)

        asyncio.run(_process_config(db, cfg))   # ok -> cookies_expirate : alerteaza
        asyncio.run(_process_config(db, cfg))   # cookies_expirate -> idem : tace

        db.refresh(cfg)
        assert cfg.last_run_status == "cookies_expirate"
        assert len(spy) == 1, f"repetitia a re-alertat: {spy}"
    finally:
        db.close()


# ── Reminder zilnic (check_cookie_expiry) ───────────────────────────────────────
def test_reminder_zilnic_un_mesaj_per_user_cu_toate_grupurile(monkeypatch):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbg_reminder@example.com")
        _settings(db, user.id, alerts="https://discord.test/alerts")
        _config(db, user.id, "Grup Expirat A", status="cookies_expirate")
        _config(db, user.id, "Grup Expirat B", status="cookies_expirate")
        _config(db, user.id, "Grup Sanatos", status="ok")
        db.commit()   # check_cookie_expiry isi deschide propria sesiune
        spy = _spy_discord(monkeypatch)

        check_cookie_expiry()

        assert len(spy) == 1, f"asteptam un singur mesaj per user, avem: {spy}"
        text = spy[0][1]
        assert "Grup Expirat A" in text
        assert "Grup Expirat B" in text
        assert "Grup Sanatos" not in text
    finally:
        db.close()


# ── Rezolvarea webhook-ului (_alert_webhook_for) ────────────────────────────────
def test_webhook_fallback_pe_all_cand_alerts_e_gol():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbg_fallback@example.com")
        _settings(db, user.id, alerts=None, all_wh="https://discord.test/all")
        db.commit()
        assert _alert_webhook_for(db, user.id) == "https://discord.test/all"
    finally:
        db.close()


def test_fara_webhook_ramane_doar_pe_live_logs(monkeypatch):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbg_fara_webhook@example.com")
        _settings(db, user.id, alerts=None, all_wh=None)
        _config(db, user.id, "Grup Expirat", status="cookies_expirate")
        fara_settings = _user(db, "fbg_fara_settings@example.com")
        db.commit()

        assert _alert_webhook_for(db, user.id) is None
        assert _alert_webhook_for(db, fara_settings.id) is None   # user fara rand RadarSettings

        spy = _spy_discord(monkeypatch)
        check_cookie_expiry()          # fara webhook nu trebuie sa crape
        assert spy == []
    finally:
        db.close()


# ── Santinela: postarile FB Groups -> Discord imobiliare ────────────────────────
def test_santinela_postarile_fb_groups_intra_in_discordul_imobiliare(monkeypatch):
    """Fixeaza ca postarile FB Groups intra in pipeline-ul Discord imobiliare existent
    — daca cineva rupe lantul _save_fb_group_post -> _notify_re -> send_imob_notification,
    testul pica."""
    from app.database import SessionLocal
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword
    import app.services.real_estate_scanner as re_scanner
    from app.services.real_estate_scanner import _notify_re, _save_fb_group_post

    db = SessionLocal()
    try:
        user = _user(db, "fbg_santinela@example.com")
        settings = _settings(db, user.id, alerts="https://discord.test/alerts")
        kw = RealEstateMonitorKeyword(user_id=user.id, name="kw fb", city="București",
                                      platform="facebook_groups", is_active=True,
                                      notify_discord=True)
        db.add(kw)
        db.commit()

        trimise = []
        monkeypatch.setattr("app.services.discord_service.send_imob_notification",
                            lambda *a, **k: trimise.append(a))
        # _notify_re inghite exceptiile si le logheaza — capturam log-ul ca esecul
        # santinelei sa fie citibil, nu doar "spy neapelat".
        loguri = []
        monkeypatch.setattr(re_scanner.log_manager, "emit",
                            lambda mod, lvl, msg: loguri.append(f"{lvl}: {msg}"))

        post = {"id": 4242, "text": "Inchiriez garsoniera in Militari, 350 euro, 40 mp",
                "group_url": "https://facebook.com/groups/chirii/posts/4242",
                "created_at": datetime(2026, 7, 17, 9, 0)}
        saved = _save_fb_group_post(db, post, kw, False, {})
        assert saved is not None, "postarea nu s-a salvat — lantul se rupe inainte de _notify_re"
        assert saved.platform == "facebook_groups"

        _notify_re(saved, kw, settings, db)

        assert len(trimise) == 1, f"lantul spre Discord imobiliare e rupt; log: {loguri}"
    finally:
        db.close()
