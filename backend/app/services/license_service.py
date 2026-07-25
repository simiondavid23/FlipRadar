"""FlipRadar — serviciu de licentiere (KEY-1). Verificare Ed25519 complet OFFLINE.

O cheie de activare are forma:
    FLIP.<b64url(payload_json)>.<b64url(semnatura_64B)>        (fara padding)
Payload-ul e JSON compact {"lid","iss"[,"name"][,"hwid"][,"exp"]}. Semnatura Ed25519 se
verifica pe bytes-ii payload-ului cu cheia publica de mai jos; perechea privata e
la furnizor (scripts/licensing/keys/, gitignored). Nimic nu iese pe retea —
totul se valideaza local, deci build-urile desktop functioneaza fara internet.
"""
import base64
import hashlib
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
        raise LicenseError("Cheie de activare invalidă (format base64 corupt).")


def _public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(_b64u_decode(LICENSE_PUBLIC_KEY_B64))


def parse_license(key: str) -> dict:
    """Valideaza o cheie de activare si intoarce payload-ul, sau ridica LicenseError
    cu mesaj distinct (format / semnatura / expirat). Nu atinge discul sau reteaua."""
    if not isinstance(key, str) or not key.startswith(_PREFIX):
        raise LicenseError("Cheie de activare invalidă (prefix necunoscut).")
    parts = key.split(".")
    if len(parts) != 3:
        raise LicenseError("Cheie de activare invalidă (format greșit).")

    payload_bytes = _b64u_decode(parts[1])
    signature = _b64u_decode(parts[2])

    from cryptography.exceptions import InvalidSignature
    try:
        _public_key().verify(signature, payload_bytes)
    except InvalidSignature:
        raise LicenseError("Cheie de activare invalidă (semnătura nu se potrivește).")

    try:
        payload = json.loads(payload_bytes)
    except Exception:
        raise LicenseError("Cheie de activare invalidă (conținut necitibil).")
    if not isinstance(payload, dict) or "lid" not in payload:
        raise LicenseError("Cheie de activare invalidă (conținut incomplet).")

    exp = payload.get("exp")
    if exp:
        try:
            exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
        except ValueError:
            raise LicenseError("Cheie de activare invalidă (data de expirare necitibilă).")
        if datetime.now(timezone.utc).date() > exp_date:
            raise LicenseError("Cheia a expirat.")

    return payload


def machine_code() -> str:
    """Codul stabil al acestui computer (KEY-2), format XXXX-XXXX-XXXX-XXXX.

    Sursa id-ului BRUT, in ordine: env FLIPRADAR_MACHINE_ID (override pentru teste,
    id ne-hashat) -> MachineGuid din registrul Windows -> /etc/machine-id (fallback
    dev Linux). Id-ul brut nu se expune niciodata: se publica doar sha256 cu sare
    ("flipradar:"), primele 16 caractere hex, uppercase, grupate 4-4-4-4."""
    raw = os.getenv("FLIPRADAR_MACHINE_ID")
    if not raw and os.name == "nt":
        try:
            import winreg  # doar pe Windows — modulul nu exista pe Linux
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                # Fara WOW64_64KEY un proces 32-bit ar citi nodul redirectat si ar
                # produce ALT cod pe aceeasi masina.
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            raw = None
    if not raw:
        try:
            raw = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        except Exception:
            raw = None
    if not raw:
        raise LicenseError("Nu pot determina codul acestui computer.")
    h = hashlib.sha256(("flipradar:" + str(raw)).encode("utf-8")).hexdigest()[:16].upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def check_hwid(payload: dict) -> None:
    """Bindingul hardware al unei chei (KEY-2). Cheile FARA "hwid" raman universale
    (valabile pe orice computer); cu "hwid" sunt valide doar pe masina emisa.
    Separata de parse_license ca sa nu-i strice puritatea — o apeleaza apelantii."""
    if not isinstance(payload, dict) or "hwid" not in payload:
        return
    if str(payload["hwid"]).strip().upper() != machine_code():
        raise LicenseError("Cheia este emisă pentru alt computer.")


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
    """{"local_mode","activated"[,"machine_code"][,"lid","name","iss","exp","hwid"]}.
    "machine_code" apare doar in mod local. Licenta de pe disc e
    RE-VERIFICATA la fiecare apel (nu doar prezenta) — o cheie expirata/coruptа
    inseamna activated=False."""
    status = {"local_mode": is_local_mode(), "activated": False}
    if status["local_mode"]:
        # KEY-2 — codul masinii e util SI neactivat: userul il trimite vanzatorului
        # ca sa primeasca o cheie legata de acest computer.
        try:
            status["machine_code"] = machine_code()
        except LicenseError:
            pass  # nu il putem determina -> campul lipseste, statusul NU crapa
    key = load_license()
    if not key:
        return status
    try:
        payload = parse_license(key)
        check_hwid(payload)  # KEY-2 — cheie emisa pentru alt computer => activated False
    except LicenseError:
        return status
    status["activated"] = True
    for field in ("lid", "name", "iss", "exp", "hwid"):
        if field in payload:
            status[field] = payload[field]
    return status
