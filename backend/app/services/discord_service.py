"""
Discord notification service — coadă persistentă în PostgreSQL (MODIFICARE 7).
- La enqueue: inserează în discord_queue cu status 'pending'
- Worker thread: polling la fiecare 2s, procesează max 5 iteme/ciclu
- Deduplicare: verifică discord_notifications_sent (tabel existent) înainte de insert
- Retry: max 3 încercări, după care status='failed'
- La startup: items 'pending' mai vechi de 1h → 'failed' (stale cleanup)

NOTA Radar: modulul Radar Piata are deja un router Discord complet, cu 3 niveluri
(all / buy_now=A,B / maybe=C,D) si embed-uri bogate (resale/marja/date) — vezi
app/services/radar/discord_service.route_discord_alerts. Nu il inlocuim ca sa nu
regresam (canalul C/D + campurile bogate). Coada globala de aici e folosita de
modulele noi (Auto + Imobiliare). send_radar_notification e pastrat corect (pe
field-urile reale discord_webhook_all/buy_now) pentru completitudine.
"""
import os
import json
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests as req
from sqlalchemy.orm import Session
from app.database import SessionLocal


class DiscordNotificationService:
    _MAX_RETRY = 3
    _POLL_INTERVAL = 2  # secunde între polling-uri

    def __init__(self):
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="discord-queue-worker")
        # Sub pytest (FLIPRADAR_TESTING=1) NU pornim worker-ul de fundal: ar accesa
        # baza de test concurent cu suita. enqueue() ramane functional; doar flush-ul
        # cozii lipseste in teste. In productie variabila nu exista → worker-ul porneste.
        if os.getenv("FLIPRADAR_TESTING") != "1":
            self._thread.start()

    def enqueue(self, webhook_url: str, embed: dict, listing_id: str,
                module: str, grade: str, mention_here: bool = False,
                image_url: Optional[str] = None) -> None:
        if not webhook_url or not webhook_url.startswith("http"):
            return
        db = SessionLocal()
        try:
            # Deduplicare 24h
            if self._is_duplicate(listing_id, module, webhook_url, db):
                return
            from app.models.discord_queue_db import DiscordQueueItem
            item = DiscordQueueItem(
                webhook_url=webhook_url,
                embed=json.dumps(embed, ensure_ascii=False),
                listing_id=listing_id,
                module=module,
                grade=grade,
                mention_here=mention_here,
                image_url=image_url,
            )
            db.add(item)
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[Discord] Eroare la enqueue: {exc}")
        finally:
            db.close()

    def _is_duplicate(self, listing_id: str, module: str,
                      webhook_url: str, db: Session) -> bool:
        from sqlalchemy import text
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = db.execute(
            text("SELECT 1 FROM discord_notifications_sent "
                 "WHERE listing_id=:lid AND module=:mod AND webhook_url=:wh AND sent_at>:cutoff LIMIT 1"),
            {"lid": listing_id, "mod": module, "wh": webhook_url, "cutoff": cutoff}
        ).fetchone()
        return result is not None

    def _mark_sent(self, listing_id: str, module: str,
                   webhook_url: str, db: Session) -> None:
        from sqlalchemy import text
        db.execute(
            text("INSERT INTO discord_notifications_sent (listing_id, module, webhook_url, sent_at) "
                 "VALUES (:lid, :mod, :wh, :now) ON CONFLICT DO NOTHING"),
            {"lid": listing_id, "mod": module, "wh": webhook_url,
             "now": datetime.now(timezone.utc)}
        )
        db.commit()

    def _worker(self) -> None:
        """Worker thread: polling PostgreSQL pentru iteme pending."""
        while True:
            try:
                self._process_batch()
            except Exception as exc:
                print(f"[Discord] Eroare worker: {exc}")
            time.sleep(self._POLL_INTERVAL)

    def _process_batch(self) -> None:
        from app.models.discord_queue_db import DiscordQueueItem
        db = SessionLocal()
        try:
            items = db.query(DiscordQueueItem).filter(
                DiscordQueueItem.status == "pending"
            ).order_by(DiscordQueueItem.created_at).limit(5).all()

            for item in items:
                self._send_item(item, db)
                time.sleep(1)  # 1s între trimiteri (rate limit Discord)
        finally:
            db.close()

    def _send_item(self, item, db: Session) -> None:
        try:
            embed = json.loads(item.embed)
            payload: dict = {"embeds": [embed]}
            if item.mention_here:
                payload["content"] = "@here"

            resp = req.post(item.webhook_url, json=payload, timeout=10)

            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                time.sleep(retry_after)
                return  # Va fi reîncercat în ciclul următor

            if resp.status_code in (200, 204):
                item.status = "sent"
                item.sent_at = datetime.now(timezone.utc)
                db.commit()
                self._mark_sent(item.listing_id, item.module, item.webhook_url, db)
            else:
                self._handle_failure(item, f"HTTP {resp.status_code}", db)

        except Exception as exc:
            self._handle_failure(item, str(exc)[:200], db)

    def _handle_failure(self, item, error: str, db: Session) -> None:
        item.retry_count += 1
        item.error_msg = error
        if item.retry_count >= self._MAX_RETRY:
            item.status = "failed"
        db.commit()

    def cleanup_stale(self, db: Session) -> None:
        """La startup: marchează pending mai vechi de 1h ca failed (stale)."""
        from sqlalchemy import text
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        db.execute(
            text("UPDATE discord_queue SET status='failed', error_msg='Stale la restart' "
                 "WHERE status='pending' AND created_at < :cutoff"),
            {"cutoff": cutoff}
        )
        db.commit()


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
        "footer": {"text": f"FlipRadar Radar Piață · Score {score}/100"},
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


# ── ALERT-1 — Alerte de pret + Flash Deals ──────────────────────────

ALERT_COLORS = {"price_drop": 0x22c55e, "price_rise": 0x3b82f6}
FLASH_DEAL_COLOR = 0xf59e0b


def build_alert_embed(product_name: str, current_price: float, target_price: float,
                      currency: str, alert_type: str, product_url: str = None) -> dict:
    emoji = "📉" if alert_type == "price_drop" else "📈"
    embed = {
        "title": f"{emoji} Alerta pret: {product_name}"[:200],
        "color": ALERT_COLORS.get(alert_type, ALERT_COLORS["price_drop"]),
        "fields": [
            {"name": "💰 Pret curent",
             "value": f"{current_price:.2f} {currency}", "inline": True},
            {"name": "🎯 Tinta",
             "value": f"{target_price:.2f} {currency}", "inline": True},
        ],
        "footer": {"text": "FlipRadar Alerte"},
    }
    if product_url:
        embed["url"] = product_url
    return embed


def build_flash_deal_embed(product_name: str, old_price: float, new_price: float,
                           currency: str, drop_pct: float, source: str,
                           product_url: str = None) -> dict:
    fields = [
        {"name": "💰 Pret",
         "value": f"{old_price} {currency} -> {new_price} {currency}", "inline": True},
        {"name": "📉 Scadere",
         "value": f"-{drop_pct * 100:.1f}%", "inline": True},
    ]
    if source:
        fields.append({"name": "🏪 Sursa", "value": source.upper(), "inline": True})
    embed = {
        "title": f"⚡ Flash Deal: {product_name}"[:200],
        "color": FLASH_DEAL_COLOR,
        "fields": fields,
        "footer": {"text": "FlipRadar Alerte"},
    }
    if product_url:
        embed["url"] = product_url
    return embed


def send_price_alert_notification(embed: dict, settings, listing_id: str) -> bool:
    """Enqueue pe webhook-ul dedicat de alerte. Returneaza True daca a fost pus in coada."""
    wh = getattr(settings, "discord_webhook_alerts", None)
    if not wh:
        return False
    # grade e doar eticheta stocata in coada (nu e folosita la rutare); coloana
    # discord_queue.grade e VARCHAR(2), asa ca folosim "AL" (alert), nu "alert".
    discord_service.enqueue(webhook_url=wh, embed=embed, listing_id=listing_id,
                            module="alerts", grade="AL", mention_here=False)
    return True


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
            discord_service.enqueue(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="radar", grade=grade, mention_here=mention)
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
            discord_service.enqueue(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="auto", grade=grade, mention_here=mention)


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
            discord_service.enqueue(
                webhook_url=wh, embed=embed, listing_id=listing_id,
                module="imobiliare", grade=grade, mention_here=mention)
