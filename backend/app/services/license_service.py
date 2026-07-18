"""FlipRadar — serviciu de licentiere (KEY-1). Verificare Ed25519 complet OFFLINE.

O cheie de activare are forma:
    FLIP.<b64url(payload_json)>.<b64url(semnatura_64B)>        (fara padding)
Payload-ul e JSON compact {"lid","iss"[,"name"][,"exp"]}. Semnatura Ed25519 se
verifica pe bytes-ii payload-ului cu cheia publica de mai jos; perechea privata e
la furnizor (scripts/licensing/keys/, gitignored). Nimic nu iese pe retea —
totul se valideaza local, deci build-urile desktop functioneaza fara internet.
"""
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.paths import get_data_dir

# Cheia publica Ed25519 (base64url, raw 32B) — perechea cheii private de semnare.
# Regenerata cu: python scripts/licensing/generate_license.py gen-keys
LICENSE_PUBLIC_KEY_B64 = "d3J-Sa7VhyAg7It8bxxdrt1PSsYnGjt_3cyeavuGKQo"

_PREFIX = "FLIP."


class LicenseError(Exception):
    """Eroare de licenta cu mesaj in romana, afisabil direct utilizatorului."""


def is_local_mode() -> bool:
    """Modul desktop/local: sub PyInstaller (sys.frozen) sau prin env explicit
    FLIPRADAR_LOCAL_MODE=1. FLIPRADAR_TESTING NU implica local — testele seteaza
    FLIPRADAR_LOCAL_MODE cand vor sa exerseze fluxul desktop."""
    return bool(getattr(sys, "frozen", False)) or os.getenv("FLIPRADAR_LOCAL_MODE") == "1"


def _b64u_decode(s: str) -> bytes:
    """base64url tolerant la padding (accepta cu sau fara '=')."""
    s = s.strip().rstrip("=")
    pad = "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s + pad)
    except Exception:
        raise LicenseError("Cheie de activare invalida (format base64 corupt).")


def _public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(_b64u_decode(LICENSE_PUBLIC_KEY_B64))


def parse_license(key: str) -> dict:
    """Valideaza o cheie de activare si intoarce payload-ul, sau ridica LicenseError
    cu mesaj distinct (format / semnatura / expirat). Nu atinge discul sau reteaua."""
    if not isinstance(key, str) or not key.startswith(_PREFIX):
        raise LicenseError("Cheie de activare invalida (prefix necunoscut).")
    parts = key.split(".")
    if len(parts) != 3:
        raise LicenseError("Cheie de activare invalida (format gresit).")

    payload_bytes = _b64u_decode(parts[1])
    signature = _b64u_decode(parts[2])

    from cryptography.exceptions import InvalidSignature
    try:
        _public_key().verify(signature, payload_bytes)
    except InvalidSignature:
        raise LicenseError("Cheie de activare invalida (semnatura nu se potriveste).")

    try:
        payload = json.loads(payload_bytes)
    except Exception:
        raise LicenseError("Cheie de activare invalida (continut necitibil).")
    if not isinstance(payload, dict) or "lid" not in payload:
        raise LicenseError("Cheie de activare invalida (continut incomplet).")

    exp = payload.get("exp")
    if exp:
        try:
            exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
        except ValueError:
            raise LicenseError("Cheie de activare invalida (data de expirare necitibila).")
        if datetime.now(timezone.utc).date() > exp_date:
            raise LicenseError("Cheia a expirat.")

    return payload


def license_path() -> Path:
    return get_data_dir() / "license.json"


def save_license(key: str) -> None:
    license_path().write_text(json.dumps({"key": key}), encoding="utf-8")


def load_license() -> str | None:
    p = license_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = data.get("key") if isinstance(data, dict) else None
    return key if isinstance(key, str) and key else None


def get_status() -> dict:
    """{"local_mode","activated"[,"lid","name","iss","exp"]}. Licenta de pe disc e
    RE-VERIFICATA la fiecare apel (nu doar prezenta) — o cheie expirata/coruptа
    inseamna activated=False."""
    status = {"local_mode": is_local_mode(), "activated": False}
    key = load_license()
    if not key:
        return status
    try:
        payload = parse_license(key)
    except LicenseError:
        return status
    status["activated"] = True
    for field in ("lid", "name", "iss", "exp"):
        if field in payload:
            status[field] = payload[field]
    return status
