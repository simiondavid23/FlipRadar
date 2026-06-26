"""Hourly background job: compute pHash + color histogram for
real estate listings that don't have them yet."""
from sqlalchemy.orm import Session
from app.services.log_manager import log_manager


def run_phash_job(db: Session) -> None:
    try:
        # Model nou de monitorizare imobiliare (tabel real_estate_listings),
        # distinct de modelul existent RealEstateListing (real_estate_listing).
        from app.models.real_estate_monitor_listing import (
            RealEstateMonitorListing as RealEstateListing)
        from app.services.real_estate.duplicate_detector import (
            compute_phash, compute_color_hist, check_duplicates)

        pending = db.query(RealEstateListing).filter(
            RealEstateListing.phash.is_(None),
            RealEstateListing.image_url.isnot(None),
            RealEstateListing.image_url != "",
        ).limit(50).all()

        if not pending:
            return

        log_manager.emit("real_estate", "SCAN",
            f"pHash job: procesare {len(pending)} listinguri")

        updated = 0
        for listing in pending:
            ph = compute_phash(listing.image_url)
            ch = compute_color_hist(listing.image_url)
            if ph:
                listing.phash = ph
                listing.color_hist = ch
                level, group_id, matched = check_duplicates(
                    listing, db,
                    RealEstateListing, listing.user_id)
                if level in (1, 2) and group_id:
                    listing.duplicate_group_id = group_id
                    listing.duplicate_level = level
                    if matched and not matched.duplicate_group_id:
                        matched.duplicate_group_id = group_id
                        matched.duplicate_level = level
                elif level == 3 and matched:
                    listing.duplicate_level = 3
                updated += 1

        db.commit()
        log_manager.emit("real_estate", "OK",
            f"pHash job: {updated} listinguri procesate")
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"pHash job eroare: {str(exc)[:100]}")
        db.rollback()
