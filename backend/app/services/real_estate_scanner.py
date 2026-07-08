"""Periodic scanner for real_estate_keywords — 30 min interval.

Modelele noi sunt importate aliasate (RealEstateKeyword / RealEstateListing) catre
clasele distincte RealEstateMonitorKeyword / RealEstateMonitorListing, ca sa nu
existe coliziune cu modelul existent RealEstateListing (tabel real_estate_listing).
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword as RealEstateKeyword
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing
from app.models.user import User
from app.services.real_estate.extractor import extract_all, groq_extract
from app.services.real_estate.scorer import compute_re_score, get_zone_avg_ppm
from app.services.real_estate.zones import normalize_zone, retroactive_normalize
from app.services.log_manager import log_manager


def _within_hours(kw: RealEstateKeyword) -> bool:
    if kw.active_hours_start is None or kw.active_hours_end is None:
        return True
    h = datetime.now().hour
    s, e = kw.active_hours_start, kw.active_hours_end
    return (s <= h < e) if s <= e else (h >= s or h < e)


def _is_groq_enabled(db: Session, user_id: int) -> bool:
    try:
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        cfg = getattr(user, "ai_features_config", None) or {}
        return cfg.get("ai_radar_review", True) is not False
    except Exception:
        return True


def _call_scraper(kw: RealEstateKeyword) -> list:
    import asyncio
    platform = kw.platform
    # Cheile TREBUIE sa fie cele CITITE de scrapere (tip_anunt/tip_proprietate/pret_*/
    # camere_min/suprafata_*/locatie), NU numele coloanelor din model. Inainte scanner-ul
    # trimitea property_type/rooms/price_max (nepotrivite) -> filtrele nu ajungeau niciodata
    # la scrapere. tip_anunt/price_min sunt campuri noi pe keyword (vezi migrarea).
    filters = {
        "tip_anunt": kw.tip_anunt or "vanzare",
        "tip_proprietate": kw.property_type,
        "pret_min": int(float(kw.price_min)) if kw.price_min else None,
        "pret_max": int(float(kw.price_max)) if kw.price_max else None,
        "camere_min": kw.rooms,
        "suprafata_min": kw.area_min,
        "suprafata_max": kw.area_max,
        "locatie": kw.zone or kw.city,
        "query": kw.query,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    try:
        if platform == "olx":
            # search_olx_real_estate(filters) — NU primeste query; il punem in filters.
            from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
            if kw.query:
                filters["query"] = kw.query
            return asyncio.run(search_olx_real_estate(filters=filters))
        elif platform == "storia":
            from app.scrapers.real_estate.storia_scraper import search_storia
            return asyncio.run(search_storia(filters=filters))
        elif platform == "imobiliare_ro":
            from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro
            return asyncio.run(search_imobiliare_ro(filters=filters))
        elif platform == "facebook_marketplace":
            # Scraper SINCRON (sync_playwright, sesiune storage_state) — apelat
            # direct, NU prin asyncio.run (sync_playwright nu merge in event loop).
            from app.scrapers.real_estate.facebook_real_estate import search_facebook_real_estate
            return search_facebook_real_estate(query=kw.query or "", filters=filters)
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"{platform} eroare: {str(exc)[:100]}")
    return []


def _save_listing(db: Session, kw: RealEstateKeyword,
                  raw: dict, groq_enabled: bool,
                  custom_aliases: dict) -> Optional[RealEstateListing]:
    ext_id = str(raw.get("external_id") or raw.get("platform_id") or "")
    if not ext_id:
        return None

    existing = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == kw.user_id,
        RealEstateListing.platform == kw.platform,
        RealEstateListing.external_id == ext_id,
    ).first()

    title = raw.get("title") or raw.get("titlu") or ""
    desc  = raw.get("description") or ""
    text  = f"{title} {desc}"

    if existing:
        # Price change detection
        new_price_raw = raw.get("price") or raw.get("pret")
        try:
            new_price = float(new_price_raw) if new_price_raw else None
        except Exception:
            new_price = None
        if new_price and existing.price:
            old_p = float(existing.price)
            if old_p > 0:
                drop = (old_p - new_price) / old_p
                if drop >= 0.05:
                    # Price dropped ≥5% → update and flag
                    history = list(existing.price_history or [])
                    history.append({
                        "price": old_p,
                        "currency": existing.currency,
                        "date": existing.last_checked_at.isoformat()
                        if existing.last_checked_at else None,
                    })
                    existing.price_history = history
                    existing.price = new_price
                    existing.price_per_sqm = (
                        round(new_price / existing.area_sqm, 2)
                        if existing.area_sqm else None)
                    existing.last_price_change_at = datetime.now(timezone.utc)
                    log_manager.emit("real_estate", "WARN",
                        f"Preț scăzut {drop*100:.0f}%: {title[:60]}")
        existing.last_checked_at = datetime.now(timezone.utc)
        db.commit()
        return None  # not new

    # Extract structured data
    extracted = extract_all(text)
    if not extracted.get("price"):
        price_raw = raw.get("price") or raw.get("pret")
        if price_raw:
            try:
                extracted["price"] = float(price_raw)
                extracted["currency"] = raw.get("currency", "EUR")
            except Exception:
                pass

    extracted = groq_extract(text, extracted, groq_enabled)

    # Zone normalization
    zone_raw = (extracted.get("zone_raw") or raw.get("location")
                or raw.get("zone") or "")
    zone_norm = normalize_zone(zone_raw, kw.city, custom_aliases)

    # Scoring
    zone_avg = get_zone_avg_ppm(
        db, RealEstateListing, kw.user_id,
        kw.city, zone_norm,
        extracted.get("rooms"), tip_anunt=kw.tip_anunt)
    price = extracted.get("price") or (float(raw.get("price") or 0) or None)
    currency = extracted.get("currency", "EUR")
    score, grade = (50, "C")
    if price and extracted.get("area_sqm"):
        score, grade = compute_re_score(
            price, currency, extracted["area_sqm"],
            extracted.get("rooms"), zone_norm, kw.city, zone_avg, tip_anunt=kw.tip_anunt)

    listing = RealEstateListing(
        user_id         = kw.user_id,
        keyword_id      = kw.id,
        platform        = kw.platform,
        external_id     = ext_id,
        source          = "platform",
        title           = title[:500],
        price           = price,
        currency        = currency,
        price_per_sqm   = extracted.get("price_per_sqm"),
        property_type   = raw.get("property_type") or kw.property_type,
        rooms           = extracted.get("rooms"),
        area_sqm        = extracted.get("area_sqm"),
        floor           = extracted.get("floor"),
        zone_raw        = zone_raw[:200] if zone_raw else None,
        zone_normalized = zone_norm,
        city            = kw.city,
        furnished       = extracted.get("furnished"),
        image_url       = raw.get("thumbnail_url") or raw.get("image_url") or "",
        images_json     = raw.get("images", []),
        url             = raw.get("source_url") or raw.get("url") or "",
        # Vanzator (cand scraperul il ofera) — folosit pentru afisare in feed/export.
        seller_id       = raw.get("seller_id") or raw.get("owner_id") or None,
        description     = desc[:2000],
        score           = score,
        grade           = grade,
        found_at        = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return listing


def _parse_floor(val) -> Optional[int]:
    """Parseaza etajul extras (string liber) intr-un int comparabil; None daca nu se poate.

    "parter"/"demisol" -> 0, "3" -> 3, "3/10" -> 3. "mansarda"/"ultim"/altele necunoscute
    -> None (nu putem compara, deci nu respingem pe baza etajului)."""
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    if s.startswith("parter") or s.startswith("demisol"):
        return 0
    m = re.match(r"(\d{1,2})", s)
    if m:
        return int(m.group(1))
    return None


def _matches_re_keyword(extracted: dict, kw: RealEstateKeyword) -> bool:
    """True daca valorile extrase NU contrazic criteriile keyword-ului.

    TOLERANTA: un criteriu setat pe kw dar cu valoare extrasa necunoscuta (None) e tratat
    ca "nu se poate verifica" -> NU respinge. Respinge DOAR cand ambele valori exista si se
    contrazic clar. `property_type`, `tip_anunt` si `city` nu sunt produse de extractor, deci
    nu pot fi verificate din text (raman necontrolate).
    """
    # Pret — doar cand monedele coincid (altfel comparatia numerica ar fi eronata).
    price = extracted.get("price")
    if price is not None:
        ext_cur = (extracted.get("currency") or "EUR").upper()
        kw_cur = (kw.price_currency or "EUR").upper()
        if ext_cur == kw_cur:
            try:
                p = float(price)
                if kw.price_min is not None and p < float(kw.price_min):
                    return False
                if kw.price_max is not None and p > float(kw.price_max):
                    return False
            except (TypeError, ValueError):
                pass

    # Camere — kw.rooms e MINIM (la fel ca filtrul trimis scraperelor: camere_min).
    rooms = extracted.get("rooms")
    if rooms is not None and kw.rooms is not None:
        try:
            if int(rooms) < int(kw.rooms):
                return False
        except (TypeError, ValueError):
            pass

    # Suprafata (min/max).
    area = extracted.get("area_sqm")
    if area is not None:
        try:
            a = float(area)
            if kw.area_min is not None and a < float(kw.area_min):
                return False
            if kw.area_max is not None and a > float(kw.area_max):
                return False
        except (TypeError, ValueError):
            pass

    # Etaj (min/max) — doar cand etajul extras e parsabil intr-un numar.
    floor = _parse_floor(extracted.get("floor"))
    if floor is not None:
        if kw.floor_min is not None and floor < kw.floor_min:
            return False
        if kw.floor_max is not None and floor > kw.floor_max:
            return False

    # Mobilat (bool) — ambele cunoscute si diferite -> respinge.
    furnished = extracted.get("furnished")
    if kw.furnished is not None and furnished is not None:
        if bool(kw.furnished) != bool(furnished):
            return False

    # Zona (substring, lax) — respinge doar cand ambele exista si nu se suprapun deloc.
    kw_zone = (kw.zone or "").strip().lower()
    zn = (extracted.get("zone_normalized") or "").strip().lower()
    if kw_zone and zn and kw_zone not in zn and zn not in kw_zone:
        return False

    return True


def _save_fb_group_post(db: Session, post: dict, kw: RealEstateKeyword,
                        groq_enabled: bool,
                        custom_aliases: dict) -> Optional[RealEstateListing]:
    """Convert facebook_group_post -> real_estate_listing pentru un keyword anume.

    FIX confiscare: postarea se salveaza DOAR daca datele extrase se POTRIVESC criteriilor
    keyword-ului (_matches_re_keyword, cu toleranta). Inainte, primul keyword care rula
    salva ORICE postare si o "confisca"; acum o postare pe care kw1 n-o potriveste ramane
    disponibila pentru kw2 s.a.m.d.

    O postare fizica se salveaza O SINGURA DATA per user — exista o constrangere DB unica
    pe (user_id, platform, external_id) (idx_re_listings_external), deci NU o putem stoca de
    mai multe ori (cate una per keyword). O prinde primul keyword care O POTRIVESTE; feed-ul
    nu arata duplicate ale aceleiasi postari sub keyword-uri diferite (cerinta de verificare).
    """
    ext_id = f"fbgroup_{post.get('id') or post.get('post_id','')}"
    if not ext_id or ext_id == "fbgroup_":
        return None

    # Deja salvata (de orice keyword al acestui user)? Constrangerea DB e pe user+platform+
    # external_id, deci verificam la fel — evitam un INSERT care ar crapa pe unicitate.
    existing = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == kw.user_id,
        RealEstateListing.external_id == ext_id,
    ).first()
    if existing:
        return None

    text = post.get("text") or ""
    extracted = extract_all(text)
    extracted = groq_extract(text, extracted, groq_enabled)

    zone_raw = extracted.get("zone_raw") or post.get("zona") or ""
    zone_norm = normalize_zone(zone_raw, kw.city, custom_aliases)

    # Filtru criterii — postarea se asociaza cu acest keyword DOAR daca valorile extrase
    # nu contrazic criteriile lui (zona normalizata e injectata pentru comparatie).
    extracted["zone_normalized"] = zone_norm
    if not _matches_re_keyword(extracted, kw):
        return None

    price = extracted.get("price") or (float(post.get("pret") or 0) or None)
    currency = extracted.get("currency", "EUR")
    score, grade = 50, "C"
    if price and extracted.get("area_sqm"):
        zone_avg = get_zone_avg_ppm(
            db, RealEstateListing, kw.user_id, kw.city, zone_norm,
            extracted.get("rooms"), tip_anunt=kw.tip_anunt)
        score, grade = compute_re_score(
            price, currency, extracted["area_sqm"],
            extracted.get("rooms"), zone_norm, kw.city, zone_avg, tip_anunt=kw.tip_anunt)

    listing = RealEstateListing(
        user_id         = kw.user_id,
        keyword_id      = kw.id,
        platform        = "facebook_groups",
        external_id     = ext_id,
        source          = "facebook_groups",
        title           = text[:200],
        price           = price,
        currency        = currency,
        price_per_sqm   = extracted.get("price_per_sqm"),
        rooms           = extracted.get("rooms"),
        area_sqm        = extracted.get("area_sqm"),
        floor           = extracted.get("floor"),
        zone_raw        = zone_raw[:200] if zone_raw else None,
        zone_normalized = zone_norm,
        city            = kw.city,
        furnished       = extracted.get("furnished"),
        url             = post.get("group_url") or "",
        description     = text[:2000],
        score           = score,
        grade           = grade,
        found_at        = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def run_real_estate_scan(db: Session, user_id: Optional[int] = None) -> None:
    query = db.query(RealEstateKeyword).join(User, RealEstateKeyword.user_id == User.id).filter(RealEstateKeyword.is_active == True, User.is_active == True)
    if user_id is not None:
        query = query.filter(RealEstateKeyword.user_id == user_id)
    keywords = query.all()
    if not keywords:
        return

    log_manager.emit("real_estate", "SCAN",
        f"Imobiliare scan: {len(keywords)} keyword-uri active")

    for kw in keywords:
        if not _within_hours(kw):
            log_manager.emit("real_estate", "INFO",
                f"Skip {kw.name!r} — interval orar inactiv")
            continue

        groq_enabled = _is_groq_enabled(db, kw.user_id)
        custom_aliases = {}
        settings = None
        try:
            from app.models.radar_settings import RadarSettings
            settings = db.query(RadarSettings).filter(
                RadarSettings.user_id == kw.user_id).first()
            if settings and settings.custom_zone_aliases:
                custom_aliases = dict(settings.custom_zone_aliases)
        except Exception:
            pass

        log_manager.emit("real_estate", "SCAN",
            f"Keyword {kw.name!r} · {kw.platform}")

        new_count = 0
        if kw.platform == "facebook_groups":
            # Pull unread posts from facebook_group_posts table
            try:
                from app.models.facebook_group_post import FacebookGroupPost
                from app.models.facebook_group_config import FacebookGroupConfig
                configs = db.query(FacebookGroupConfig).filter(
                    FacebookGroupConfig.user_id == kw.user_id,
                    FacebookGroupConfig.is_active == True,
                ).all()
                for cfg in configs:
                    # coloana FacebookGroupPost.created_at e naivă-UTC (default=datetime.utcnow);
                    # migrarea completă pe timezone-aware rămâne post-licență.
                    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)
                    posts = db.query(FacebookGroupPost).filter(
                        FacebookGroupPost.config_id == cfg.id,
                        FacebookGroupPost.created_at >= cutoff,
                    ).all()
                    for post in posts:
                        post_dict = {c.name: getattr(post, c.name)
                                     for c in post.__table__.columns}
                        saved = _save_fb_group_post(
                            db, post_dict, kw, groq_enabled, custom_aliases)
                        if saved:
                            new_count += 1
                            _notify_re(saved, kw, settings, db)
            except Exception as exc:
                log_manager.emit("real_estate", "ERR",
                    f"FB Groups ingest: {str(exc)[:80]}")
        else:
            results = _call_scraper(kw)
            for r in results:
                saved = _save_listing(db, kw, r, groq_enabled, custom_aliases)
                if saved:
                    new_count += 1
                    _notify_re(saved, kw, settings, db)

        log_manager.emit("real_estate", "OK",
            f"{kw.platform}: {new_count} anunțuri noi")


def _notify_re(listing: RealEstateListing, kw: RealEstateKeyword,
               settings, db: Session) -> None:
    if kw.notify_discord:
        try:
            from app.services.discord_service import send_imob_notification
            from app.services.real_estate.scorer import get_zone_avg_ppm
            zone_avg = get_zone_avg_ppm(
                db, RealEstateListing, kw.user_id,
                listing.city, listing.zone_normalized, listing.rooms, tip_anunt=kw.tip_anunt)
            listing_dict = {c.name: getattr(listing, c.name)
                            for c in listing.__table__.columns}
            listing_dict["price"] = float(listing.price or 0)
            send_imob_notification(
                listing_dict, listing.grade, listing.score,
                kw.name, settings, f"re_{listing.id}", db, zone_avg)
        except Exception as exc:
            log_manager.emit("real_estate", "WARN",
                f"Notificare Discord imob esuata: {str(exc)[:60]}")

    if listing.grade in ("A", "B") and kw.notify_email:
        try:
            from app.models.user import User
            from app.services.email_service import is_configured as smtp_configured, send_email
            user = db.query(User).filter(User.id == kw.user_id).first()
            if user and user.email and smtp_configured():
                _send_email_alert_re(user, kw, listing, send_email)
        except Exception as exc:
            log_manager.emit("real_estate", "WARN",
                f"Email imob esuat: {str(exc)[:60]}")


def _send_email_alert_re(user, kw, listing, send_email) -> None:
    subject = f"[Imobiliare] {listing.grade} — {(listing.title or '')[:60]}"
    body = (
        f"Salut!\n\n"
        f"Un anunt cu grad {listing.grade} a fost detectat pe {listing.platform}.\n"
        f"Keyword: {kw.name}\n"
        f"Titlu: {listing.title}\n"
        f"Zona: {listing.zone_normalized or listing.city or '—'}\n"
        f"Camere: {listing.rooms or '—'} · Suprafata: {listing.area_sqm or '—'} mp\n"
        f"Pret: {listing.price} {listing.currency or 'EUR'}\n"
        f"Link: {listing.url}\n"
        f"\n-- FlipRadar Imobiliare"
    )
    send_email(user.email, subject, body)


def run_cleanup(db: Session) -> int:
    """Daily cleanup: HEAD check URLs, remove 404, flag price drops."""
    import requests as req
    listings = db.query(RealEstateListing).filter(
        RealEstateListing.status == "active",
        RealEstateListing.platform != "facebook_groups",
        RealEstateListing.url.isnot(None),
    ).limit(200).all()

    deleted = 0
    for listing in listings:
        try:
            resp = req.head(listing.url, timeout=8, allow_redirects=True)
            if resp.status_code in (404, 410):
                db.delete(listing)
                deleted += 1
            else:
                listing.last_checked_at = datetime.now(timezone.utc)
        except Exception:
            pass

    db.commit()
    if deleted:
        log_manager.emit("real_estate", "WARN",
            f"Cleanup: {deleted} anunțuri dispărute șterse")
    return deleted
