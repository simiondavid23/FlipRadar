"""Re-autentificare automată Facebook când sesiunea expiră.
Folosește credențialele din variabilele de mediu FACEBOOK_EMAIL și FACEBOOK_PASSWORD.
"""
import os
import time
from pathlib import Path
from app.services.log_manager import log_manager

STORAGE_STATE_PATH = Path("facebook_storage_state.json")
_reauth_lock = {"in_progress": False}


def needs_reauth(results: list) -> bool:
    """Sesiunea a expirat dacă scraperul returnează 0 rezultate
    și nu există o altă cauză evidentă (keyword prea specific etc.).
    Conservator: nu re-auth la fiecare 0 rezultate, ci doar dacă
    storage_state există dar e vechi (> 24h).
    """
    if results:
        return False
    if not STORAGE_STATE_PATH.exists():
        return False
    age_hours = (time.time() - STORAGE_STATE_PATH.stat().st_mtime) / 3600
    return age_hours > 23  # Sesiunea e probabil expirată


def re_authenticate() -> bool:
    """Re-autentifică pe Facebook. Returnează True la succes.
    Thread-safe: nu rulează concurent dacă un re-auth e deja în curs.
    """
    if _reauth_lock["in_progress"]:
        log_manager.emit("radar", "WARN", "Facebook re-auth deja în curs, skip.")
        return False

    email = os.getenv("FACEBOOK_EMAIL")
    password = os.getenv("FACEBOOK_PASSWORD")
    if not email or not password:
        log_manager.emit("radar", "ERR",
            "Facebook re-auth imposibil: FACEBOOK_EMAIL sau FACEBOOK_PASSWORD lipsesc din .env")
        return False

    _reauth_lock["in_progress"] = True
    try:
        from playwright.sync_api import sync_playwright
        log_manager.emit("radar", "INFO", "Facebook: încearcă re-autentificare...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.facebook.com/login", timeout=30_000)
            page.fill("#email", email)
            page.fill("#pass", password)
            page.click("[name='login']")
            page.wait_for_timeout(5_000)

            if "login" in page.url or "checkpoint" in page.url:
                log_manager.emit("radar", "ERR",
                    "Facebook re-auth eșuat: login invalid sau checkpoint de securitate.")
                browser.close()
                return False

            context.storage_state(path=str(STORAGE_STATE_PATH))
            browser.close()
            log_manager.emit("radar", "OK",
                "Facebook re-autentificare reușită. Sesiune nouă salvată.")
            return True
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"Facebook re-auth eroare: {str(exc)[:120]}")
        return False
    finally:
        _reauth_lock["in_progress"] = False
