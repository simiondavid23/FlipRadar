"""Login interactiv pentru Facebook Marketplace.

Deschide un browser vizibil — Chrome-ul real al utilizatorului daca exista
(zero download, login mai natural pentru Facebook), cu fallback pe Chromium-ul
Playwright. Asteapta pana la LOGIN_TIMEOUT_S (240s) ca utilizatorul sa se
logheze manual (inclusiv 2FA prin SMS / captcha). Storage_state-ul Playwright
(cookies + localStorage) se salveaza DOAR daca login-ul s-a finalizat, ca un
Reconecteaza abandonat sa nu suprascrie o sesiune valida cu una anonima.
"""
import json
import os
import time
from typing import Optional

LOGIN_TIMEOUT_S = 240  # era 120 — strans pentru 2FA prin SMS + captcha


def start_facebook_login_session(session_path: str) -> bool:
    """Pornește un browser vizibil (Chrome real cu fallback Chromium) si asteapta
    login manual pana la LOGIN_TIMEOUT_S.

    Returneaza True doar daca apare cookie-ul c_user (login finalizat); in acel
    caz — si NUMAI atunci — scrie storage_state in session_path. La timeout /
    fereastra inchisa / login nefinalizat NU atinge fisierul (sesiunea existenta
    ramane neatinsa).
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
            # Chrome-ul real al utilizatorului = zero download + login mai natural
            # pentru Facebook; fallback pe Chromium Playwright pastreaza functionarea.
            try:
                browser = p.chromium.launch(headless=False, channel="chrome")
                print("[FacebookAuth] Folosesc Chrome-ul instalat al utilizatorului.")
            except Exception:
                browser = p.chromium.launch(headless=False)
                print("[FacebookAuth] Chrome indisponibil — fallback pe Chromium Playwright.")
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
            except Exception as exc:
                print(f"[FacebookAuth] Nu am putut deschide facebook.com: {exc}")

            print(f"[FacebookAuth] Asteapta pana la {LOGIN_TIMEOUT_S}s pentru login manual...")
            # Polling pentru cookie c_user — daca apare mai devreme, iesim si salvam
            # imediat. Daca utilizatorul INCHIDE fereastra, context.cookies() arunca
            # -> prins de try-ul mare de mai jos -> return False FARA scriere
            # (intentionat: nu suprascriem o sesiune valida existenta).
            deadline = time.time() + LOGIN_TIMEOUT_S
            success = False
            while time.time() < deadline:
                cookies = context.cookies()
                if any(c.get("name") == "c_user" for c in cookies):
                    success = True
                    break
                time.sleep(2)

            # BUG FIX: scriem storage_state DOAR la login reusit. Altfel un storage
            # anonim (Reconecteaza abandonat / timeout) suprascria sesiunea valida.
            if success:
                storage = context.storage_state()
                try:
                    with open(session_path, "w", encoding="utf-8") as f:
                        json.dump(storage, f, ensure_ascii=False)
                    print(f"[FacebookAuth] Sesiune salvata in {session_path}")
                except Exception as exc:
                    print(f"[FacebookAuth] Eroare la salvare sesiune: {exc}")
                    success = False
            else:
                print("[FacebookAuth] Login nefinalizat — sesiunea existenta ramane neatinsa.")

            try:
                context.close()
                browser.close()
            except Exception:
                pass

            return success
    except Exception as exc:
        print(f"[FacebookAuth] Eroare la login: {exc}")
        return False
