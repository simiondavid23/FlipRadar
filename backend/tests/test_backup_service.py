"""BK-1 — teste pentru backup-ul automat al bazei SQLite.

Fixture-urile autouse din conftest (schema pe fisierul SQLite temporar + golirea
tabelelor inainte de fiecare test) ofera o baza reala, goala, pe care VACUUM INTO
o poate copia. `BACKUP_DIR` se redirecteaza spre tmp_path ca sa nu atinga disk-ul
real; `run_db_backup()` fara `db` nu trimite pe Discord.
"""
import sqlite3

from app.services import backup_service
from app.services.backup_service import run_db_backup


def test_backup_creates_valid_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)

    p = run_db_backup()  # db=None -> fara Discord
    assert p is not None
    assert p.exists()

    conn = sqlite3.connect(p)
    try:
        tables = {r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'")}
        assert "users" in tables
        # ruleaza fara eroare; baza de test e goala intre teste (count 0 e ok)
        conn.execute("select count(*) from users").fetchone()
    finally:
        conn.close()


def test_backup_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(backup_service, "BACKUP_RETENTION", 3)

    for day in range(1, 6):  # 01..05
        (tmp_path / f"flipradar_backup_2026010{day}_000000.db").touch()

    backup_service._rotate()

    remaining = sorted(x.name for x in tmp_path.glob("flipradar_backup_*.db"))
    assert len(remaining) == 3
    assert remaining == [
        "flipradar_backup_20260103_000000.db",
        "flipradar_backup_20260104_000000.db",
        "flipradar_backup_20260105_000000.db",
    ]
