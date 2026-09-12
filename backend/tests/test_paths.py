"""PKG-DATA — rezolvarea directorului de date + cheia secreta persistata.

Testam direct functiile din app.paths (fara sa re-importam config, ca sa evitam
efectele lui la nivel de modul). Toate caile scriibile sunt tmp_path.
"""
import sys
from pathlib import Path

from app.paths import get_data_dir, get_or_create_secret_key


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
