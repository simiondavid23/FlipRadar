import os
import json
from cryptography.fernet import Fernet

# FBG-2 (C1) — mapa sameSite: extensiile de export (Cookie-Editor, EditThisCookie)
# emit valori cu litere mici ("no_restriction"/"lax"/"strict"/"none"/"unspecified"),
# dar Playwright accepta DOAR capitalizarea exacta Strict/Lax/None si arunca
# `cookies[0].sameSite: expected one of (Strict|Lax|None)` INAINTE de goto —
# adica orice export brut de extensie pica cu "eroare" generica (confirmat empiric
# pe Playwright 1.56/1.58). Valorile necunoscute ("unspecified") se OMIT, nu se
# ghicesc — Playwright aplica default-ul lui.
_SAMESITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "lax": "Lax",
    "strict": "Strict",
}

# Campurile pe care Playwright add_cookies() le intelege. Restul (hostOnly,
# storeId, session, expirationDate — deja convertit mai jos) se arunca.
_PLAYWRIGHT_FIELDS = ("name", "value", "domain", "path", "expires",
                      "httpOnly", "secure", "sameSite")


def normalize_cookies(cookies: list) -> list:
    """FBG-2 (C1) — adapteaza un export de cookies din extensii de browser la
    formatul strict acceptat de Playwright add_cookies().

    - pastreaza doar campurile _PLAYWRIGHT_FIELDS;
    - sameSite: mapare case-insensitive prin _SAMESITE_MAP; valoare necunoscuta
      sau absenta => campul se omite;
    - expirationDate (float, formatul extensiilor) => expires (int); un expires
      existent are prioritate;
    - httpOnly/secure => bool;
    - intrarile care nu sunt dict sau nu au name+value se arunca (Playwright
      le-ar respinge oricum, cu tot batch-ul).
    Idempotenta: un cookie deja normalizat trece neschimbat.
    """
    result = []
    for c in cookies or []:
        if not isinstance(c, dict) or not c.get("name") or "value" not in c:
            continue
        out = {"name": str(c["name"]), "value": str(c["value"])}
        if c.get("domain"):
            out["domain"] = str(c["domain"])
        if c.get("path"):
            out["path"] = str(c["path"])
        expires = c.get("expires", c.get("expirationDate"))
        if expires is not None:
            try:
                out["expires"] = int(float(expires))
            except (TypeError, ValueError):
                pass
        for flag in ("httpOnly", "secure"):
            if flag in c:
                out[flag] = bool(c[flag])
        same_site = _SAMESITE_MAP.get(str(c.get("sameSite", "")).lower())
        if same_site:
            out["sameSite"] = same_site
        result.append(out)
    return result

# Cache in-process al cheii: evita re-citirea fisierului la fiecare apel.
_CACHED_KEY: bytes | None = None


def _key_file():
    """Calea fisierului de cheie persistat: <data_dir>/cookie_encryption_key.

    Acelasi model ca secret_key/vapid_private_key din app.paths (PKG-DATA).
    Import lazy ca modulul sa ramana importabil fara app.paths in teste vechi."""
    from pathlib import Path
    from app.paths import get_data_dir
    return Path(get_data_dir()) / "cookie_encryption_key"


def _get_key() -> bytes:
    """FBG-2 (C4) — cheia de criptare a cookie-urilor, in ordinea:
    1. COOKIE_ENCRYPTION_KEY din mediu (override explicit, prioritar);
    2. fisierul persistat <data_dir>/cookie_encryption_key;
    3. generare + PERSISTARE in fisier la primul boot.

    Inainte, fara variabila in .env cheia se genera PER PROCES (doar print cu
    "adauga in .env") => la primul restart al serviciului toate cookie-urile
    salvate deveneau nedecriptabile (InvalidToken -> configurile pe "eroare").
    """
    global _CACHED_KEY
    key = os.environ.get("COOKIE_ENCRYPTION_KEY")
    if key:
        return key.encode()
    if _CACHED_KEY:
        return _CACHED_KEY
    try:
        f = _key_file()
        if f.is_file():
            stored = f.read_text(encoding="utf-8").strip()
            if stored:
                try:
                    Fernet(stored.encode())  # validare: cheie Fernet reala
                    _CACHED_KEY = stored.encode()
                    return _CACHED_KEY
                except Exception:
                    print("[CookieCrypto] Fisier de cheie corupt — se regenereaza "
                          "(cookie-urile deja salvate vor trebui re-lipite).")
        new_key = Fernet.generate_key()
        f.write_text(new_key.decode(), encoding="utf-8")
        _CACHED_KEY = new_key
        return new_key
    except OSError as exc:
        # Disc read-only / permisiuni: cadem pe comportamentul vechi (cheie de
        # proces) ca sa nu blocam aplicatia, dar spunem explicit ca nu persistam.
        print(f"[CookieCrypto] Nu pot persista cheia ({exc}) — cheia traieste "
              f"doar in acest proces; seteaza COOKIE_ENCRYPTION_KEY in .env.")
        new_key = Fernet.generate_key()
        _CACHED_KEY = new_key
        return new_key


def encrypt_cookies(cookies: list) -> str:
    f = Fernet(_get_key())
    return f.encrypt(json.dumps(cookies).encode()).decode()


def decrypt_cookies(encrypted: str) -> list:
    f = Fernet(_get_key())
    return json.loads(f.decrypt(encrypted.encode()).decode())
