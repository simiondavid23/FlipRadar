"""Caile scriibile ale aplicatiei — PKG-DATA.

Rezolvarea directorului de date, in ordine:
1. FLIPRADAR_DATA_DIR (env) — override explicit (teste, mod portabil).
2. Sub PyInstaller (sys.frozen) — directorul standard per-utilizator:
   Windows: %LOCALAPPDATA%/FlipRadar; altfel: $XDG_DATA_HOME/flipradar.
3. Dev (fallback): directorul curent — comportamentul istoric neschimbat
   (flipradar.db, backups/, data/ raman in backend/ la rularea de acolo).

Modulul NU importa nimic din app.* (e importat de config — fara cicluri).
"""
import os
import secrets
import sys
from pathlib import Path


def get_data_dir() -> Path:
    override = os.getenv("FLIPRADAR_DATA_DIR")
    if override:
        p = Path(override)
    elif getattr(sys, "frozen", False):
        if os.name == "nt":
            base = Path(os.getenv("LOCALAPPDATA")
                        or (Path.home() / "AppData" / "Local"))
            p = base / "FlipRadar"
        else:
            base = Path(os.getenv("XDG_DATA_HOME")
                        or (Path.home() / ".local" / "share"))
            p = base / "flipradar"
    else:
        p = Path.cwd()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_or_create_secret_key(data_dir: Path) -> str:
    """Cheia JWT a instantei: citita din <data_dir>/secret_key sau generata
    (token_hex(32) = 64 caractere) si persistata, ca sesiunile sa
    supravietuiasca restarturilor. Env-ul SECRET_KEY are prioritate (config)."""
    f = data_dir / "secret_key"
    if f.is_file():
        key = f.read_text(encoding="utf-8").strip()
        if len(key) >= 32:
            return key
    key = secrets.token_hex(32)
    f.write_text(key, encoding="utf-8")
    return key


def get_or_create_vapid_keys(data_dir: Path) -> tuple[str, str]:
    """(public_b64url, private_b64url) pentru Web Push — VAPID-AUTO.

    Un singur secret persistat: <data_dir>/vapid_private_key (cheia privata
    P-256 ca base64url al celor 32 de octeti raw). Publicul se DERIVA la
    fiecare pornire din privat — perechea nu se poate desincroniza.
    Generarea foloseste cryptography direct (py_vapid.generate_keys() e
    incompatibil cu cryptography modern); consumul in pywebpush trece prin
    Vapid.from_string, care accepta exact acest format (validat empiric).
    La ImportError (cryptography absent) intoarce ("", "") cu WARN —
    push-ul ramane dezactivat elegant, ca pana acum.
    """
    import base64
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        print("[VAPID] cryptography indisponibil — Web Push dezactivat.")
        return "", ""

    def _b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    f = data_dir / "vapid_private_key"
    sk = None
    if f.is_file():
        try:
            raw = base64.urlsafe_b64decode(
                f.read_text(encoding="utf-8").strip() + "===")
            if len(raw) == 32:
                sk = ec.derive_private_key(
                    int.from_bytes(raw, "big"), ec.SECP256R1())
        except Exception:
            sk = None  # fisier corupt -> regeneram mai jos
    if sk is None:
        sk = ec.generate_private_key(ec.SECP256R1())
        raw = sk.private_numbers().private_value.to_bytes(32, "big")
        f.write_text(_b64u(raw), encoding="utf-8")
    priv_b64 = _b64u(sk.private_numbers().private_value.to_bytes(32, "big"))
    pub_b64 = _b64u(sk.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint))
    return pub_b64, priv_b64
