"""
4-level duplicate detection for real estate listings.
Level 1: 1a same source URL · 1b same seller_id + price → auto-group (certain)
Level 2: pHash ≤10 OR (pHash ≤20 AND color_hist ≥0.85) → auto-group
Level 3: price ±3% + zone + rooms + area ±8%, no image confirm → badge
Level 4: partial match only → no action
"""
import re
import uuid
from typing import Optional
from sqlalchemy.orm import Session

# Helper-ele generice (hash imagine + _prices_close) traiesc acum in shared/image_hash.py,
# partajate cu detectorul de duplicate Auto. Logica IDENTICA, doar sursa s-a mutat.
from app.services.shared.image_hash import (
    compute_phash, compute_color_hist, phash_distance, hist_similarity, _prices_close)


# ── Zone / area matching helper (specific imobiliare) ──────────

def _areas_close(a1: int, a2: int, tolerance: float = 0.08) -> bool:
    if not a1 or not a2:
        return True  # if one is missing, don't penalize
    return abs(a1 - a2) / max(a1, a2) <= tolerance


# ── Main detection function ──────────────────────────────────

def check_duplicates(listing, db: Session, model_class,
                     user_id: int) -> tuple:
    """
    Returns (duplicate_level, group_id_or_none, matched_listing_or_none)
    """
    # MODIFICARE 10 — Level 1 revizuit. Vechiul check pe `external_id` nu se putea
    # declansa niciodata (exista index unic pe (user, platform, external_id), deci
    # nu pot exista doua randuri cu acelasi external_id pentru acelasi user).
    #
    # Level 1a: acelasi URL sursa (acelasi anunt indexat de doua ori). In schema
    # reala coloana se numeste `url` (nu `source_url`).
    if getattr(listing, "url", None):
        l1a = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.url == listing.url,
            model_class.id != listing.id,
        ).first()
        if l1a:
            group_id = l1a.duplicate_group_id or str(uuid.uuid4())
            return 1, group_id, l1a

    # Level 1b: acelasi vanzator + acelasi pret (acelasi anunt de la acelasi owner).
    if getattr(listing, "seller_id", None) and listing.price:
        l1b = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.seller_id == listing.seller_id,
            model_class.price == listing.price,
            model_class.id != listing.id,
        ).first()
        if l1b:
            group_id = l1b.duplicate_group_id or str(uuid.uuid4())
            return 1, group_id, l1b

    # Level 2: image hash match
    if listing.phash:
        candidates = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.phash.isnot(None),
            model_class.id != listing.id,
        ).all()
        for cand in candidates:
            dist = phash_distance(listing.phash, cand.phash)
            if dist <= 10:
                group_id = cand.duplicate_group_id or str(uuid.uuid4())
                return 2, group_id, cand
            if dist <= 20 and listing.color_hist and cand.color_hist:
                sim = hist_similarity(listing.color_hist, cand.color_hist)
                if sim >= 0.85:
                    group_id = cand.duplicate_group_id or str(uuid.uuid4())
                    return 2, group_id, cand

    # Level 3: text criteria (price + zone + rooms + area)
    if (listing.price and listing.zone_normalized and listing.rooms):
        candidates = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.zone_normalized == listing.zone_normalized,
            model_class.rooms == listing.rooms,
            model_class.id != listing.id,
            model_class.price.isnot(None),
        ).all()
        for cand in candidates:
            price_ok = _prices_close(float(listing.price),
                                     float(cand.price), 0.03)
            area_ok = _areas_close(listing.area_sqm, cand.area_sqm, 0.08)
            if price_ok and area_ok:
                return 3, None, cand

    return 4, None, None
