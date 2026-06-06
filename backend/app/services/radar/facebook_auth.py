"""Login interactiv pentru Facebook Marketplace.

Deschide Chromium-ul vizibil, asteapta 120s ca utilizatorul sa se logheze
manual (inclusiv 2FA daca e cazul), apoi salveaza storage_state-ul Playwright
in fisierul indicat. Storage state include cookies + localStorage, suficient
pentru ca search_facebook sa restaureze sesiunea ulterior.
"""
import json
import os
import time
from typing import Optional


def start_facebook_login_session(session_path: str) -> bool:
    """Pornește browser-ul vizibil si asteapta login manual.

    Returneaza True doar daca dupa cele 120s exista cookie-ul c_user
    (semn ca login-ul s-a finalizat).
    """
    if not session_path:
        print("[FacebookAuth] session_path lipseste.")
        return False

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FacebookAuth] Playwright nu e instalat — instalati `playwright install chromium`.")
        return False

    # Asigura directorul tinta
    os.makedirs(os.path.dirname(session_path), exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
            except Exception as exc:
                print(f"[FacebookAuth] Nu am putut deschide facebook.com: {exc}")

            print("[FacebookAuth] Asteapta 120s pentru login manual...")
            # Polling pentru cookie c_user — daca apare mai devreme,
            # iesim si salvam imediat ca sa nu tinem browser-ul deschis
            # mai mult decat e nevoie.
            deadline = time.time() + 120
            success = False
            while time.time() < deadline:
                cookies = context.cookies()
                if any(c.get("name") == "c_user" for c in cookies):
                    success = True
                    break
                time.sleep(2)

            storage = context.storage_state()
            try:
                with open(session_path, "w", encoding="utf-8") as f:
                    json.dump(storage, f, ensure_ascii=False)
                print(f"[FacebookAuth] Sesiune salvata in {session_path}")
            except Exception as exc:
                print(f"[FacebookAuth] Eroare la salvare sesiune: {exc}")
                success = False

            try:
                context.close()
                browser.close()
            except Exception:
                pass

            return success
    except Exception as exc:
        print(f"[FacebookAuth] Eroare la login: {exc}")
        return False
