from collections import deque
from datetime import datetime, date
import os
import time
import json
import threading
import re as _re

# MODIFICARE 12 — persistarea log-urilor in DB e optionala (env LOG_DB_PERSISTENCE).
_DB_PERSISTENCE = os.getenv("LOG_DB_PERSISTENCE", "false").lower() == "true"


class LogManager:
    MODULES = ["radar", "catalog", "auto_lots", "auto_listings", "real_estate"]

    def __init__(self):
        self.buffers: dict[str, deque] = {m: deque(maxlen=500) for m in self.MODULES}
        # ID-urile trebuie sa fie unice si STRICT crescatoare, chiar daca emit()
        # e apelat de mai multe ori in aceeasi milisecunda sau din thread-uri
        # diferite (scannerele ruleaza concurent). int(time.time()*1000) singur
        # nu garanteaza asta -> folosim un contor monoton protejat de un lock.
        self._lock = threading.Lock()
        self._last_id = 0

    def emit(self, module: str, level: str, message: str) -> None:
        if module not in self.buffers:
            module = "radar"
        # Mesajele trebuie sa fie text simplu — eliminam orice tag HTML
        # ramas din greseala (highlight-ul se face in frontend cu regex).
        clean = _re.sub(r"<[^>]+>", "", str(message))
        # Generarea id-ului + append-ul in deque trebuie sa fie atomice sub lock,
        # altfel doua thread-uri ar putea insera intrarile in ordine inversata
        # fata de id-urile lor (id unic dar nu strict crescator in buffer).
        with self._lock:
            new_id = int(time.time() * 1000)
            if new_id <= self._last_id:
                new_id = self._last_id + 1
            self._last_id = new_id
            entry = {
                "id": new_id,
                "ts": datetime.now().strftime("%H:%M:%S"),
                "level": level.upper(),
                "msg": clean,
            }
            self.buffers[module].append(entry)

        # MODIFICARE 12 — persistare optionala in DB (nu afecteaza deque-ul SSE).
        if _DB_PERSISTENCE:
            self._persist_to_db(module, level.upper(), clean)

    def _persist_to_db(self, module: str, level: str, message: str) -> None:
        """Inserare non-blocking în DB. Eșecul DB nu afectează logging-ul în memorie."""
        try:
            from app.database import SessionLocal
            from app.models.log_entry import LogEntry
            db = SessionLocal()
            db.add(LogEntry(module=module, level=level, message=message))
            db.commit()
            db.close()
        except Exception:
            pass  # Silențios — logging-ul în memorie continuă indiferent

    def get_all(self, module: str) -> list:
        return list(self.buffers.get(module, []))

    def get_since(self, module: str, last_id: int) -> list:
        return [e for e in self.buffers.get(module, []) if e["id"] > last_id]

    def get_stats(self) -> dict:
        now_ms = int(time.time() * 1000)
        hour_ago = now_ms - 3_600_000
        five_min_ago = now_ms - 300_000
        today_start = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)
        stats = {}
        total_new_hour = 0
        active_count = 0
        total_today = 0
        for m, buf in self.buffers.items():
            entries = list(buf)
            new_hour = sum(1 for e in entries if e["id"] > hour_ago and e["level"] == "OK")
            active = any(e["id"] > five_min_ago for e in entries)
            today = sum(1 for e in entries if e["id"] > today_start)
            stats[m] = {"new_hour": new_hour, "active": active, "today": today}
            total_new_hour += new_hour
            total_today += today
            if active:
                active_count += 1
        stats["__totals__"] = {
            "active_modules": active_count,
            "new_listings_hour": total_new_hour,
            "events_today": total_today,
        }
        return stats


log_manager = LogManager()
