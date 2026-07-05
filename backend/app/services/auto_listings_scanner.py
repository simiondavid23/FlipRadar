"""Periodic scanner for auto_keywords — similar to radar_scanner."""
import random
import time
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.auto_keyword import AutoKeyword
from app.models.auto_feed_listing import AutoFeedListing
from app.services.auto_scorer import (
    compute_score, compute_import_costs, IMPORT_PLATFORMS, _fetch_market_avg)
from app.services.log_manager import log_manager
from app.services.ml.feed_ml_bridge import try_save_to_ml

_CURRENT_YEAR = 2026

# MODULE 3 — delay (secunde) intre paginile aceleiasi platforme la paginare.
# MODIFICARE 6 — interval (min, max) per platforma; delay aleator in interval ca
# sa nu existe un pattern temporal fix detectabil ca bot.
_AUTO_PLATFORM_DELAY_RANGES: dict[str, tuple[float, float]] = {
    "autovit":            (0.5, 1.3),
    "olx_auto":           (0.3, 0.9),
    "mobile_de":          (0.8, 1.8),
    "autoscout24":        (0.8, 1.8),
    "facebook_auto":      (1.5, 3.5),
    "kleinanzeigen_auto": (0.7, 1.5),
}


def _auto_platform_delay(platform: str) -> float:
    """Returnează un delay aleator în intervalul platformei (anti bot-detection)."""
    lo, hi = _AUTO_PLATFORM_DELAY_RANGES.get((platform or "").lower(), (0.5, 1.5))
    return random.uniform(lo, hi)


def _within_hours(kw: AutoKeyword) -> bool:
    if kw.active_hours_start is None or kw.active_hours_end is None:
        return True
    h = datetime.now().hour
    s, e = kw.active_hours_start, kw.active_hours_end
    return (s <= h < e) if s <= e else (h >= s or h < e)


def _market_avg(db: Session, user_id: int, make: str,
                year_from: int, year_to: int) -> Optional[float]:
    """Compute average RON price for similar listings already in DB."""
    try:
        rows = db.query(AutoFeedListing).filter(
            AutoFeedListing.user_id == user_id,
            AutoFeedListing.platform == "autovit",
            AutoFeedListing.price.isnot(None),
        ).all()
        vals = []
        for r in rows:
            if r.year and year_from <= r.year <= year_to:
                p = float(r.price or 0)
                if r.currency == "EUR":
                    from app.services.bnr_exchange import get_eur_ron
                    p *= get_eur_ron()
                if p > 500:
                    vals.append(p)
        return sum(vals) / len(vals) if len(vals) >= 5 else None
    except Exception:
        return None


def _call_scraper(kw: AutoKeyword, page: int = 1) -> list:
    """Dispatch to the correct platform scraper for a given page."""
    import asyncio

    platform = kw.platform
    filters = {
        "year_min":  kw.year_from,
        "year_max":  kw.year_to,
        "km_max":    kw.km_max,
        "price_max": float(kw.price_max) if kw.price_max else None,
        "fuel":      kw.fuel_type,
        "gearbox":   kw.transmission,
        "body":      kw.body_type,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    # Categoria salvata pe keyword -> path-ul de cautare al scraperului (validata in scraper).
    if getattr(kw, "category", None):
        filters["category"] = kw.category
    # Filtre tehnice confirmate salvate pe keyword (JSON) — cheile sunt numele campurilor
    # (fuel_type, engine_capacity_min/max, condition, seller_type, engine_power_min,
    # drivetrain, power_unit, ...). Scraperele le aplica prin apply_confirmed_filters.
    if getattr(kw, "tech_filters", None):
        filters.update({k: v for k, v in kw.tech_filters.items() if v not in (None, "")})

    try:
        if platform == "autovit":
            from app.scrapers.auto.listings.autovit_scraper import search_autovit
            return asyncio.run(search_autovit(
                make=kw.make or "", filters={**filters, "model": kw.model or ""}, page=page))

        elif platform == "olx_auto":
            from app.scrapers.auto.listings.olx_auto import search_olx_auto
            query = " ".join(x for x in [kw.make, kw.model, kw.query] if x)
            return asyncio.run(search_olx_auto(query=query, filters=filters, page=page))

        elif platform == "mobile_de":
            from app.scrapers.auto.listings.mobile_de_scraper import search_mobile_de
            return asyncio.run(search_mobile_de(
                make_id=kw.make or "", filters=filters, page=page))

        elif platform == "autoscout24":
            from app.scrapers.auto.listings.autoscout24_scraper import search_autoscout24
            return asyncio.run(search_autoscout24(
                make=kw.make or "", filters=filters, page=page))

        elif platform == "facebook_auto":
            # Scraper SINCRON (sync_playwright) — apelat direct, NU prin asyncio.run
            # (sync_playwright nu poate rula intr-un event loop asyncio).
            from app.scrapers.auto.listings.facebook_auto_scraper import search_facebook_auto
            query = " ".join(x for x in [kw.make, kw.model, kw.query] if x)
            return search_facebook_auto(query=query, filters=filters, page=page)

        elif platform == "kleinanzeigen_auto":
            from app.scrapers.auto.listings.kleinanzeigen_auto import search_kleinanzeigen_auto
            return asyncio.run(search_kleinanzeigen_auto(
                query=kw.query or "", make=kw.make or "", filters=filters, page=page))

    except Exception as exc:
        log_manager.emit("auto_listings", "ERR",
            f"{platform} pagina {page} eroare: {str(exc)[:100]}")
    return []


def _save_listing(db: Session, user_id: int, keyword_id: int,
                  raw: dict, platform: str,
                  market_avg_ron: Optional[float],
                  make: Optional[str] = None,
                  model: Optional[str] = None) -> bool:
    """Persist new listing. Returns True if new (not seen before)."""
    ext_id = (raw.get("external_id") or raw.get("platform_id") or "").strip()
    if not ext_id:
        return False

    existing = db.query(AutoFeedListing).filter(
        AutoFeedListing.user_id == user_id,
        AutoFeedListing.platform == platform,
        AutoFeedListing.external_id == ext_id,
    ).first()
    if existing:
        existing.last_checked_at = datetime.now(timezone.utc)
        db.commit()
        return False

    price  = float(raw.get("price") or raw.get("pret") or 0) or None
    cur    = (raw.get("currency") or raw.get("moneda") or "RON").upper()
    year   = raw.get("year")
    km     = raw.get("km")
    title  = raw.get("title") or raw.get("titlu") or ""

    # MODIFICARE 8 — daca nu avem o medie de piata keyword-level, o calculam dinamic
    # per-listing (marca din titlu, an ±2) ca referinta de scoring.
    if market_avg_ron is None and db is not None:
        market_avg_ron = _fetch_market_avg(
            make=raw.get("make") or make,
            model=raw.get("model") or model,
            year=year,
            db=db,
        )

    score, grade = compute_score(price, cur, year, km, title, market_avg_ron)

    import_json = None
    if platform in IMPORT_PLATFORMS and price and cur == "EUR":
        import_json = compute_import_costs(price, market_avg_ron)

    listing = AutoFeedListing(
        user_id      = user_id,
        keyword_id   = keyword_id,
        platform     = platform,
        external_id  = ext_id,
        title        = title,
        price        = price,
        currency     = cur,
        year         = year,
        km           = km,
        fuel_type    = raw.get("engine_type") or raw.get("fuel_type"),
        transmission = raw.get("gearbox") or raw.get("transmission"),
        body_type    = raw.get("body_type"),
        location     = raw.get("locatie") or raw.get("location"),
        image_url    = raw.get("thumbnail_url") or raw.get("image_url") or "",
        images_json  = raw.get("images", []),
        url          = raw.get("source_url") or raw.get("url") or "",
        description  = raw.get("description", ""),
        score        = score,
        grade        = grade,
        import_score_json = import_json,
        found_at     = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    return True


def _notify(kw: AutoKeyword, saved_listing, db: Session):
    """Trimite notificare Discord (A/B) prin coada globala discord_service."""
    if saved_listing.grade not in ("A", "B"):
        return
    try:
        from app.models.radar_settings import RadarSettings
        from app.services.discord_service import send_auto_notification
        settings = db.query(RadarSettings).filter(
            RadarSettings.user_id == kw.user_id).first()
        if not (kw.notify_discord and settings):
            return
        listing_dict = {c.name: getattr(saved_listing, c.name)
                        for c in saved_listing.__table__.columns}
        listing_dict["price"] = float(saved_listing.price or 0)
        send_auto_notification(
            listing_dict, saved_listing.grade, saved_listing.score,
            kw.name, settings, f"auto_{saved_listing.id}", db)
    except Exception as exc:
        log_manager.emit("auto_listings", "WARN",
            f"Notificare Discord auto esuata: {str(exc)[:80]}")


def run_auto_scan(db: Session, user_id: Optional[int] = None) -> None:
    """Called by APScheduler every 10 minutes (global) sau din butonul „Scanează
    acum” cu user_id setat (atunci scaneaza DOAR keyword-urile acelui user)."""
    query = db.query(AutoKeyword).filter(AutoKeyword.is_active == True)
    if user_id is not None:
        query = query.filter(AutoKeyword.user_id == user_id)
    keywords = query.all()

    if not keywords:
        return

    log_manager.emit("auto_listings", "SCAN",
        f"Auto scan pornit: {len(keywords)} keyword-uri active")

    for kw in keywords:
        if not _within_hours(kw):
            log_manager.emit("auto_listings", "INFO",
                f"Skip {kw.name!r} — interval orar inactiv")
            continue

        log_manager.emit("auto_listings", "SCAN",
            f"Keyword {kw.name!r} · {kw.platform}")

        market_avg = _market_avg(
            db, kw.user_id,
            kw.make or "",
            kw.year_from or 1990,
            kw.year_to or _CURRENT_YEAR,
        )

        # MODULE 3 — paginare: aduna pagini pana cand una nu mai aduce anunturi noi.
        page = 1
        total_new = 0
        total_seen = 0
        while True:
            results = _call_scraper(kw, page=page)
            if not results:
                break
            total_seen += len(results)
            new_on_page = 0
            for r in results:
                is_new = _save_listing(
                    db, kw.user_id, kw.id, r, kw.platform, market_avg,
                    make=kw.make, model=kw.model)
                if is_new:
                    new_on_page += 1
                    total_new += 1
                    # Reload to get computed grade
                    ext = (r.get("external_id") or r.get("platform_id") or "")
                    saved = db.query(AutoFeedListing).filter(
                        AutoFeedListing.user_id == kw.user_id,
                        AutoFeedListing.platform == kw.platform,
                        AutoFeedListing.external_id == ext,
                    ).first()
                    if saved:
                        _notify(kw, saved, db)
                        # MODULE 5b — bridge ML: salveaza in market_listings daca
                        # titlul matchuieste o categorie. Erorile nu rup scanul auto.
                        try:
                            try_save_to_ml(
                                db=db,
                                title=saved.title or "",
                                price=float(saved.price or 0),
                                currency=getattr(saved, "currency", "EUR") or "EUR",
                                external_id=saved.external_id or str(saved.id),
                                platform=saved.platform,
                                source_url=getattr(saved, "url", "") or "",
                                thumbnail_url=getattr(saved, "image_url", "") or "",
                                description=getattr(saved, "description", "") or "",
                                year=getattr(saved, "year", None),
                                km=getattr(saved, "km", None),
                                fuel_type=getattr(saved, "fuel_type", None),
                                transmission=getattr(saved, "transmission", None),
                            )
                        except Exception:
                            pass

            log_manager.emit("auto_listings", "INFO",
                f"{kw.platform} pagina {page}: {len(results)} rezultate · {new_on_page} noi")
            # Facebook Auto deruleaza intern (infinite scroll) → o singura pagina.
            if kw.platform == "facebook_auto":
                break
            if new_on_page == 0:
                break
            page += 1
            # MODIFICARE 6 — delay aleator proaspăt la fiecare pagină (nu fix).
            time.sleep(_auto_platform_delay(kw.platform))

        log_manager.emit("auto_listings", "OK",
            f"{kw.platform}: {total_seen} rezultate · {total_new} noi")
