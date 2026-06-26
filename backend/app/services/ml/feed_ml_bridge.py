"""
Bridges the feed scanners (Radar Piață, Auto Anunțuri) to ML
data collection. When a new listing is saved to the feed and its
title matches a ML category, it's also saved to market_listings.
Detection is done via listing TITLE, not keyword.
"""
from datetime import datetime, timezone
from typing import Optional


# ── Category detection ──────────────────────────────────────────

APPLE_TITLE_SIGNALS = ["iphone", "ipad", "macbook", "airpod", "apple watch"]
BMW_TITLE_SIGNALS = ["bmw"]


def detect_ml_category(title: str) -> Optional[str]:
    """
    Returns ML category string or None.
    Detection by listing title only — platform-agnostic.
    """
    t = (title or "").lower()
    if any(s in t for s in APPLE_TITLE_SIGNALS):
        return "electronics_apple"
    if "bmw" in t:
        return "auto_bmw"
    return None


# ── Relevance check ─────────────────────────────────────────────

def _is_relevant(title: str, price: float,
                 category: str, year=None, km=None) -> bool:
    """Apply category-specific relevance filters."""
    try:
        from app.services.ml.relevance_filter import (
            is_relevant_apple, is_relevant_bmw)
        if category == "electronics_apple":
            return is_relevant_apple(title, price)
        if category == "auto_bmw":
            has_yk = (year is not None and km is not None)
            return is_relevant_bmw(title, price, year,
                                   has_year_and_km=has_yk)
    except Exception:
        pass
    return True


# ── Feature extraction ──────────────────────────────────────────

def _extract_features(title: str, price: float, category: str,
                      description: str = "", **extra) -> dict:
    """Extract ML features from listing data."""
    try:
        if category == "electronics_apple":
            from app.services.ml.apple_collector import AppleCollector
            return AppleCollector()._extract_apple_features(
                title, price, description)

        if category == "auto_bmw":
            from app.services.ml.bmw_collector import BMWCollector
            raw = {
                "title":       title,
                "titlu":       title,
                "description": description,
                "year":        extra.get("year"),
                "km":          extra.get("km"),
                "is_diesel": "diesel" in (
                    extra.get("fuel_type") or "").lower(),
                "is_automatic": "automat" in (
                    extra.get("transmission") or "").lower(),
                "color":    extra.get("color"),
                "platform": extra.get("platform"),
                "pret":     price,
            }
            return BMWCollector()._features(raw)
    except Exception as exc:
        print(f"[FeedMLBridge] Feature extraction error: {exc}")
    return {}


# ── Main save function ──────────────────────────────────────────

def try_save_to_ml(
    db,
    title: str,
    price: float,
    currency: str,
    external_id: str,
    platform: str,
    source_url: str,
    thumbnail_url: str,
    description: str = "",
    year=None,
    km=None,
    fuel_type=None,
    transmission=None,
) -> bool:
    """
    Detects ML category from title. If matched and relevant,
    saves to market_listings. Returns True if saved.
    """
    category = detect_ml_category(title)
    if not category:
        return False

    # Price sanity
    try:
        price_f = float(price) if price else None
    except (TypeError, ValueError):
        price_f = None
    if not price_f or price_f <= 0 or price_f > 999_999:
        price_f = None

    # Relevance filter
    if not _is_relevant(title, price_f or 0, category, year, km):
        return False

    # Deduplication
    try:
        from app.models.market_listing import MarketListing
        existing = db.query(MarketListing).filter(
            MarketListing.external_id == str(external_id),
            MarketListing.platform == platform,
            MarketListing.category == category,
        ).first()
        if existing:
            # Update last_seen_at only
            existing.last_seen_at = datetime.now(timezone.utc)
            db.commit()
            return False

        # Extract features
        features = _extract_features(
            title, price_f or 0, category, description,
            year=year, km=km, fuel_type=fuel_type,
            transmission=transmission, platform=platform)

        brand = "Apple" if category == "electronics_apple" else "BMW"

        ml_entry = MarketListing(
            category=category,
            brand=brand,
            platform=platform,
            external_id=str(external_id),
            title=title[:500],
            features=features,
            price=price_f,
            currency=currency or "RON",
            listed_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            source_url=source_url or "",
            thumbnail_url=thumbnail_url or "",
            scraped_at=datetime.now(timezone.utc),
        )
        db.add(ml_entry)
        db.commit()
        return True

    except Exception as exc:
        db.rollback()
        print(f"[FeedMLBridge] Save error: {str(exc)[:120]}")
        return False
