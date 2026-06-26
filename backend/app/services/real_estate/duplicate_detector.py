"""
4-level duplicate detection for real estate listings.
Level 1: same external_id or same URL → auto-group (certain)
Level 2: pHash ≤10 OR (pHash ≤20 AND color_hist ≥0.85) → auto-group
Level 3: price ±3% + zone + rooms + area ±8%, no image confirm → badge
Level 4: partial match only → no action
"""
import re
import uuid
from typing import Optional
from sqlalchemy.orm import Session


# ── Image hashing ──────────────────────────────────────────────

def compute_phash(image_url: str) -> Optional[str]:
    try:
        import imagehash
        from PIL import Image
        import requests as req
        resp = req.get(image_url, timeout=8, stream=True)
        if resp.status_code != 200:
            return None
        from io import BytesIO
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        h = imagehash.phash(img)
        return str(h)
    except Exception:
        return None


def compute_color_hist(image_url: str) -> Optional[list]:
    try:
        from PIL import Image
        import requests as req
        from io import BytesIO
        resp = req.get(image_url, timeout=8, stream=True)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img_small = img.resize((64, 64))
        hist = img_small.histogram()
        total = sum(hist) or 1
        return [v / total for v in hist]
    except Exception:
        return None


def phash_distance(h1: str, h2: str) -> int:
    try:
        import imagehash
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
    except Exception:
        return 64  # max distance if error


def hist_similarity(h1: list, h2: list) -> float:
    if not h1 or not h2 or len(h1) != len(h2):
        return 0.0
    try:
        dot = sum(a * b for a, b in zip(h1, h2))
        mag1 = sum(a * a for a in h1) ** 0.5
        mag2 = sum(b * b for b in h2) ** 0.5
        if mag1 * mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)
    except Exception:
        return 0.0


# ── Zone / price matching helpers ──────────────────────────────

def _prices_close(p1: float, p2: float, tolerance: float = 0.03) -> bool:
    if not p1 or not p2:
        return False
    return abs(p1 - p2) / max(p1, p2) <= tolerance


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
    # Level 1: same external_id on different platform
    if listing.external_id:
        l1 = db.query(model_class).filter(
            model_class.user_id == user_id,
            model_class.external_id == listing.external_id,
            model_class.id != listing.id,
        ).first()
        if l1:
            group_id = l1.duplicate_group_id or str(uuid.uuid4())
            return 1, group_id, l1

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
