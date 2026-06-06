"""Orchestratorul Radar Marketplace.

Ruleaza ca job APScheduler la fiecare 5 minute. Pentru fiecare user activ:
- itereaza keyword-urile active si poll-uieste platformele activate
- filtreaza listingurile deja vazute si vanzatorii blocati
- calculeaza scor + marja, sare peste cele filtrate
- salveaza listing-ul, ruleaza AI review (Groq), trimite alerte Discord + email + in-app

Scraperele ruleaza SECVENTIAL ca sa nu fie blocate de WAF-uri ca trafic abuziv.
La fiecare 10 cicluri se ruleaza cleanup-ul (mark sold/removed).
"""
import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.notification import Notification
from app.models.radar_blocked_seller import RadarBlockedSeller
from app.models.radar_keyword import RadarKeyword
from app.models.radar_listing import RadarListing
from app.models.radar_seen_id import RadarSeenId
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services.email_service import is_configured as smtp_configured, send_email
from app.services.push_service import is_push_configured, notify_user_push
from app.services.radar.ai_reviewer import generate_ai_review
from app.services.radar.cleanup_service import cleanup_sold_listings
from app.services.radar.discord_service import route_discord_alerts
from app.services.radar.autovit_scraper import search_autovit
from app.services.radar.facebook_scraper import search_facebook
from app.services.radar.lajumate_scraper import search_lajumate
from app.services.radar.mobilede_scraper import search_mobilede
from app.services.radar.okazii_scraper import search_okazii
from app.services.radar.olx_scraper import search_olx
from app.services.radar.publi24_scraper import search_publi24
from app.services.radar.scorer import calculate_score
from app.services.radar.vinted_scraper import search_vinted


# Contor global pentru frecventa cleanup-ului (ruleaza la fiecare 10 cicluri).
_cycle_counter = {"n": 0}

# Delay intre scraping-urile platformelor pentru a evita blocaje.
_PLATFORM_DELAY_RANGE = (1.5, 3.5)


# Seturi globale partajate cu router-ul: cand userul dezactiveaza/sterge un
# keyword in timp ce scanul ruleaza, marcam id-ul aici si bucla principala
# verifica la fiecare iteratie ca sa iasa imediat.
_cancelled_keyword_ids: set[int] = set()
_deleted_keyword_ids: set[int] = set()


def cancel_keyword_scan(keyword_id: int) -> None:
    _cancelled_keyword_ids.add(int(keyword_id))


def restore_keyword_scan(keyword_id: int) -> None:
    _cancelled_keyword_ids.discard(int(keyword_id))


def mark_keyword_deleted(keyword_id: int) -> None:
    _deleted_keyword_ids.add(int(keyword_id))


def _is_keyword_cancelled(keyword_id: int) -> bool:
    return keyword_id in _cancelled_keyword_ids or keyword_id in _deleted_keyword_ids


def _parse_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    return []


def _get_or_create_settings(db: Session, user_id: int) -> RadarSettings:
    s = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
    if s:
        return s
    s = RadarSettings(user_id=user_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _platform_enabled_in_settings(platform: str, settings: RadarSettings) -> bool:
    p = (platform or "").lower()
    if p == "olx":
        return bool(settings.platform_olx_enabled)
    if p == "vinted":
        return bool(settings.platform_vinted_enabled)
    if p == "okazii":
        return bool(settings.platform_okazii_enabled)
    if p == "facebook":
        return bool(settings.platform_facebook_enabled)
    if p == "lajumate":
        return bool(getattr(settings, "platform_lajumate_enabled", True))
    if p == "publi24":
        return bool(getattr(settings, "platform_publi24_enabled", True))
    if p == "autovit":
        return bool(getattr(settings, "platform_autovit_enabled", True))
    if p == "mobilede":
        return bool(getattr(settings, "platform_mobilede_enabled", True))
    return False


def _should_scan_keyword(keyword: RadarKeyword) -> bool:
    """True daca intervalul de polling a expirat de la ultimul scan."""
    if keyword.last_scan_at is None:
        return True
    elapsed = datetime.now(timezone.utc) - keyword.last_scan_at.replace(tzinfo=timezone.utc) if keyword.last_scan_at.tzinfo is None else datetime.now(timezone.utc) - keyword.last_scan_at
    return elapsed >= timedelta(minutes=keyword.poll_interval_minutes or 5)


def _run_scraper(
    platform: str,
    keyword: RadarKeyword,
    settings: RadarSettings,
    exclude_words: list[str],
) -> list[dict]:
    """Apel sincron la scraperul potrivit. Try/except per scraper ca un crash
    pe o platforma sa nu opreasca scanul pentru celelalte.
    """
    try:
        if platform == "olx":
            return search_olx(
                keyword=keyword.name,
                max_price=keyword.max_price,
                judet=keyword.judet,
                oras=keyword.oras,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                min_price=keyword.min_price,
                category=keyword.category,
            )
        if platform == "vinted":
            return search_vinted(
                keyword=keyword.name,
                max_price=keyword.max_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                cookie_str=settings.vinted_cookie,
                min_price=keyword.min_price,
                category=keyword.category,
            )
        if platform == "okazii":
            return search_okazii(
                keyword=keyword.name,
                max_price=keyword.max_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                min_price=keyword.min_price,
                category=keyword.category,
            )
        if platform == "facebook":
            return search_facebook(
                keyword=keyword.name,
                max_price=keyword.max_price,
                judet=keyword.judet,
                oras=keyword.oras,
                exclude_words=exclude_words,
                session_path=settings.facebook_session_path,
                min_price=keyword.min_price,
                category=keyword.category,
            )
        if platform == "lajumate":
            return search_lajumate(
                keyword=keyword.name,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                judet=keyword.judet,
                oras=keyword.oras,
            )
        if platform == "publi24":
            return search_publi24(
                keyword=keyword.name,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                condition=keyword.condition or "all",
                exclude_words=exclude_words,
                judet=keyword.judet,
                oras=keyword.oras,
            )
        if platform in ("autovit", "mobilede"):
            try:
                car_filters_dict = json.loads(keyword.car_filters) if keyword.car_filters else None
            except (json.JSONDecodeError, TypeError):
                car_filters_dict = None
            if platform == "autovit":
                return search_autovit(
                    keyword=keyword.name,
                    max_price=keyword.max_price,
                    min_price=keyword.min_price,
                    exclude_words=exclude_words,
                    car_filters=car_filters_dict,
                )
            return search_mobilede(
                keyword=keyword.name,
                max_price=keyword.max_price,
                min_price=keyword.min_price,
                exclude_words=exclude_words,
                car_filters=car_filters_dict,
            )
    except Exception as exc:
        print(f"[RadarScanner] Scraperul {platform} a crapat: {exc}")
    return []


def _is_blocked_seller(db: Session, user_id: int, platform: str, seller_id: Optional[str]) -> bool:
    if not seller_id:
        return False
    blocked = (
        db.query(RadarBlockedSeller)
        .filter(
            RadarBlockedSeller.user_id == user_id,
            RadarBlockedSeller.platform == platform,
            RadarBlockedSeller.seller_id == str(seller_id),
        )
        .first()
    )
    return blocked is not None


def _already_seen(db: Session, user_id: int, platform: str, external_id: str) -> bool:
    seen = (
        db.query(RadarSeenId)
        .filter(
            RadarSeenId.user_id == user_id,
            RadarSeenId.platform == platform,
            RadarSeenId.external_id == external_id,
        )
        .first()
    )
    return seen is not None


def _mark_seen(db: Session, user_id: int, platform: str, external_id: str) -> None:
    db.add(RadarSeenId(user_id=user_id, platform=platform, external_id=external_id))


def _make_ai_review(listing: dict, keyword: RadarKeyword, score: Optional[str]) -> str:
    """Wrapper sincron in jurul Groq (apelul de la ai_reviewer e sincron deja)."""
    try:
        return generate_ai_review(
            title=listing.get("title", ""),
            description=listing.get("description"),
            price=float(listing.get("price") or 0),
            resale_price=float(keyword.resale_price or 0),
            platform=listing.get("platform", "?"),
            score=score,
            condition=listing.get("condition"),
            location=listing.get("location"),
        )
    except Exception as exc:
        print(f"[RadarScanner] AI review esuat: {exc}")
        return ""


def _fmt_dt(dt) -> str:
    if not dt:
        return "Necunoscut"
    try:
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "Necunoscut"


def _send_email_alert(
    user: User,
    listing: dict,
    keyword: RadarKeyword,
    score: str,
    margin_pct: float,
    listed_at=None,
    found_at=None,
) -> None:
    if not smtp_configured() or not user.email:
        return
    subject = f"[Radar] {score} — {listing.get('title', '')[:60]}"
    body = (
        f"Salut!\n\n"
        f"Un deal cu scor {score} a fost detectat pe {listing.get('platform', '?')}.\n"
        f"Keyword: {keyword.name}\n"
        f"Titlu: {listing.get('title')}\n"
        f"Preț cerut: {listing.get('price')} {listing.get('currency', 'RON')}\n"
        f"Marjă estimată: {margin_pct:.0f}%\n"
        f"Postat pe platformă: {_fmt_dt(listed_at)}\n"
        f"Găsit de FlipRadar: {_fmt_dt(found_at)}\n"
        f"Link: {listing.get('url')}\n"
        f"\n-- FlipRadar Radar"
    )
    try:
        send_email(user.email, subject, body)
    except Exception as exc:
        print(f"[RadarScanner] Email esuat: {exc}")


def _create_inapp_notification(db: Session, user_id: int, listing_db: RadarListing, keyword: RadarKeyword) -> None:
    title = f"Radar [{listing_db.score or '?'}]: {listing_db.title[:60]}"
    message = (
        f"Anunț nou pe {listing_db.platform.upper()} pentru \"{keyword.name}\": "
        f"{listing_db.price} {listing_db.currency} "
        f"(marjă ~{int(listing_db.margin_pct or 0)}%)."
    )
    db.add(Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type="alert",
        link=f"/dashboard/radar?listing={listing_db.id}",
    ))


def _scan_user(db: Session, user: User) -> dict:
    """Scaneaza toate keyword-urile active ale unui user. Returneaza statistici."""
    stats = {"new_listings": 0, "alerts_sent": 0}
    settings = _get_or_create_settings(db, user.id)
    keywords = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.user_id == user.id, RadarKeyword.is_active == True)
        .all()
    )

    for kw in keywords:
        if _is_keyword_cancelled(kw.id):
            print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters — sare peste.")
            continue
        if not _should_scan_keyword(kw):
            continue

        platforms = _parse_json_list(kw.platforms)
        exclude_words = _parse_json_list(kw.exclude_words)

        cancelled_mid_loop = False
        for idx, platform in enumerate(platforms):
            if _is_keyword_cancelled(kw.id):
                print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters mid-scan — opresc.")
                cancelled_mid_loop = True
                break
            platform = (platform or "").lower()
            if not _platform_enabled_in_settings(platform, settings):
                continue
            if idx > 0:
                time.sleep(random.uniform(*_PLATFORM_DELAY_RANGE))

            listings = _run_scraper(platform, kw, settings, exclude_words)
            for listing in listings:
                if _is_keyword_cancelled(kw.id):
                    print(f"[RadarScanner] Keyword {kw.id} dezactivat/șters — opresc procesarea.")
                    cancelled_mid_loop = True
                    break
                try:
                    ext_id = listing.get("external_id")
                    if not ext_id:
                        continue
                    if _already_seen(db, user.id, platform, ext_id):
                        continue
                    if _is_blocked_seller(db, user.id, platform, listing.get("seller_id")):
                        continue

                    score_data = calculate_score(
                        listing_price=listing.get("price") or 0,
                        resale_price=kw.resale_price,
                        min_margin_pct=kw.min_margin_pct or 10.0,
                    )
                    if score_data["filtered"] and score_data["score"] is None:
                        # marja negativa — nici nu salvam, e zgomot
                        _mark_seen(db, user.id, platform, ext_id)
                        continue

                    _mark_seen(db, user.id, platform, ext_id)

                    ai_review = _make_ai_review(listing, kw, score_data["score"])

                    listing_db = RadarListing(
                        user_id=user.id,
                        keyword_id=kw.id,
                        external_id=ext_id,
                        platform=platform,
                        title=listing.get("title", "")[:500],
                        price=float(listing.get("price") or 0),
                        currency=listing.get("currency") or "RON",
                        condition=listing.get("condition"),
                        location=listing.get("location"),
                        url=listing.get("url", ""),
                        images=json.dumps(listing.get("images") or [], ensure_ascii=False),
                        description=listing.get("description"),
                        seller_name=listing.get("seller_name"),
                        seller_id=listing.get("seller_id"),
                        score=score_data["score"],
                        margin_pct=score_data["margin_pct"],
                        status="active",
                        ai_review=ai_review or None,
                        listed_at=listing.get("listed_at"),
                    )
                    db.add(listing_db)
                    db.flush()
                    stats["new_listings"] += 1

                    if not score_data["filtered"]:
                        # Discord doar daca keyword-ul are notify_discord activ
                        if getattr(kw, "notify_discord", True):
                            sent = route_discord_alerts(
                                settings=settings,
                                listing=listing,
                                keyword_name=kw.name,
                                score=score_data["score"],
                                resale_price=kw.resale_price,
                                margin_pct=score_data["margin_pct"],
                                listed_at=listing.get("listed_at"),
                                found_at=listing_db.found_at,
                            )
                            stats["alerts_sent"] += sent
                        # In-app intotdeauna (independent de setari)
                        _create_inapp_notification(db, user.id, listing_db, kw)
                        # Email doar daca scor A/B SI keyword-ul are notify_email activ
                        if score_data["score"] in ("A", "B") and getattr(kw, "notify_email", True):
                            _send_email_alert(
                                user, listing, kw,
                                score_data["score"], score_data["margin_pct"],
                                listed_at=listing.get("listed_at"),
                                found_at=listing_db.found_at,
                            )
                        # Web Push pentru deal-uri prioritare (A/B)
                        if score_data["score"] in ("A", "B") and is_push_configured():
                            try:
                                notify_user_push(
                                    db, user.id,
                                    title=f"[{score_data['score']}] {listing.get('title', '')[:50]}",
                                    body=(
                                        f"{int(listing.get('price') or 0)} RON · "
                                        f"Marjă {score_data['margin_pct']:.0f}% · "
                                        f"{platform} · {listing.get('location') or '—'}"
                                    ),
                                    url=f"/dashboard/radar?listing={listing_db.id}",
                                )
                            except Exception as exc:
                                print(f"[RadarScanner] Push esuat: {exc}")
                except Exception as exc:
                    print(f"[RadarScanner] Eroare la procesare listing: {exc}")
                    continue
            if cancelled_mid_loop:
                break

        # Daca keyword-ul a fost sters in timpul scanarii, nu mai actualizam
        # nimic in DB pentru el — rowul oricum dispare in cateva milisecunde.
        if kw.id in _deleted_keyword_ids:
            _deleted_keyword_ids.discard(kw.id)
            continue
        kw.last_scan_at = datetime.now(timezone.utc)
        db.commit()

    return stats


def run_radar_scan() -> None:
    """Punctul de intrare apelat de APScheduler la fiecare 5 minute."""
    print(f"[RadarScanner] Pornit la {datetime.now().strftime('%H:%M:%S')}")
    db: Session = SessionLocal()
    total_new = 0
    total_alerts = 0
    try:
        active_user_ids = {
            row[0] for row in db.query(RadarKeyword.user_id)
            .filter(RadarKeyword.is_active == True)
            .distinct().all()
        }
        if not active_user_ids:
            print("[RadarScanner] Niciun user cu keyword-uri active.")
            return

        users = db.query(User).filter(User.id.in_(active_user_ids), User.is_active == True).all()
        for user in users:
            try:
                stats = _scan_user(db, user)
                total_new += stats["new_listings"]
                total_alerts += stats["alerts_sent"]
            except Exception as exc:
                print(f"[RadarScanner] Eroare la scan user {user.id}: {exc}")
                try:
                    db.rollback()
                except Exception:
                    pass

        _cycle_counter["n"] += 1
        if _cycle_counter["n"] % 10 == 0:
            try:
                cleanup_sold_listings(db)
            except Exception as exc:
                print(f"[RadarScanner] Cleanup esuat: {exc}")

        print(f"[RadarScanner] Scan completat: {total_new} listinguri noi, {total_alerts} alerte trimise")
    except Exception as exc:
        print(f"[RadarScanner] EROARE NEASTEPTATA: {exc}")
        import traceback
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
