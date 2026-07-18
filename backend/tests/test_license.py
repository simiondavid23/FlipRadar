"""KEY-1 — teste pentru licentierea cu cheie de activare Ed25519 (mod desktop).

Cheile de test se genereaza EFEMER (o pereche Ed25519 per rulare) si
LICENSE_PUBLIC_KEY_B64 din service se monkeypatch-uieste pe publicul efemer —
nu atingem cheia reala de productie. license.json ajunge in tmp_path (prin
FLIPRADAR_DATA_DIR), iar modul local se simuleaza cu FLIPRADAR_LOCAL_MODE=1.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import license_service as ls
from app.services.license_service import parse_license, LicenseError
from app.models.user import User


# ── helpers b64url (fara padding), oglinda formatului cheii ──────────────────────
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64u(s: str) -> bytes:
    s = s.rstrip("=")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── fixtures ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def signer(monkeypatch):
    """Pereche Ed25519 efemera; publicul ei inlocuieste cheia din service. Intoarce
    o functie issue(payload_dict) -> cheie FLIP.<...>.<...> semnata cu privata efemera."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    priv = ed25519.Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(ls, "LICENSE_PUBLIC_KEY_B64", _b64u(pub_raw))

    def issue(payload: dict) -> str:
        pb = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return "FLIP." + _b64u(pb) + "." + _b64u(priv.sign(pb))

    return issue


@pytest.fixture
def local_mode(monkeypatch, tmp_path):
    """Simuleaza modul desktop + izoleaza license.json in tmp_path."""
    monkeypatch.setenv("FLIPRADAR_LOCAL_MODE", "1")
    monkeypatch.setenv("FLIPRADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _reg_payload():
    uniq = uuid.uuid4().hex[:12]
    return {
        "email": f"key_{uniq}@example.com",
        "username": f"key_{uniq}",
        "password": "testpass123",
        "full_name": "Key Test",
        "security_question": "Care e culoarea preferata?",
        "security_answer": "albastru",
    }


def _set_cookie_headers(resp):
    return [v for (k, v) in resp.headers.multi_items() if k.lower() == "set-cookie"]


# ── a-e: parse_license la nivel de unitate ───────────────────────────────────────
def test_parse_valid_key_returns_payload(signer):
    key = signer({"lid": "FR-0001", "iss": "2026-01-01", "name": "Client"})
    payload = parse_license(key)
    assert payload["lid"] == "FR-0001"
    assert payload["name"] == "Client"
    assert payload["iss"] == "2026-01-01"


def test_parse_rejects_tampered_payload(signer):
    """Payload modificat dar semnatura veche -> semnatura nu se potriveste."""
    key = signer({"lid": "FR-0001", "iss": "2026-01-01"})
    _, payload_seg, sig_seg = key.split(".")
    payload = json.loads(_unb64u(payload_seg))
    payload["lid"] = "FR-HACKED"
    forged = "FLIP." + _b64u(json.dumps(payload, separators=(",", ":")).encode()) + "." + sig_seg
    with pytest.raises(LicenseError):
        parse_license(forged)


def test_parse_rejects_foreign_signature(signer):
    """Semnata cu ALTA cheie privata -> respinsa de publicul din service."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    other = ed25519.Ed25519PrivateKey.generate()
    pb = json.dumps({"lid": "FR-9", "iss": "2026-01-01"}, separators=(",", ":")).encode()
    key = "FLIP." + _b64u(pb) + "." + _b64u(other.sign(pb))
    with pytest.raises(LicenseError):
        parse_license(key)


@pytest.mark.parametrize("bad", [
    "no-flip-prefix.aaa.bbb",           # fara prefix FLIP.
    "FLIP.onlytwo",                     # doar 2 segmente
    "FLIP.@@@.@@@",                     # base64 corupt / semnatura imposibila
    "",                                 # gol
])
def test_parse_rejects_malformed(signer, bad):
    with pytest.raises(LicenseError):
        parse_license(bad)


def test_parse_expiry(signer):
    today = datetime.now(timezone.utc).date()
    past = (today - timedelta(days=1)).isoformat()
    future = (today + timedelta(days=3650)).isoformat()

    with pytest.raises(LicenseError) as ei:
        parse_license(signer({"lid": "FR-1", "iss": "2020-01-01", "exp": past}))
    assert "expirat" in str(ei.value).lower()

    # exp in viitor -> ok; fara exp -> ok
    assert parse_license(signer({"lid": "FR-1", "iss": "2026-01-01", "exp": future}))["lid"] == "FR-1"
    assert parse_license(signer({"lid": "FR-1", "iss": "2026-01-01"}))["lid"] == "FR-1"


# ── f-j: endpointuri /api/license ────────────────────────────────────────────────
def test_activate_local_mode(client, local_mode, signer):
    """Cheie valida in mod local -> 200, license.json scris, user local admin, cookie-uri httpOnly."""
    key = signer({"lid": "FR-0001", "iss": "2026-01-01", "name": "Client"})
    resp = client.post("/api/license/activate", json={"key": key})
    assert resp.status_code == 200, resp.text
    assert resp.json()["activated"] is True

    assert (local_mode / "license.json").is_file()
    saved = json.loads((local_mode / "license.json").read_text(encoding="utf-8"))
    assert saved["key"] == key

    from app.database import SessionLocal
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "local@flipradar.app").first()
        assert u is not None
        assert u.is_admin is True and u.is_active is True
    finally:
        db.close()

    assert resp.cookies.get("access_token")
    assert resp.cookies.get("refresh_token")
    cookies = _set_cookie_headers(resp)
    assert any("access_token" in c and "httponly" in c.lower() for c in cookies)
    assert any("refresh_token" in c and "httponly" in c.lower() for c in cookies)


def test_activate_idempotent(client, local_mode, signer):
    key = signer({"lid": "FR-0001", "iss": "2026-01-01"})
    assert client.post("/api/license/activate", json={"key": key}).status_code == 200
    assert client.post("/api/license/activate", json={"key": key}).status_code == 200
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "local@flipradar.app").count() == 1
    finally:
        db.close()


def test_activate_invalid_key_400(client, local_mode, signer):
    resp = client.post("/api/license/activate", json={"key": "FLIP.garbage"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail  # mesaj romanesc din LicenseError


def test_activate_requires_local_mode_404(client, monkeypatch, tmp_path, signer):
    """Fara mod local, /activate e ascuns (404)."""
    monkeypatch.setenv("FLIPRADAR_DATA_DIR", str(tmp_path))  # izolare, dar FARA LOCAL_MODE
    key = signer({"lid": "FR-1", "iss": "2026-01-01"})
    resp = client.post("/api/license/activate", json={"key": key})
    assert resp.status_code == 404


def test_session_with_and_without_license(client, local_mode, signer):
    # fara licenta pe disc -> 401
    assert client.post("/api/license/session").status_code == 401
    # dupa activare, licenta valida pe disc -> 200 + cookie-uri
    key = signer({"lid": "FR-0001", "iss": "2026-01-01"})
    client.post("/api/license/activate", json={"key": key})
    resp = client.post("/api/license/session")
    assert resp.status_code == 200, resp.text
    assert resp.cookies.get("access_token")
    assert resp.cookies.get("refresh_token")


def test_status_endpoint_public(client, local_mode, signer):
    """/status merge in orice mod, fara autentificare, si reflecta activarea."""
    before = client.get("/api/license/status")
    assert before.status_code == 200
    assert before.json() == {"local_mode": True, "activated": False}
    client.post("/api/license/activate", json={"key": signer({"lid": "FR-7", "iss": "2026-01-01"})})
    after = client.get("/api/license/status").json()
    assert after["activated"] is True and after["lid"] == "FR-7"


# ── k: gardarea fluxului email+parola in mod local ───────────────────────────────
# Fiecare endpoint primeste un body/param VALID pentru schema lui, ca requestul sa
# treaca de validarea Pydantic (422) si sa AJUNGA la guard-ul de mod local (404).
def _selfservice_call(client):
    return {
        "register": lambda: client.post("/api/auth/register", json=_reg_payload()),
        "security-question": lambda: client.get(
            "/api/auth/security-question", params={"email": "x@example.com"}),
        "reset-password": lambda: client.post("/api/auth/reset-password", json={
            "email": "x@example.com", "security_answer": "albastru", "new_password": "parolanoua"}),
    }


@pytest.mark.parametrize("name", ["register", "security-question", "reset-password"])
def test_selfservice_blocked_in_local_mode(client, monkeypatch, name):
    monkeypatch.setenv("FLIPRADAR_LOCAL_MODE", "1")
    resp = _selfservice_call(client)[name]()
    assert resp.status_code == 404, f"{name}: {resp.status_code} {resp.text[:200]}"


def test_register_still_works_in_normal_mode(client):
    """Fara mod local, register-ul clasic ramane functional (dev/web neafectat)."""
    resp = client.post("/api/auth/register", json=_reg_payload())
    assert resp.status_code == 200, resp.text
