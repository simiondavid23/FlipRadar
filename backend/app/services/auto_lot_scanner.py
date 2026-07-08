"""Scanner periodic pentru auto_lot_keywords — calchiat pe auto_listings_scanner.

Diferenta cheie fata de bug-ul din auto_listings (run_auto_scan scaneaza GLOBAL):
aici avem run_auto_lot_scan_for_user(db, user_id) scopat per-user, iar
run_auto_lot_scan_global(db) doar itereaza userii si deleaga per-user (ca la Radar).
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.auto_lot_keyword import AutoLotKeyword
from app.models.auto_lot import AutoLot
from app.models.user import User
from app.services.log_manager import log_manager
from app.scrapers.auto.lots.copart_public import search_copart_lots
from app.scrapers.auto.lots.iaai_public import search_iaai_lots
from app.scrapers.auto.lots.sca_auctions import search_sca_lots
from app.scrapers.auto.lots.openlane_scraper import search_openlane_lots

_SCRAPERS = {
    "copart": search_copart_lots,
    "iaai": search_iaai_lots,
    "sca": search_sca_lots,
    "openlane": search_openlane_lots,
}


def _within_hours(kw: AutoLotKeyword) -> bool:
    if kw.active_hours_start is None or kw.active_hours_end is None:
        return True
    h = datetime.now().hour
    s, e = kw.active_hours_start, kw.active_hours_end
    return (s <= h < e) if s <= e else (h >= s or h < e)


def _build_query(kw: AutoLotKeyword) -> str:
    """Toate scraperele de loturi cauta pe `query` (text liber). Filtrele fine
    (an/dauna/bid/stat) le aplicam local pe rezultate — vezi _lot_matches_keyword."""
    return " ".join(x for x in [kw.make, kw.model] if x).strip()


def _parse_auction_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _lot_matches_keyword(lot: dict, kw: AutoLotKeyword) -> bool:
    """Filtrare locala pe campurile care nu se pot pasa uniform la scraper."""
    y = lot.get("year")
    if kw.year_from and y and y < kw.year_from:
        return False
    if kw.year_to and y and y > kw.year_to:
        return False
    if kw.damage_primary:
        if kw.damage_primary.lower() not in (lot.get("damage_primary") or "").lower():
            return False
    if kw.location_state:
        if kw.location_state.lower() not in (lot.get("location_state") or "").lower():
            return False
    if kw.bid_max is not None and lot.get("current_bid") is not None:
        try:
            if float(lot["current_bid"]) > float(kw.bid_max):
                return False
        except (TypeError, ValueError):
            pass
    return True


def _save_lot(db: Session, user_id: int, keyword_id: int, raw: dict) -> bool:
    """Persista un lot nou. Dedup pe (user, platform, <cheie>), in ordinea stabilitatii:
    lot_number > source_url real (http) > (title, year). Fallback-ul pe title+year e
    necesar pentru scraperele publice fara identificator: IAAI intoarce lot_number=None
    si source_url='JavaScript:void(0)' (identic pe toate loturile) — fara fallback,
    toate cele 30 s-ar prabusi intr-un singur rand.
    Pe lot deja vazut NU face un `continue` orb: actualizeaza campurile volatile
    (bid/buy-now/data licitatie) + last_seen_at (evitam bug-ul din radar_scanner)."""
    platform = raw.get("platform")
    now = datetime.now(timezone.utc)

    raw_url = (raw.get("source_url") or "").strip()
    source_url = raw_url if raw_url.startswith("http") else None  # ignora placeholder gen JavaScript:void(0)
    lot_number = raw.get("lot_number")
    title = (raw.get("title") or "").strip()

    base = db.query(AutoLot).filter(
        AutoLot.user_id == user_id, AutoLot.platform == platform)
    if lot_number:
        existing = base.filter(AutoLot.lot_number == lot_number).first()
    elif source_url:
        existing = base.filter(AutoLot.source_url == source_url).first()
    elif title:
        q = base.filter(func.lower(AutoLot.title) == title.lower())
        if raw.get("year"):
            q = q.filter(AutoLot.year == raw.get("year"))
        existing = q.first()
    else:
        # Niciun identificator (nici titlu) → sarim (altfel spam la fiecare scan).
        return False

    if existing:
        existing.last_seen_at = now
        if raw.get("current_bid") is not None:
            existing.current_bid = raw.get("current_bid")
        if raw.get("buy_now_price") is not None:
            existing.buy_now_price = raw.get("buy_now_price")
        if raw.get("auction_date"):
            existing.auction_date = _parse_auction_date(raw.get("auction_date"))
        db.commit()
        return False

    lot = AutoLot(
        user_id=user_id,
        keyword_id=keyword_id,
        platform=platform,
        lot_number=lot_number,
        title=raw.get("title"),
        make=raw.get("make"),
        model=raw.get("model"),
        year=raw.get("year"),
        odometer=raw.get("odometer"),
        damage_primary=raw.get("damage_primary"),
        damage_secondary=raw.get("damage_secondary"),
        location_city=raw.get("location_city"),
        location_state=raw.get("location_state"),
        auction_date=_parse_auction_date(raw.get("auction_date")),
        thumbnail_url=raw.get("thumbnail_url"),
        source_url=source_url,
        current_bid=raw.get("current_bid"),
        buy_now_price=raw.get("buy_now_price"),
        title_type=raw.get("title_type"),
        starts=raw.get("starts"),
        drives=raw.get("drives"),
        keys_present=raw.get("keys_present"),
        vin=raw.get("vin"),
        status="active",
        saved=False,
        last_seen_at=now,
    )
    db.add(lot)
    db.commit()
    return True


def _notify_lot(db: Session, kw: AutoLotKeyword, raw: dict) -> None:
    """Notificare Discord pentru un lot nou (daca kw.notify_discord).

    send_auto_notification NU se potriveste pe loturi: are early-return pentru
    grade not in (A, B), iar loturile nu au scoring/grade. Construim deci un embed
    minimal si il punem direct in coada Discord (module="auto_lots")."""
    if kw.notify_discord:
        try:
            from app.models.radar_settings import RadarSettings
            from app.services.discord_service import discord_service
            settings = db.query(RadarSettings).filter(
                RadarSettings.user_id == kw.user_id).first()
            # NU folosim `return` aici: ar sari peste blocul de email de mai jos.
            webhook = ((getattr(settings, "discord_webhook_auto_all", None)
                        or getattr(settings, "discord_webhook_auto", None))
                       if settings else None)
            if webhook:
                title = (raw.get("title")
                         or " ".join(str(x) for x in [raw.get("year"), raw.get("make"), raw.get("model")] if x)
                         or "Lot nou")
                fields = []
                if raw.get("current_bid") is not None:
                    fields.append({"name": "💰 Bid curent", "value": f"${raw['current_bid']}", "inline": True})
                if raw.get("damage_primary"):
                    fields.append({"name": "🔧 Daună", "value": str(raw["damage_primary"]), "inline": True})
                loc = " · ".join(x for x in [raw.get("location_city"), raw.get("location_state")] if x)
                if loc:
                    fields.append({"name": "📍 Locație", "value": loc, "inline": True})
                fields.append({"name": "🏷️ Platformă", "value": (raw.get("platform") or "").upper(), "inline": True})
                fields.append({"name": "🎯 Keyword", "value": kw.name, "inline": True})

                embed = {
                    "title": f"🚗 {title[:200]}",
                    "color": 0x2563eb,
                    "fields": fields,
                    "footer": {"text": "FlipRadar · Loturi Auto"},
                }
                if raw.get("source_url"):
                    embed["url"] = raw["source_url"]

                lot_id = raw.get("lot_number") or raw.get("source_url") or title
                discord_service.enqueue(
                    webhook_url=webhook, embed=embed,
                    listing_id=f"autolot_{kw.platform}_{lot_id}",
                    module="auto_lots", grade=None, mention_here=False,
                    image_url=raw.get("thumbnail_url"),
                )
        except Exception as exc:
            log_manager.emit("auto_lots", "WARN", f"Notificare Discord lot esuata: {str(exc)[:80]}")

    if kw.notify_email:
        try:
            from app.models.user import User
            from app.services.email_service import is_configured as smtp_configured, send_email
            user = db.query(User).filter(User.id == kw.user_id).first()
            if user and user.email and smtp_configured():
                _send_email_alert_lot(user, kw, raw, send_email)
        except Exception as exc:
            log_manager.emit("auto_lots", "WARN",
                f"Email lot esuat: {str(exc)[:80]}")


def _send_email_alert_lot(user, kw, raw, send_email) -> None:
    title = (raw.get("title")
             or " ".join(str(x) for x in [raw.get("year"), raw.get("make"), raw.get("model")] if x)
             or "Lot nou")
    subject = f"[Loturi Auto] {title[:60]}"
    body = (
        f"Salut!\n\n"
        f"Un lot nou a fost detectat.\n"
        f"Keyword: {kw.name}\n"
        f"Titlu: {title}\n"
        f"Bid curent: {raw.get('current_bid') or '—'}\n"
        f"Daune: {raw.get('damage_primary') or '—'}\n"
        f"Link: {raw.get('source_url') or '—'}\n"
        f"\n-- FlipRadar Loturi"
    )
    send_email(user.email, subject, body)


def run_auto_lot_scan_for_user(db: Session, user_id: int) -> dict:
    """Scaneaza toate keyword-urile active de loturi ale unui SINGUR user.
    Returneaza {"new_lots": int, "keywords_scanned": int}."""
    stats = {"new_lots": 0, "keywords_scanned": 0}
    keywords = db.query(AutoLotKeyword).filter(
        AutoLotKeyword.user_id == user_id,
        AutoLotKeyword.is_active == True,
    ).all()
    if not keywords:
        return stats

    log_manager.emit("auto_lots", "SCAN",
        f"Scan loturi pornit: {len(keywords)} keyword-uri (user {user_id})")

    for kw in keywords:
        if not _within_hours(kw):
            log_manager.emit("auto_lots", "INFO", f"Skip {kw.name!r} — interval orar inactiv")
            continue
        scraper = _SCRAPERS.get((kw.platform or "").lower())
        if not scraper:
            log_manager.emit("auto_lots", "WARN", f"Platforma necunoscuta: {kw.platform}")
            continue

        query = _build_query(kw)
        try:
            results = asyncio.run(scraper(query, {})) or []
        except Exception as exc:
            log_manager.emit("auto_lots", "ERR", f"{kw.platform} eroare: {str(exc)[:100]}")
            results = []

        new_for_kw = 0
        for raw in results:
            if not _lot_matches_keyword(raw, kw):
                continue
            try:
                if _save_lot(db, user_id, kw.id, raw):
                    new_for_kw += 1
                    stats["new_lots"] += 1
                    _notify_lot(db, kw, raw)
            except Exception as exc:
                db.rollback()
                log_manager.emit("auto_lots", "ERR", f"Salvare lot esuata: {str(exc)[:80]}")

        kw.last_scan_at = datetime.now(timezone.utc)
        db.commit()
        stats["keywords_scanned"] += 1
        log_manager.emit("auto_lots", "OK",
            f"{kw.platform}: {len(results)} loturi · {new_for_kw} noi ({kw.name})")

    return stats


def run_auto_lot_scan_global(db: Session) -> None:
    """Apelat de APScheduler la fiecare 15 min. Itereaza toti userii cu keyword-uri
    active si deleaga per-user (la fel ca _scan_user vs run_radar_scan)."""
    user_ids = {
        row[0] for row in db.query(AutoLotKeyword.user_id)
        .join(User, AutoLotKeyword.user_id == User.id)
        .filter(AutoLotKeyword.is_active == True, User.is_active == True).distinct().all()
    }
    if not user_ids:
        return
    total_new = 0
    for uid in user_ids:
        try:
            stats = run_auto_lot_scan_for_user(db, uid)
            total_new += stats["new_lots"]
        except Exception as exc:
            print(f"[AutoLotScan] eroare user {uid}: {exc}")
            try:
                db.rollback()
            except Exception:
                pass
    log_manager.emit("auto_lots", "OK", f"Scan global loturi: {total_new} loturi noi")
