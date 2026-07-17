"""Backup automat al bazei SQLite — BK-1.

VACUUM INTO scrie o copie compacta si consistenta a bazei din mers (in WAL,
cititorul de backup coexista cu scriitorii), fara oprirea backend-ului.
Rotatie la BACKUP_RETENTION copii. Esecul alerteaza pe Discord — webhook-ul
de alerte al fiecarui user, cu fallback pe cel general (pattern FBG-1).
Fara emit in Jurnale Live: canalele log_manager au semantica de module de
scanare, evenimentele de sistem raman pe print + Discord.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from app.database import engine
from app.config import DATA_DIR

BACKUP_DIR = DATA_DIR / "backups"   # data dir-ul instantei; in dev = cwd, ca inainte
BACKUP_RETENTION = 7           # ultimele 7 copii zilnice (o saptamana)
_PREFIX = "flipradar_backup_"


def _resolve_alert_webhooks(db) -> set[str]:
    """Audienta alertei: toti userii cu webhook de alerte setat, fallback pe
    cel general. Fara filtrul de keyword activ din health_watchdog — backup-ul
    priveste intreaga instanta, nu doar userii care scaneaza."""
    from sqlalchemy import func

    from app.models.radar_settings import RadarSettings

    rows = db.query(
        func.coalesce(RadarSettings.discord_webhook_alerts,
                      RadarSettings.discord_webhook_all)
    ).all()
    return {r[0] for r in rows if r[0]}


def _rotate() -> None:
    copies = sorted(BACKUP_DIR.glob(f"{_PREFIX}*.db"))
    for old in copies[:-BACKUP_RETENTION]:
        old.unlink(missing_ok=True)


def run_db_backup(db=None):
    """Creeaza o copie datata in BACKUP_DIR si aplica rotatia.

    Returneaza calea copiei la succes, None la esec sau skip. `db` (Session)
    e folosit DOAR pentru audienta Discord la esec; None (teste) = fara Discord.
    """
    if engine.dialect.name != "sqlite":
        print("[Backup] Sarit: dialect non-sqlite.")
        return None
    src = engine.url.database
    if not src or src == ":memory:":
        print("[Backup] Sarit: baza fara fisier.")
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"{_PREFIX}{ts}.db"
        # Conexiune sqlite3 dedicata, autocommit: VACUUM nu poate rula intr-o
        # tranzactie, iar conexiunile SQLAlchemy din pool deschid tranzactii.
        conn = sqlite3.connect(src, isolation_level=None)
        try:
            conn.execute("VACUUM INTO ?", (str(dest),))
        finally:
            conn.close()
        check = sqlite3.connect(dest)
        try:
            status = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if status != "ok":
            raise RuntimeError(f"integrity_check pe copie: {status}")
        _rotate()
        print(f"[Backup] OK: {dest}")
        return dest
    except Exception as exc:
        text = f"Backup-ul bazei de date a esuat: {exc}"
        print(f"[Backup] {text}")
        if db is not None:
            try:
                from app.services.radar.discord_service import send_system_alert

                for url in _resolve_alert_webhooks(db):
                    try:
                        send_system_alert(url, text)
                    except Exception as e2:
                        print(f"[Backup] Alerta Discord esuata: {e2}")
            except Exception as e3:
                print(f"[Backup] Rezolvare audienta esuata: {e3}")
        return None
