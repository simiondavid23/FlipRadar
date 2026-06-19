"""Clasa de baza pentru colectorii de date ML (market_listings).

Fiecare colector concret (BMW, Apple, ...) scrapeaza periodic anunturi noi,
le persista in market_listings cu features structurate si marcheaza anunturile
disparute ca vandute (pentru a obtine days_to_sell — eticheta de antrenament).
"""
from datetime import datetime, timezone


class BaseMLCollector:
    async def collect_new_listings(self, db) -> int:
        """Scrapeaza anunturi noi de la ultima rulare. Returneaza numarul de intrari noi."""
        raise NotImplementedError

    async def check_sold_status(self, db) -> int:
        """Verifica ce anunturi nu mai sunt active (vandute). Returneaza numarul de actualizari."""
        raise NotImplementedError

    def _save_listing(self, db, listing_data: dict, category: str, brand: str, platform: str):
        from app.models.market_listing import MarketListing
        existing = db.query(MarketListing).filter(
            MarketListing.external_id == listing_data.get("external_id"),
            MarketListing.platform == platform,
        ).first()
        if existing:
            existing.last_seen_at = datetime.now(timezone.utc)
            existing.price = listing_data.get("price", existing.price)
        else:
            ml = MarketListing(
                category=category, brand=brand, platform=platform,
                external_id=listing_data.get("external_id"),
                title=listing_data.get("title", ""),
                features=listing_data.get("features", {}),
                price=listing_data.get("price"),
                currency=listing_data.get("currency", "EUR"),
                listed_at=listing_data.get("listed_at", datetime.now(timezone.utc)),
                last_seen_at=datetime.now(timezone.utc),
                source_url=listing_data.get("source_url"),
                thumbnail_url=listing_data.get("thumbnail_url"),
            )
            db.add(ml)
        db.commit()
