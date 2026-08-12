"""R3 + R5 (audit FB) — semnalizarea sesiunii moarte in Radar Piata.

R3: login wall servit pe 200, fara redirect.
R5: login-ul automat a fost ELIMINAT; cand sesiunea pare moarta doar semnalizam.


Detectia de sesiune moarta din search_facebook se uita DOAR la final_url ("login"/
"checkpoint"). Facebook serveste insa frecvent 200 pe URL-ul ORIGINAL, cu formularul
de login in corpul paginii: _iter_listing_objects gaseste 0 obiecte si scraperul
raporteaza "0 rezultate" cu status OK. Plasa session_probably_expired cere fisier de
sesiune mai vechi de 23h, deci o sesiune invalidata la 2h dupa login producea ZILE de
zero-uri tacute.

Fix: cand nu exista NICIUN obiect de listare, verificam HTML-ul cu
_looks_like_login_wall (mutat aici din facebook_real_estate, FBM-1f) — WARN + raport
BLOCKED catre watchdog, exact ca pe ramura de redirect. Fara obiecte de listare =
0 rezultate legitime raman legitime.

Rotatia de IP NU se declanseaza pentru Facebook: platforma nu e in
MODEM_ROUTED_PLATFORMS (.env / .env.example), iar cookie-ul FB vazut de pe alt IP
inseamna checkpoint (NET-5). Testele de mai jos pinuiesc si asta.
"""
import pytest

from app.services.radar import facebook_scraper as fb
from app.services.radar.base_scraper import Outcome


_HTML_LOGIN_WALL = """
<html><body><form id="royal_login_form" action="/login/?next=x" method="post">
<input name="email"><input type="password" name="pass"></form></body></html>
"""

_HTML_ZERO_LEGITIM = """
<html><body><div role="main">Nu am gasit rezultate pentru cautarea ta.
<form action="/search/" method="get"><input name="q"></form></div></body></html>
"""


def _run(monkeypatch, html: str, obiecte: list, final_url: str = "https://www.facebook.com/marketplace/search/"):
    """Ruleaza search_facebook REAL cu sesiunea/fetch-ul/iterarea JSON stubuite.

    Intoarce (rezultate, logs, blocked, expired_calls):
      logs          = [(nivel, mesaj)] emise de scraper
      blocked       = [(platforma, outcome)] raportate prin report_outcome
      expired_calls = argumentele cu care s-a consultat session_probably_expired
                      (mecanismul existent de sesiune moarta) — ca sa vedem ca
                      login-wall-ul NU inventeaza alta cale
    """
    import app.services.facebook_auth as fauth

    logs, blocked, reauth_calls = [], [], []
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fb, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fb, "_fetch", lambda url, cookies: (html, final_url))
    monkeypatch.setattr(fb, "_iter_listing_objects", lambda h: list(obiecte))
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)))
    monkeypatch.setattr(fb, "report_outcome",
                        lambda platform, outcome: (blocked.append((platform, outcome)), False)[1])
    monkeypatch.setattr(fauth, "session_probably_expired",
                        lambda results, path: (reauth_calls.append((list(results), path)), False)[1])

    out = fb.search_facebook(keyword="iphone", max_price=5000,
                             session_path="sesiune.json")
    return out, logs, blocked, reauth_calls


def _fb_obj(oid: str, title: str, amount="1000.00") -> dict:
    return {
        "id": oid,
        "marketplace_listing_title": title,
        "listing_price": {"amount": amount, "formatted_amount": f"RON{amount}"},
    }


# ── login wall servit pe 200 ─────────────────────────────────────────────────────

def test_login_wall_fara_redirect_e_semnalat_ca_sesiune_moarta(monkeypatch):
    """TINTA R3: 0 obiecte + HTML de login => WARN, nu "0 rezultate OK" tacut."""
    out, logs, blocked, reauth_calls = _run(monkeypatch, _HTML_LOGIN_WALL, [])

    assert out == []
    warns = [m for lvl, m in logs if lvl == "WARN"]
    assert len(warns) == 1
    assert "login" in warns[0].lower() and "sesiune" in warns[0].lower()
    # Acelasi mecanism ca pe ramura de redirect: semnalul de sesiune moarta
    # (session_probably_expired) e consultat cu lista goala.
    assert reauth_calls == [([], "sesiune.json")]


def test_login_wall_raporteaza_blocked_la_watchdog(monkeypatch):
    _, _, blocked, _ = _run(monkeypatch, _HTML_LOGIN_WALL, [])
    assert blocked == [("facebook", Outcome.BLOCKED)]


# ── control negativ: 0 rezultate legitime raman legitime ─────────────────────────

def test_zero_rezultate_legitime_nu_declanseaza_nimic(monkeypatch):
    out, logs, blocked, _ = _run(monkeypatch, _HTML_ZERO_LEGITIM, [])
    assert out == []
    assert [m for lvl, m in logs if lvl == "WARN"] == []
    assert blocked == []


def test_detectorul_nu_se_apeleaza_cand_exista_obiecte(monkeypatch):
    # Cost inutil pe calea buna: cu obiecte de listare, HTML-ul nu se mai scaneaza.
    apeluri = []
    monkeypatch.setattr(fb, "_looks_like_login_wall",
                        lambda h: (apeluri.append(h), True)[1])
    out, logs, blocked, _ = _run(monkeypatch, _HTML_LOGIN_WALL,
                                 [_fb_obj("1", "iPhone 13 128GB")])
    assert len(out) == 1
    assert apeluri == []                 # nici macar o data
    assert blocked == []


# ── watchdog: se numara blocajul, dar NU se roteste IP-ul ────────────────────────

def test_report_outcome_ajunge_la_note_blocked_fara_rotatie(monkeypatch):
    """Cablarea reala (fara stub pe report_outcome): note_blocked primeste
    platforma, iar rotatorul nu e atins nici macar o data."""
    from app.services.network import triggers
    from app.services.radar import base_scraper, health_watchdog

    notate, rotatoare = [], []
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "mobilede,vinted,autovit,okazii,publi24,lajumate")
    monkeypatch.setattr(health_watchdog, "note_blocked", lambda p: notate.append(p))
    monkeypatch.setattr(triggers, "get_rotator", lambda: rotatoare.append("atins"))

    can_retry = base_scraper.report_outcome("facebook", Outcome.BLOCKED)

    assert notate == ["facebook"]
    assert can_retry is False            # apelantul NU are alt IP pe care sa reincerce
    assert rotatoare == []               # rotatorul nici nu e instantiat


def test_facebook_nu_e_platforma_rutata_prin_modem(monkeypatch):
    """Santinela de politica: un cookie FB vazut de pe alt IP = checkpoint (NET-5),
    deci facebook nu are voie sa intre in allowlist-ul de rotatie."""
    from app.services.network import binding, triggers

    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "mobilede,vinted,autovit,okazii,publi24,lajumate")
    assert "facebook" not in binding.routed_platforms()
    assert triggers.rotate_for("facebook", Outcome.BLOCKED) is False


# ── detectorul si-a pastrat comportamentul dupa mutare ───────────────────────────

def test_detectorul_mutat_e_acelasi_obiect_in_ambele_module():
    from app.scrapers.real_estate import facebook_real_estate as fbre
    assert fbre._looks_like_login_wall is fb._looks_like_login_wall


@pytest.mark.parametrize("html,asteptat", [
    ('<form id="royal_login_form"></form>', True),
    ('<form><input name="email"><input name="pass"></form>', True),
    ('<form method="post" action="/login/?next=x"></form>', True),
    (_HTML_ZERO_LEGITIM, False),
    ("", False),
    (None, False),
])
def test_detectorul_dupa_mutare(html, asteptat):
    assert fb._looks_like_login_wall(html) is asteptat


# ── R5: semnalizare in loc de re-autentificare automata ──────────────────────────
#
# `re_authenticate` (chromium fara masca + parola din .env) a fost STERS: un login
# automat esuat cu checkpoint poate bloca si sesiunile MANUALE viitoare ale contului.
# Detectia ramane (session_probably_expired), actiunea devine semnal: WARN + BLOCKED.

def test_sesiune_invalida_semnalizeaza_si_nu_incearca_login(monkeypatch):
    """Ramura de sesiune invalida: WARN + BLOCKED, zero incercari de login."""
    logs, blocked = [], []
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)))
    monkeypatch.setattr(fb, "report_outcome",
                        lambda platform, outcome: (blocked.append((platform, outcome)), False)[1])
    # Daca ar mai exista vreun login automat, ar trebui sa treaca pe aici:
    monkeypatch.setattr(fb, "_fetch", lambda url, cookies: pytest.fail("nu trebuie sa iasa in retea"))

    out = fb.search_facebook(keyword="iphone", max_price=5000, session_path="sesiune.json")

    assert out == []
    warns = [m for lvl, m in logs if lvl == "WARN"]
    assert len(warns) == 1 and "sesiune" in warns[0].lower()
    assert blocked == [("facebook", Outcome.BLOCKED)]


def test_sesiune_veche_cu_zero_rezultate_semnalizeaza(monkeypatch):
    """Detectia conservatoare (0 rezultate + storage_state > 23h) -> semnal, nu login."""
    import app.services.facebook_auth as fauth

    logs, blocked = [], []
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: True)
    monkeypatch.setattr(fb, "_load_cookies", lambda p: {})
    monkeypatch.setattr(fb, "_fetch",
                        lambda url, cookies: (_HTML_ZERO_LEGITIM, "https://www.facebook.com/marketplace/search/"))
    monkeypatch.setattr(fb, "_iter_listing_objects", lambda h: [])
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)))
    monkeypatch.setattr(fb, "report_outcome",
                        lambda platform, outcome: (blocked.append((platform, outcome)), False)[1])
    monkeypatch.setattr(fauth, "session_probably_expired", lambda results, path: True)

    out = fb.search_facebook(keyword="iphone", max_price=5000, session_path="sesiune.json")

    assert out == []
    assert [m for lvl, m in logs if lvl == "WARN" and "expirat" in m.lower()]
    assert blocked == [("facebook", Outcome.BLOCKED)]


def test_sesiune_valida_cu_rezultate_nu_semnalizeaza_nimic(monkeypatch):
    """CONTROL: scan sanatos -> niciun WARN, niciun BLOCKED (fara alarme false)."""
    out, logs, blocked, _ = _run(monkeypatch, "<html></html>", [_fb_obj("1", "iPhone 13")])
    assert len(out) == 1
    assert [m for lvl, m in logs if lvl == "WARN"] == []
    assert blocked == []


def test_login_automat_nu_mai_exista_nicaieri_in_cod():
    """Pin: nici functia, nici vreun apel/import al ei. Daca cineva o readuce, aici pica.
    Motivul e in docstring-ul lui app/services/facebook_auth.py (R5)."""
    import inspect

    import app.services.facebook_auth as fauth

    assert not hasattr(fauth, "re_authenticate")
    assert not hasattr(fauth, "_reauth_lock")
    src = inspect.getsource(fb)
    # In comentarii numele apare (explica de ce a fost scos) — cautam APELURI/importuri.
    assert "re_authenticate(" not in src
    assert "import re_authenticate" not in src
    assert "_retry" not in src              # parametrul exista doar pentru re-auth
