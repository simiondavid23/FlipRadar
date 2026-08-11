"""FBG-2 (C1 + C4) — normalizatorul de cookies pentru Playwright si persistenta
cheii de criptare.

C1: exporturile extensiilor (Cookie-Editor / EditThisCookie) emit sameSite cu
litere mici ("no_restriction"/"lax"/"strict"/"unspecified") + campuri extra;
Playwright add_cookies() accepta DOAR Strict/Lax/None si arunca inainte de goto
=> orice export brut pica cu status "eroare" generic (confirmat empiric pe
Playwright real: RAW respins cu `cookies[0].sameSite: expected one of
(Strict|Lax|None)`, normalizat acceptat integral).

C4: fara COOKIE_ENCRYPTION_KEY in .env, cheia se genera PER PROCES => la primul
restart cookie-urile salvate deveneau nedecriptabile. Acum se persista in
<data_dir>/cookie_encryption_key (modelul secret_key din PKG-DATA).
"""
import asyncio
import json

import pytest

import app.services.facebook_group_service as fbs
import app.utils.cookie_crypto as cc
from app.services.facebook_group_service import _process_config
from app.utils.cookie_crypto import (
    decrypt_cookies,
    encrypt_cookies,
    normalize_cookies,
)


# Export tipic Cookie-Editor: sameSite lowercase, expirationDate float, campuri extra.
def _raw_export():
    return [
        {"name": "c_user", "value": "100001", "domain": ".facebook.com",
         "path": "/", "sameSite": "no_restriction", "secure": True,
         "httpOnly": False, "hostOnly": False, "session": False,
         "storeId": "0", "expirationDate": 1790000000.123},
        {"name": "xs", "value": "abc%3A123", "domain": ".facebook.com",
         "path": "/", "sameSite": "unspecified", "secure": True,
         "httpOnly": True, "storeId": "0", "expirationDate": 1790000000.5},
        {"name": "datr", "value": "xyz", "domain": ".facebook.com",
         "path": "/", "sameSite": "lax", "secure": True, "httpOnly": True},
    ]


# ── C1: normalize_cookies ───────────────────────────────────────────────────────
def test_samesite_lowercase_e_mapat_la_capitalizarea_playwright():
    out = normalize_cookies(_raw_export())
    assert out[0]["sameSite"] == "None"      # no_restriction
    assert out[2]["sameSite"] == "Lax"       # lax
    strict = normalize_cookies([{"name": "a", "value": "b", "sameSite": "strict"}])
    assert strict[0]["sameSite"] == "Strict"
    # "none" (formatul EditThisCookie) -> "None"
    none_ = normalize_cookies([{"name": "a", "value": "b", "sameSite": "none"}])
    assert none_[0]["sameSite"] == "None"


def test_samesite_necunoscut_sau_absent_se_omite():
    out = normalize_cookies(_raw_export())
    assert "sameSite" not in out[1]          # unspecified -> omis
    fara = normalize_cookies([{"name": "a", "value": "b"}])
    assert "sameSite" not in fara[0]


def test_campurile_extra_de_extensie_sunt_eliminate():
    out = normalize_cookies(_raw_export())
    for c in out:
        for extra in ("hostOnly", "session", "storeId", "expirationDate"):
            assert extra not in c


def test_expiration_date_float_devine_expires_int():
    out = normalize_cookies(_raw_export())
    assert out[0]["expires"] == 1790000000
    assert isinstance(out[0]["expires"], int)
    # expires deja prezent are prioritate si ramane
    keep = normalize_cookies([{"name": "a", "value": "b", "expires": 123,
                               "expirationDate": 456.7}])
    assert keep[0]["expires"] == 123


def test_intrarile_fara_name_sau_value_se_arunca():
    out = normalize_cookies([
        {"value": "orfan"}, {"name": "fara_value"}, "nu-e-dict", None,
        {"name": "ok", "value": ""},   # value gol e VALID (exista cheia)
    ])
    assert [c["name"] for c in out] == ["ok"]


def test_normalizarea_e_idempotenta():
    o1 = normalize_cookies(_raw_export())
    assert normalize_cookies(o1) == o1


# ── C1: capatul de salvare normalizeaza inainte de criptare ─────────────────────
def _make_config(auth_client):
    r = auth_client.post("/api/facebook-groups", json={
        "group_name": "Chirii Test",
        "group_url": "https://facebook.com/groups/test",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_save_cookies_stocheaza_forma_normalizata(auth_client):
    cfg_id = _make_config(auth_client)
    r = auth_client.post(f"/api/facebook-groups/{cfg_id}/cookies",
                         json={"cookies_json": json.dumps(_raw_export())})
    assert r.status_code == 200, r.text

    from app.database import SessionLocal
    from app.models.facebook_group_config import FacebookGroupConfig
    db = SessionLocal()
    try:
        cfg = db.query(FacebookGroupConfig).filter(
            FacebookGroupConfig.id == cfg_id).first()
        stored = decrypt_cookies(cfg.cookies_encrypted)
    finally:
        db.close()
    assert stored == normalize_cookies(_raw_export())
    assert all("storeId" not in c for c in stored)


def test_save_cookies_export_fara_niciun_cookie_valid_da_400(auth_client):
    cfg_id = _make_config(auth_client)
    r = auth_client.post(f"/api/facebook-groups/{cfg_id}/cookies",
                         json={"cookies_json": json.dumps([{"storeId": "0"}])})
    assert r.status_code == 400
    assert "Niciun cookie valid" in r.json()["detail"]


# ── C1: statusul dedicat "cookies_invalide" in _process_config ──────────────────
def _user_si_config(db):
    from app.models.facebook_group_config import FacebookGroupConfig
    from app.models.user import User
    u = User(email="fbg_inv@example.com", username="fbg_inv",
             hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    c = FacebookGroupConfig(user_id=u.id, group_name="G",
                            group_url="https://facebook.com/groups/g",
                            is_active=True, cookies_encrypted="x")
    db.add(c)
    db.flush()
    return c


def test_add_cookies_respins_seteaza_status_cookies_invalide(monkeypatch):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        cfg = _user_si_config(db)
        monkeypatch.setattr(fbs, "decrypt_cookies", lambda enc: [])

        async def _fail(**kwargs):
            raise Exception("COOKIES_INVALIDE: cookies[0].sameSite: expected ...")

        monkeypatch.setattr(fbs, "scrape_facebook_group", _fail)
        asyncio.run(_process_config(db, cfg))
        assert cfg.last_run_status == "cookies_invalide"
    finally:
        db.close()


def test_eroarea_generica_ramane_status_eroare(monkeypatch):
    """Control negativ: o exceptie oarecare NU e clasificata drept cookies_invalide."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        cfg = _user_si_config(db)
        monkeypatch.setattr(fbs, "decrypt_cookies", lambda enc: [])

        async def _fail(**kwargs):
            raise Exception("Nu am putut accesa grupul: timeout")

        monkeypatch.setattr(fbs, "scrape_facebook_group", _fail)
        asyncio.run(_process_config(db, cfg))
        assert cfg.last_run_status == "eroare"
    finally:
        db.close()


# ── C4: persistenta cheii de criptare ──────────────────────────────────────────
@pytest.fixture
def _cheie_izolata(monkeypatch, tmp_path):
    """Izoleaza rezolvarea cheii: fara env, cache golit, data dir pe tmp_path."""
    monkeypatch.delenv("COOKIE_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("FLIPRADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cc, "_CACHED_KEY", None)
    yield tmp_path
    monkeypatch.setattr(cc, "_CACHED_KEY", None)


def test_cheia_se_persista_si_supravietuieste_restartului(_cheie_izolata):
    tmp_path = _cheie_izolata
    enc = encrypt_cookies([{"name": "a", "value": "b"}])
    key_file = tmp_path / "cookie_encryption_key"
    assert key_file.is_file(), "cheia trebuie scrisa pe disc la prima folosire"

    # "Restart": cache-ul de proces golit -> cheia se reciteste din fisier.
    cc._CACHED_KEY = None
    assert decrypt_cookies(enc) == [{"name": "a", "value": "b"}]


def test_env_are_prioritate_peste_fisier(_cheie_izolata, monkeypatch):
    tmp_path = _cheie_izolata
    from cryptography.fernet import Fernet
    env_key = Fernet.generate_key().decode()
    # Un fisier DIFERIT exista deja; env-ul trebuie sa castige.
    tmp_path.joinpath("cookie_encryption_key").write_text(
        Fernet.generate_key().decode(), encoding="utf-8")
    monkeypatch.setenv("COOKIE_ENCRYPTION_KEY", env_key)
    enc = encrypt_cookies([{"name": "k", "value": "v"}])
    assert Fernet(env_key.encode())  # env-ul e o cheie valida
    assert decrypt_cookies(enc) == [{"name": "k", "value": "v"}]
    # Criptat cu cheia din env, deci decriptabil direct cu ea:
    import json as _json
    assert _json.loads(Fernet(env_key.encode()).decrypt(enc.encode()).decode()) \
        == [{"name": "k", "value": "v"}]


def test_fisier_corupt_se_regenereaza(_cheie_izolata):
    tmp_path = _cheie_izolata
    key_file = tmp_path / "cookie_encryption_key"
    key_file.write_text("nu-e-o-cheie-fernet", encoding="utf-8")
    enc = encrypt_cookies([{"name": "a", "value": "b"}])
    # Fisierul a fost inlocuit cu o cheie valida si functionala.
    from cryptography.fernet import Fernet
    Fernet(key_file.read_text(encoding="utf-8").strip().encode())
    cc._CACHED_KEY = None
    assert decrypt_cookies(enc) == [{"name": "a", "value": "b"}]
