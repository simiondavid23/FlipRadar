"""Criptare/decriptare a cookie-urilor de sesiune ale platformelor (Vinted/LaJumate/
Okazii) stocate ca text in radar_settings.

Cheia Fernet e derivata din SECRET_KEY (PBKDF2-HMAC-SHA256), deci nu necesita o
variabila de mediu separata. Distinct de app.utils.cookie_crypto, care cripteaza
liste de cookies pentru grupurile Facebook folosind COOKIE_ENCRYPTION_KEY.
"""
import base64
import os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

_SALT = b"flipradar_cookie_v1"


def _get_fernet() -> Fernet:
    key_material = os.getenv("SECRET_KEY", "dev_fallback_key_change_in_prod").encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=100_000)
    key = base64.urlsafe_b64encode(kdf.derive(key_material))
    return Fernet(key)


def encrypt_cookie(plain: str) -> str:
    """Criptează un cookie de sesiune înainte de stocare în DB."""
    if not plain:
        return plain
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_cookie(value: str) -> str:
    """Decriptează un cookie de sesiune din DB.
    Backward compatible: dacă valoarea nu e criptată valid, o returnează ca atare.
    """
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # Valoare plain text (salvată înainte de această modificare) — returnează neatinsă
        return value
