"""PKG-DATA — rezolvarea directorului de date + cheia secreta persistata.

Testam direct functiile din app.paths (fara sa re-importam config, ca sa evitam
efectele lui la nivel de modul). Toate caile scriibile sunt tmp_path.
"""
import sys
from pathlib import Path

from app.paths import get_data_dir, get_or_create_secret_key, get_or_create_vapid_keys


def test_override_env_wins(tmp_path, monkeypatch):
    dd = tmp_path / "dd"
    monkeypatch.setenv("FLIPRADAR_DATA_DIR", str(dd))
    result = get_data_dir()
    assert result == dd
    assert result.is_dir()  # get_data_dir creeaza directorul


def test_dev_fallback_is_cwd(monkeypatch):
    monkeypatch.delenv("FLIPRADAR_DATA_DIR", raising=False)
    # fara override si fara sys.frozen -> comportamentul istoric (cwd)
    assert get_data_dir() == Path.cwd()


def test_frozen_uses_per_user_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("FLIPRADAR_DATA_DIR", raising=False)
    # setam ambele (cross-OS) ca mkdir sa nu atinga home-ul real
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    result = get_data_dir()
    assert result.name.lower() == "flipradar"
    assert tmp_path in result.parents  # sub tmp_path, nu in home
    assert result != Path.cwd()


def test_secret_key_generated_and_persisted(tmp_path):
    k1 = get_or_create_secret_key(tmp_path)
    assert len(k1) == 64
    assert len(bytes.fromhex(k1)) == 32  # hex valid -> 32 octeti
    # al doilea apel citeste fisierul persistat, aceeasi cheie
    k2 = get_or_create_secret_key(tmp_path)
    assert k2 == k1
    # o cheie prea scurta pe disc e ignorata si regenerata
    (tmp_path / "secret_key").write_text("scurt", encoding="utf-8")
    k3 = get_or_create_secret_key(tmp_path)
    assert len(k3) == 64
    assert k3 != "scurt"


# ── VAPID-AUTO — chei Web Push per instanta ──────────────────────────────────

def _b64u_decode(s: str) -> bytes:
    import base64
    return base64.urlsafe_b64decode(s + "===")


def test_vapid_generate_shapes(tmp_path):
    pub, priv = get_or_create_vapid_keys(tmp_path)
    assert len(_b64u_decode(priv)) == 32          # cheia privata raw P-256
    pub_raw = _b64u_decode(pub)
    assert len(pub_raw) == 65                       # punct necomprimat P-256
    assert pub_raw[0] == 0x04                        # prefix UncompressedPoint
    assert (tmp_path / "vapid_private_key").is_file()


def test_vapid_persists(tmp_path):
    p1 = get_or_create_vapid_keys(tmp_path)
    p2 = get_or_create_vapid_keys(tmp_path)          # a doua pornire citeste fisierul
    assert p1 == p2                                   # exact aceeasi pereche


def test_vapid_consumable_by_pywebpush(tmp_path):
    # Testul de aur: traseul REAL pywebpush -> Vapid.from_string trebuie sa
    # accepte formatul nostru, iar publicul derivat de el sa fie EXACT publicul nostru.
    import base64
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization

    pub, priv = get_or_create_vapid_keys(tmp_path)
    v = Vapid.from_string(priv)
    derived = base64.urlsafe_b64encode(v.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint)).rstrip(b"=").decode()
    assert derived == pub


def test_vapid_regenerates_on_corrupt_file(tmp_path):
    (tmp_path / "vapid_private_key").write_text("abc", encoding="utf-8")
    pub, priv = get_or_create_vapid_keys(tmp_path)    # nu arunca exceptie
    assert len(_b64u_decode(priv)) == 32              # regenerata, valida
    assert priv != "abc"
