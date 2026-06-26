"""
Global Discord notification queue.
- Processes all modules (radar, auto, imobiliare) through one queue.
- 1 second delay between sends to respect Discord rate limits.
- Automatic retry on HTTP 429 using retry_after from response.
- Deduplication: same listing_id + module + webhook = skip if sent < 24h ago.
- @here injected for Grade A if toggle enabled.

NOTA Radar: modulul Radar Piata are deja un router Discord complet, cu 3 niveluri
(all / buy_now=A,B / maybe=C,D) si embed-uri bogate (resale/marja/date) — vezi
app/services/radar/discord_service.route_discord_alerts. Nu il inlocuim ca sa nu
regresam (canalul C/D + campurile bogate). Coada globala de aici e folosita de
modulele noi (Auto + Imobiliare). send_radar_notification e pastrat corect (pe
field-urile reale discord_webhook_all/buy_now) pentru completitudine.
"""
import time
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Optional
import requests as req
from sqlalchemy.orm import Session


@dataclass
class DiscordNotification:
    webhook_url: str
    embed: dict
    listing_id: str
    module: str          # "radar" | "auto" | "imobiliare"
    grade: str           # "A" | "B" | "C" | "D"
    mention_here: bool = False
    image_url: Optional[str] = None


class DiscordNotificationService:
    def __init__(self):
        self._queue: Queue = Queue()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="discord-notif-worker")
        self._thread.start()

    def enqueue(self, notif: DiscordNotification, db: Session) -> None:
        if not notif.webhook_url or not notif.webhook_url.startswith("http"):
            return
        if self._is_duplicate(notif, db):
            return
        self._queue.put(notif)

    def _is_duplicate(self, notif: DiscordNotification, db: Session) -> bool:
        from sqlalchemy import text
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = db.execute(
            text("SELECT 1 FROM discord_notifications_sent "
                 "WHERE listing_id = :lid AND module = :mod "
                 "AND webhook_url = :wh AND sent_at > :cutoff LIMIT 1"),
            {"lid": notif.listing_id, "mod": notif.module,
             "wh": notif.webhook_url, "cutoff": cutoff}
        ).fetchone()
        return result is not None

    def _mark_sent(self, notif: DiscordNotification, db: Session) -> None:
        from sqlalchemy import text
        try:
            db.execute(
                text("INSERT INTO discord_notifications_sent "
                     "(listing_id, module, webhook_url) "
                     "VALUES (:lid, :mod, :wh) "
                     "ON CONFLICT DO NOTHING"),
                {"lid": notif.listing_id, "mod": notif.module,
                 "wh": notif.webhook_url}
            )
            db.commit()
        except Exception:
            db.rollback()

    def _send(self, notif: DiscordNotification) -> None:
        payload = {"embeds": [notif.embed]}
        if notif.mention_here and notif.grade == "A":
            payload["content"] = "@here"

        for attempt in range(5):
            try:
                resp = req.post(notif.webhook_url, json=payload, timeout=10)
                if resp.status_code == 204:
                    return
                if resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 1.0)
                    time.sleep(float(retry_after) + 0.1)
                    continue
                print(f"[Discord] HTTP {resp.status_code} on attempt {attempt+1}")
                break
            except Exception as exc:
                print(f"[Discord] Send error attempt {attempt+1}: {exc}")
                time.sleep(2)

    def _worker(self) -> None:
        while True:
            notif: DiscordNotification = self._queue.get()
            try:
                self._send(notif)
                # Mark sent in DB
                from app.database import SessionLocal
                _db = SessionLocal()
                try:
                    self._mark_sent(notif, _db)
                finally:
                    _db.close()
            except Exception as exc:
                print(f"[Discord] Worker error: {exc}")
            finally:
                self._queue.task_done()
                time.sleep(1.0)  # 1 second delay between sends


# Module-level singleton
discord_service = DiscordNotificationService()


# ── Embed builders ─────────────────────────────────────────────────

GRADE_COLORS = {"A": 0x22c55e, "B": 0x3b82f6, "C": 0xf59e0b, "D": 0xef4444}
GRADE_EMOJI  = {"A": "🏆", "B": "⭐", "C": "📌", "D": "📋"}

MODULE_EMOJI = {
    "radar": "🔍",
    "auto": "🚗",
    "imobiliare": "🏠",
}


def build_radar_embed(listing: dict, grade: str, score: int,
                      keyword_name: str) -> dict:
    title_text = listing.get("title", "")[:200]
    price = listing.get("price", "")
    currency = listing.get("currency", "RON")
    platform = listing.get("platform", "")
    location = listing.get("location", "")
    margin = listing.get("margin")
    resale = listing.get("resale_price")

    fields = []
    if price:
        fields.append({"name": "💰 Preț cerut",
                       "value": f"{price} {currency}", "inline": True})
    if resale:
        fields.append({"name": "💵 Revânzare estimată",
                       "value": f"{resale} RON", "inline": True})
    if margin is not None:
        fields.append({"name": "📈 Marjă",
                       "value": f"{margin} RON", "inline": True})
    if platform:
        fields.append({"name": "🏪 Platformă",
                       "value": platform.upper(), "inline": True})
    if location:
        fields.append({"name": "📍 Locație",
                       "value": location, "inline": True})
    fields.append({"name": "🎯 Keyword",
                   "value": keyword_name, "inline": True})

    embed = {
        "title": f"{GRADE_EMOJI[grade]} [{grade}] {title_text}",
        "color": GRADE_COLORS[grade],
        "fields": fields,
        "footer": {"text": f"FlipRadar Radar Piată · Score {score}/100"},
    }
    if listing.get("url"):
        embed["url"] = listing["url"]
    if listing.get("image_url"):
        embed["thumbnail"] = {"url": listing["image_url"]}
    return embed


def build_auto_embed(listing: dict, grade: str, score: int,
                     keyword_name: str) -> dict:
    title_text = listing.get("title", "")[:200]
    price = listing.get("price")
    currency = listing.get("currency", "RON")
    year = listing.get("year")
    km = listing.get("km")
    fuel = listing.get("fuel_type")
    transmission = listing.get("transmission")
    location = listing.get("location")
    platform = listing.get("platform", "")
    import_data = listing.get("import_score_json")

    fields = []
    price_str = f"{price} {currency}" if price else "—"
    fields.append({"name": "💰 Preț", "value": price_str, "inline": True})
    if year:
        fields.append({"name": "📅 An", "value": str(year), "inline": True})
    if km:
        fields.append({"name": "🛣️ Km",
                       "value": f"{int(km):,}".replace(",", "."),
                       "inline": True})
    if fuel:
        fields.append({"name": "⛽ Combustibil",
                       "value": fuel, "inline": True})
    if transmission:
        fields.append({"name": "⚙️ Transmisie",
                       "value": transmission, "inline": True})
    if location:
        fields.append({"name": "📍 Locație",
                       "value": location, "inline": True})
    if platform:
        fields.append({"name": "🏪 Platformă",
                       "value": platform.upper(), "inline": True})
    fields.append({"name": "🎯 Keyword",
                   "value": keyword_name, "inline": True})

    if import_data and currency == "EUR":
        pe_roti = import_data.get("pe_roti", {})
        if pe_roti.get("total_ron"):
            saving = pe_roti.get("saving_ron")
            import_str = f"~{int(pe_roti['total_ron']):,} RON".replace(",", ".")
            if saving is not None:
                icon = "✅" if saving > 0 else "❌"
                import_str += f"\n{icon} Economie: {int(abs(saving)):,} RON".replace(",", ".")
            fields.append({"name": "🌍 Import pe roți",
                           "value": import_str, "inline": False})

    embed = {
        "title": f"🚗 [{grade}] {title_text}",
        "color": GRADE_COLORS[grade],
        "fields": fields,
        "footer": {"text": f"FlipRadar Auto Anunțuri · Score {score}/100"},
    }
    if listing.get("url"):
        embed["url"] = listing["url"]
    if listing.get("image_url"):
        embed["thumbnail"] = {"url": listing["image_url"]}
    return embed


def build_imob_embed(listing: dict, grade: str, score: int,
                     keyword_name: str, zone_avg_ppm: float = None) -> dict:
    title_text = listing.get("title", "")[:200]
    price = listing.get("price")
    currency = listing.get("currency", "RON")
    rooms = listing.get("rooms")
    area = listing.get("area_sqm")
    floor = listing.get("floor")
    zone = listing.get("zone_normalized") or listing.get("zone_raw")
    platform = listing.get("platform", "")

    fields = []
    price_str = f"{price} {currency}/lună" if price else "—"
    fields.append({"name": "💰 Chirie", "value": price_str, "inline": True})
    if rooms:
        fields.append({"name": "🛏️ Camere",
                       "value": str(rooms), "inline": True})
    if area:
        fields.append({"name": "📐 Suprafață",
                       "value": f"{area} mp", "inline": True})
        if price and area > 0:
            ppm = price / area
            ppm_str = f"{ppm:.2f} {currency}/mp"
            if zone_avg_ppm:
                diff_pct = (zone_avg_ppm - ppm) / zone_avg_ppm * 100
                ppm_str += f" (medie zonă: {zone_avg_ppm:.2f} · ↓ {diff_pct:.0f}%)"
            fields.append({"name": "📊 Preț/mp",
                           "value": ppm_str, "inline": False})
    if floor:
        fields.append({"name": "🏢 Etaj",
                       "value": str(floor), "inline": True})
    if zone:
        fields.append({"name": "📍 Zonă",
                       "value": zone, "inline": True})
    if platform:
        fields.append({"name": "🏪 Platformă",
                       "value": platform.upper(), "inline": True})
    fields.append({"name": "🎯 Keyword",
                   "value": keyword_name, "inline": True})

    embed = {
        "title": f"🏠 [{grade}] {title_text}",
        "color": GRADE_COLORS[grade],
        "fields": fields,
        "footer": {"text": f"FlipRadar Imobiliare · Score {score}/100"},
    }
    if listing.get("url"):
        embed["url"] = listing["url"]
    if listing.get("image_url"):
        embed["thumbnail"] = {"url": listing["image_url"]}
    return embed


def send_radar_notification(listing: dict, grade: str, score: int,
                            keyword_name: str, settings,
                            listing_id: str, db: Session) -> int:
    """Pune in coada globala notificarile Radar pe 3 tier-uri (la fel ca vechiul
    route_discord_alerts, dar cu rate-limit + dedup). Returneaza nr. de canale puse
    in coada (folosit de scanner pentru stats/logging)."""
    if grade not in ("A", "B", "C", "D"):
        return 0
    embed = build_radar_embed(listing, grade, score, keyword_name)
    mention = getattr(settings, "discord_here_radar", False) and grade == "A"

    # Field-urile REALE din RadarSettings, 3 tier-uri:
    #   all = TOATE (A/B/C/D) · buy_now = A/B · maybe = C/D.
    queued = 0
    for wh_attr, allowed_grades in [
        ("discord_webhook_all", ("A", "B", "C", "D")),
        ("discord_webhook_buy_now", ("A", "B")),
        ("discord_webhook_maybe", ("C", "D")),
    ]:
        wh = getattr(settings, wh_attr, None)
        if wh and grade in allowed_grades:
            discord_service.enqueue(DiscordNotification(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="radar", grade=grade, mention_here=mention), db)
            queued += 1
    return queued


def send_auto_notification(listing: dict, grade: str, score: int,
                           keyword_name: str, settings,
                           listing_id: str, db: Session) -> None:
    if grade not in ("A", "B"):
        return
    embed = build_auto_embed(listing, grade, score, keyword_name)
    mention = getattr(settings, "discord_here_auto", False) and grade == "A"

    for wh_attr, allowed_grades in [
        ("discord_webhook_auto_all",  ("A", "B", "C", "D")),
        ("discord_webhook_auto_b",    ("B",)),
        ("discord_webhook_auto",      ("A",)),
    ]:
        wh = getattr(settings, wh_attr, None)
        if wh and grade in allowed_grades:
            discord_service.enqueue(DiscordNotification(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="auto", grade=grade, mention_here=mention), db)


def send_imob_notification(listing: dict, grade: str, score: int,
                           keyword_name: str, settings,
                           listing_id: str, db: Session,
                           zone_avg_ppm: float = None) -> None:
    if grade not in ("A", "B"):
        return
    embed = build_imob_embed(listing, grade, score, keyword_name, zone_avg_ppm)
    mention = getattr(settings, "discord_here_imob", False) and grade == "A"

    for wh_attr, allowed_grades in [
        ("discord_webhook_imob_all", ("A", "B", "C", "D")),
        ("discord_webhook_imob_b",   ("B",)),
        ("discord_webhook_imob_a",   ("A",)),
    ]:
        wh = getattr(settings, wh_attr, None)
        if wh and grade in allowed_grades:
            discord_service.enqueue(DiscordNotification(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="imobiliare", grade=grade, mention_here=mention), db)
