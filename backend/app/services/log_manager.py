from collections import deque
from datetime import datetime, date
import time
import json
import re as _re


class LogManager:
    MODULES = ["radar", "catalog", "auto_lots", "auto_listings", "real_estate"]

    def __init__(self):
        self.buffers: dict[str, deque] = {m: deque(maxlen=500) for m in self.MODULES}

    def emit(self, module: str, level: str, message: str) -> None:
        if module not in self.buffers:
            module = "radar"
        # Mesajele trebuie sa fie text simplu — eliminam orice tag HTML
        # ramas din greseala (highlight-ul se face in frontend cu regex).
        clean = _re.sub(r"<[^>]+>", "", str(message))
        entry = {
            "id": int(time.time() * 1000),
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level.upper(),
            "msg": clean,
        }
        self.buffers[module].append(entry)

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
