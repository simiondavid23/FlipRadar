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
