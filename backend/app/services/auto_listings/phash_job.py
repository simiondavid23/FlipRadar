"""Job orar de fundal: calculeaza pHash + histograma de culoare pentru anunturile auto
care inca nu le au. Mirror exact pe services/real_estate/phash_job.py."""
from sqlalchemy.orm import Session
from app.services.log_manager import log_manager


def run_auto_phash_job(db: Session) -> None:
    try:
        from app.models.auto_feed_listing import AutoFeedListing
        from app.services.shared.image_hash import compute_phash, compute_color_hist
        from app.services.auto_listings.duplicate_detector import check_auto_duplicates

        pending = db.query(AutoFeedListing).filter(
            AutoFeedListing.phash.is_(None),
            AutoFeedListing.image_url.isnot(None),
            AutoFeedListing.image_url != "",
        ).limit(50).all()

        if not pending:
            return

        log_manager.emit("auto_listings", "SCAN",
            f"pHash job auto: procesare {len(pending)} listinguri")

        updated = 0
        for listing in pending:
            ph = compute_phash(listing.image_url)
            ch = compute_color_hist(listing.image_url)
            if ph:
                listing.phash = ph
                listing.color_hist = ch
                level, group_id, matched = check_auto_duplicates(
                    listing, db, listing.user_id)
                if level in (1, 2) and group_id:
                    listing.duplicate_group_id = group_id
                    listing.duplicate_level = level
                    if matched:
                        listing.duplicate_match_id = matched.id
                        if not matched.duplicate_group_id:
                            matched.duplicate_group_id = group_id
                            matched.duplicate_level = level
                elif level == 3 and matched:
                    listing.duplicate_level = 3
                    listing.duplicate_match_id = matched.id
                updated += 1

        db.commit()
        log_manager.emit("auto_listings", "OK",
            f"pHash job auto: {updated} listinguri procesate")
    except Exception as exc:
        log_manager.emit("auto_listings", "ERR",
            f"pHash job auto eroare: {str(exc)[:100]}")
        db.rollback()
