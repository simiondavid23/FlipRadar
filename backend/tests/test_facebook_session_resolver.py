"""FB-AUDIT A2+A3 — sesiunea Facebook se rezolva PER USER, nu "cea mai recenta de pe disc".

Inainte, Auto/Imobiliare-Marketplace/stats faceau glob("data/facebook_session_*.json")
si luau max pe mtime: scanul userului B rula pe contul userului A daca acela se logase
mai recent (A2), iar calea pleca din CWD in loc de DATA_DIR (A3).

DATA_DIR e rezolvat O SINGURA DATA, la importul app.config (`DATA_DIR = get_data_dir()`),
deci setarea variabilei FLIPRADAR_DATA_DIR dupa import e un no-op. Testele patch-uiesc
valoarea deja rezolvata — exact ce citeste _default_facebook_session_path prin importul
lui local — si seteaza si env-ul, ca intentia sa ramana lizibila.
"""
import json
import os
import time

import pytest

from app.services.facebook_session import resolve_facebook_session_path


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """DATA_DIR mutat in tmp_path (izolat de CWD si de %LOCALAPPDATA%)."""
    monkeypatch.setenv("FLIPRADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path)
    return tmp_path


def _user(db, email):
    from app.models.user import User

    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _write_session(path, age_seconds=0):
    """Fisier de sesiune VALID (cookie c_user), optional imbatranit prin mtime."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cookies": [{"name": "c_user", "value": "42"}]}, f)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


def _default_path(data_dir, user_id):
    return str(data_dir / "data" / f"facebook_session_{user_id}.json")


# ── precedenta: setarea userului bate calea default ─────────────────────────────

def test_calea_din_settings_castiga(data_dir):
    from app.database import SessionLocal
    from app.models.radar_settings import RadarSettings

    db = SessionLocal()
    try:
        u = _user(db, "fbsess_settings@example.com")
        aleasa = str(data_dir / "custom" / "sesiunea_mea.json")
        db.add(RadarSettings(user_id=u.id, facebook_session_path=aleasa))
        db.commit()
        assert resolve_facebook_session_path(db, u.id) == aleasa
    finally:
        db.close()


# ── fallback: calea default per-user, sub DATA_DIR (nu sub CWD) ─────────────────

def test_fara_settings_cade_pe_calea_default_din_data_dir(data_dir):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u = _user(db, "fbsess_default@example.com")
        db.commit()
        rezolvata = resolve_facebook_session_path(db, u.id)
        assert rezolvata == _default_path(data_dir, u.id)
        # A3: sub DATA_DIR, NU relativ la CWD.
        assert os.path.isabs(rezolvata)
        assert str(data_dir) in rezolvata
        assert not os.path.relpath(rezolvata, os.getcwd()).startswith("data" + os.sep)
    finally:
        db.close()


def test_fara_user_id_nu_alege_sesiunea_nimanui(data_dir):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        assert resolve_facebook_session_path(db, None) is None
    finally:
        db.close()


# ── ANTI-REGRESIE A2: fisierul mai recent al altui user nu mai fura scanul ──────

def test_a2_sesiunea_altui_user_mai_recenta_nu_mai_castiga(data_dir):
    """TESTUL-TINTA. Vechiul glob + max(mtime) intorcea fisierul lui A si pentru B."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        a = _user(db, "fbsess_a@example.com")
        b = _user(db, "fbsess_b@example.com")
        db.commit()

        cale_a = _write_session(_default_path(data_dir, a.id))                 # proaspat
        cale_b = _write_session(_default_path(data_dir, b.id), age_seconds=3600)  # mai vechi
        assert os.path.getmtime(cale_a) > os.path.getmtime(cale_b)   # A e cel mai recent

        assert resolve_facebook_session_path(db, b.id) == cale_b
        assert resolve_facebook_session_path(db, a.id) == cale_a
    finally:
        db.close()


# ── stats: bannerul de sesiune priveste DOAR fisierul userului curent ───────────

def _kw_fbm(db, user):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    db.add(RealEstateMonitorKeyword(user_id=user.id, name="kw", platform="facebook_marketplace",
                                    is_active=True, active_hours_start=None,
                                    active_hours_end=None))
    db.commit()


def test_stats_vede_sesiunea_proprie_valida(data_dir):
    from app.database import SessionLocal
    from app.routers.real_estate_keywords import get_stats

    db = SessionLocal()
    try:
        u = _user(db, "fbsess_stats_ok@example.com")
        _kw_fbm(db, u)
        _write_session(_default_path(data_dir, u.id))
        assert get_stats(db=db, current_user=u)["facebook_session_valid"] is True
    finally:
        db.close()


def test_stats_nu_imprumuta_sesiunea_altui_user(data_dir):
    from app.database import SessionLocal
    from app.routers.real_estate_keywords import get_stats

    db = SessionLocal()
    try:
        altul = _user(db, "fbsess_stats_alt@example.com")
        u = _user(db, "fbsess_stats_gol@example.com")
        _kw_fbm(db, u)
        _write_session(_default_path(data_dir, altul.id))   # doar ALTUL are sesiune
        assert get_stats(db=db, current_user=u)["facebook_session_valid"] is False
    finally:
        db.close()
