"""Detectia sesiunii Facebook expirate (Radar Marketplace).

R5 — login-ul automat headless A FOST ELIMINAT DELIBERAT. `re_authenticate` deschidea
un chromium simplu (fara stealth, fara masca) si se autentifica cu FACEBOOK_EMAIL /
FACEBOOK_PASSWORD din .env: exact profilul care atrage checkpoint pe Facebook, iar un
checkpoint declansat asa poate bloca si sesiunile MANUALE ulterioare ale contului —
adica exact contul de scanare. In plus tinea parola in clar in .env. NU-l readuce:
cand sesiunea moare, semnalizam (WARN + raport BLOCKED la health_watchdog) si
utilizatorul reface login-ul MANUAL din Setari Radar -> Facebook
(services/radar/facebook_auth.py, browser real, cu masca).

Aici a ramas doar detectia — pura, fara retea si fara browser.
"""
import time
from pathlib import Path
from typing import Optional


def session_probably_expired(results: list, session_path: Optional[str]) -> bool:
    """True daca sesiunea pare moarta: scan cu 0 rezultate SI storage_state-ul real
    (`session_path`) exista dar e vechi (> 23h).

    Semnal, nu actiune: apelantul doar avertizeaza (R5 a scos login-ul automat).
    Conservator din acelasi motiv ca inainte — 0 rezultate se intampla si legitim
    (keyword prea specific), deci cerem si fisierul de sesiune probabil expirat, ca
    sa nu alarmam degeaba.

    `session_path` e pasat EXPLICIT de apelant — este exact fisierul folosit de
    search_facebook (RadarSettings.facebook_session_path). Inainte exista o constanta
    globala hardcodata `Path("facebook_storage_state.json")`, complet diferita de
    sesiunea reala, deci verificarea de varsta se facea pe un fisier inexistent.
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
