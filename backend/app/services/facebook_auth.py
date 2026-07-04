"""Re-autentificare automată Facebook când sesiunea expiră.
Folosește credențialele din variabilele de mediu FACEBOOK_EMAIL și FACEBOOK_PASSWORD.

Playwright e folosit DOAR aici (login headless automat) — calea de căutare
(facebook_scraper.search_facebook) nu mai importă Playwright, merge pe curl_cffi.
"""
import os
import time
from pathlib import Path
from typing import Optional

from app.services.log_manager import log_manager

_reauth_lock = {"in_progress": False}


def needs_reauth(results: list, session_path: Optional[str]) -> bool:
    """Sesiunea a expirat dacă scraperul returnează 0 rezultate ȘI storage_state-ul
    real (`session_path`) există dar e vechi (> 23h).

    Conservator: nu re-auth la fiecare 0 rezultate (keyword prea specific etc.),
    ci doar dacă fișierul de sesiune e probabil expirat.

    IMPORTANT (fix cale): `session_path` e pasat EXPLICIT de apelant — este
    exact fișierul folosit de search_facebook (RadarSettings.facebook_session_path).
    Înainte exista o constantă globală hardcodată `Path("facebook_storage_state.json")`,
    complet diferită de sesiunea reală, deci verificarea de vârstă se făcea pe un
    fișier inexistent și re-auth-ul nu se declanșa niciodată corect.
    """
    if results:
        return False
    if not session_path:
        return False
    p = Path(session_path)
    if not p.exists():
        return False
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    return age_hours > 23  # Sesiunea e probabil expirată


def re_authenticate(session_path: Optional[str]) -> bool:
    """Re-autentifică pe Facebook și salvează storage_state-ul ÎN `session_path`.

    Returnează True la succes. Thread-safe: nu rulează concurent dacă un re-auth
    e deja în curs.

    `session_path` (pasat explicit) e citit/scris atât pentru target-ul de salvare
    cât și de `needs_reauth` — nu mai există cale hardcodată. Login automat cu
    FACEBOOK_EMAIL / FACEBOOK_PASSWORD (strategie neschimbată).

    Dacă apare checkpoint / 2FA la login-ul automat, funcția loghează eroare clară
    și întoarce False (comportament păstrat intenționat — un login automat headless
    nu poate trece de 2FA; utilizatorul trebuie să refacă login-ul manual).
    """
    if not session_path:
        log_manager.emit("radar", "ERR",
            "Facebook re-auth imposibil: session_path lipsește.")
        return False

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

        storage_path = Path(session_path)
        # Asigură directorul țintă (ex. .../backend/data/) înainte de scriere.
        if storage_path.parent and not storage_path.parent.exists():
            storage_path.parent.mkdir(parents=True, exist_ok=True)

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

            context.storage_state(path=str(storage_path))
            browser.close()
            log_manager.emit("radar", "OK",
                f"Facebook re-autentificare reușită. Sesiune nouă salvată în {storage_path}.")
            return True
    except Exception as exc:
        log_manager.emit("radar", "ERR", f"Facebook re-auth eroare: {str(exc)[:120]}")
        return False
    finally:
        _reauth_lock["in_progress"] = False
