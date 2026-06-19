import os
import json
from cryptography.fernet import Fernet

# Cache in-process al cheii generate: fara el, fiecare apel ar genera o cheie
# noua, iar criptarea/decriptarea ar folosi chei diferite (cookies nedecriptabile).
_CACHED_KEY: bytes | None = None


def _get_key() -> bytes:
    """Returneaza cheia de criptare din variabila de mediu (sau una generata + cache-uita)."""
    global _CACHED_KEY
    key = os.environ.get("COOKIE_ENCRYPTION_KEY")
    if key:
        return key.encode()
    if _CACHED_KEY:
        return _CACHED_KEY
    # Genereaza o cheie noua la primul run si salveaz-o in .env
    new_key = Fernet.generate_key()
    _CACHED_KEY = new_key
    # O punem si in environ ca apelurile urmatoare din acest proces sa o reutilizeze.
    os.environ["COOKIE_ENCRYPTION_KEY"] = new_key.decode()
    print(f"[ATENTIE] Adauga in .env: COOKIE_ENCRYPTION_KEY={new_key.decode()}")
    return new_key


def encrypt_cookies(cookies: list) -> str:
    f = Fernet(_get_key())
    return f.encrypt(json.dumps(cookies).encode()).decode()


def decrypt_cookies(encrypted: str) -> list:
    f = Fernet(_get_key())
    return json.loads(f.decrypt(encrypted.encode()).decode())
