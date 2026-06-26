"""Cleanup periodic — marcheaza listinguri ca sold/removed.

Polling-ul HEAD/GET al URL-urilor vechi e single-threaded si rate-limited;
ruleaza la fiecare ~10 cicluri din orchestratorul principal, nu la fiecare scan.
"""
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from app.models.radar_listing import RadarListing
from app.services.radar.base_scraper import build_headers
from app.services.log_manager import log_manager


_SOLD_MARKERS = {
    "olx": ["anunț expirat", "anunt expirat", "anunțul a fost șters", "this offer has expired"],
    "vinted": ["sold", "vandut", "vândut"],
    "okazii": ["vandut", "vândut", "anunt expirat", "anunț expirat"],
    "facebook": ["this listing was sold", "no longer available"],
}


def _check_url(url: str, platform: str) -> str:
    """Returneaza 'active', 'sold' sau 'removed' dupa raspunsul HTTP."""
    try:
        resp = requests.get(
            url,
            headers=build_headers(),
            timeout=5,
            allow_redirects=True,
        )
    except Exception:
        return "active"

    if resp.status_code == 404:
        return "removed"
    if resp.status_code >= 400:
        return "active"

    markers = _SOLD_MARKERS.get(platform, [])
    body = (resp.text or "").lower()
    for m in markers:
        if m in body:
            return "sold"
    return "active"


def cleanup_sold_listings(db: Session) -> int:
    """Verifica listingurile active mai vechi de 1h si actualizeaza statusul.

    Returneaza numarul de listinguri actualizate.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    candidates = (
        db.query(RadarListing)
        .filter(RadarListing.status == "active", RadarListing.found_at < cutoff)
        .order_by(RadarListing.last_checked_at.asc().nullsfirst())
        .limit(50)
        .all()
    )
    updated = 0
    for listing in candidates:
        new_status = _check_url(listing.url, listing.platform)
        listing.last_checked_at = datetime.now(timezone.utc)
        if new_status != "active":
            listing.status = new_status
            updated += 1
    if candidates:
        db.commit()
    if updated:
        print(f"[RadarCleanup] {updated} listinguri marcate ca sold/removed.")
    return updated


def cleanup_removed_listings_daily(db: Session) -> int:
    """Job zilnic: verifica TOATE listingurile (orice status) si sterge definitiv
    cele care nu mai exista pe marketplace (404 / markeri sold/removed).
    Include listinguri salvate si ignorate — odata ce anuntul dispare, nu mai are rost sa fie urmarit.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    BATCH_SIZE = 50
    total_deleted = 0
    offset = 0

    total_checked = db.query(RadarListing).filter(RadarListing.found_at < cutoff).count()
    log_manager.emit("radar", "CLEAN", f"Cleanup zilnic pornit · verificare {total_checked} anunțuri")

    while True:
        candidates = (
            db.query(RadarListing)
            .filter(RadarListing.found_at < cutoff)
            .order_by(RadarListing.last_checked_at.asc().nullsfirst())
            .limit(BATCH_SIZE)
            .offset(offset)
            .all()
        )
        if not candidates:
            break

        batch_deleted = 0
        for listing in candidates:
            result = _check_url(listing.url, listing.platform)
            listing.last_checked_at = datetime.now(timezone.utc)
            if result in ("removed", "sold"):
                db.delete(listing)
                batch_deleted += 1

        db.commit()
        total_deleted += batch_deleted
        offset += BATCH_SIZE - batch_deleted  # adjust for deleted rows

        if len(candidates) < BATCH_SIZE:
            break

    if total_deleted:
        print(f"[RadarDailyCleanup] {total_deleted} anunțuri șterse definitiv (dispărute de pe marketplace).")
        log_manager.emit("radar", "WARN", f"{total_deleted} anunțuri nu mai există pe marketplace → șterse definitiv")
    log_manager.emit("radar", "OK", f"Cleanup finalizat · {total_checked - total_deleted} anunțuri rămase active")
    return total_deleted
