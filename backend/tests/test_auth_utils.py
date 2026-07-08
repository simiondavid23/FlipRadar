"""Teste pentru utilitarele de autentificare: JWT (expires_delta) + hashing parole."""
import time
from datetime import timedelta

from jose import jwt

from app.config import ALGORITHM, SECRET_KEY
from app.utils.auth import create_access_token, get_password_hash, verify_password


def test_access_token_respecta_expires_delta():
    # create_access_token pune exp = now(utc) + expires_delta (utils/auth.py:34).
    before = time.time()
    token = create_access_token({"sub": "42"}, expires_delta=timedelta(minutes=15))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "42"
    # exp e in secunde epoch; toleranta ±30s fata de momentul crearii + 15 min.
    assert abs(payload["exp"] - (before + 15 * 60)) <= 30


def test_password_hash_roundtrip():
    h = get_password_hash("parolaMea123")
    assert h != "parolaMea123"           # nu se stocheaza in clar
    assert verify_password("parolaMea123", h) is True


def test_password_verify_respinge_parola_gresita():
    h = get_password_hash("parolaCorecta")
    assert verify_password("parolaGresita", h) is False
