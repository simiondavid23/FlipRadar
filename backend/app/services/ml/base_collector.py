"""Clasa de baza pentru colectorii de date ML (market_listings).

Fiecare colector concret (BMW, Apple, ...) scrapeaza periodic anunturi noi,
le persista in market_listings cu features structurate si marcheaza anunturile
disparute ca vandute (pentru a obtine days_to_sell — eticheta de antrenament).
"""
from datetime import datetime, timezone


def _safe_price(raw) -> float | None:
    """Parseaza pretul in siguranta. Returneaza None pentru valori invalide/garbage.

    Scraperele pot intoarce preturi corupte (ex: tot textul cardului concatenat
    intr-un singur numar urias ca 1.6e+41) cand selectorul de pret nu se
    potriveste. Astfel de valori depasesc coloana Numeric(10,2) si arunca
    NumericValueOutOfRange la INSERT — aceasta garda le prinde inainte.
    """
    if raw is None:
        return None
    try:
        val = float(str(raw).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    # Niciun anunt real nu poate avea pret in afara acestui interval.
    if val <= 0 or val > 999_999:
        return None
    return val


class BaseMLCollector:
    async def collect_new_listings(self, db) -> int:
        """Scrapeaza anunturi noi de la ultima rulare. Returneaza numarul de intrari noi."""
        raise NotImplementedError

    async def check_sold_status(self, db) -> int:
        """Verifica ce anunturi nu mai sunt active (vandute). Returneaza numarul de actualizari."""
        raise NotImplementedError

    def _save_listing(self, db, listing_data: dict, category: str, brand: str, platform: str):
        from app.models.market_listing import MarketListing
        # Garda finala de pret inainte de orice INSERT/UPDATE — respinge valorile
        # imposibile (None pe garbage) ca sa nu arunce NumericValueOutOfRange.
        price = _safe_price(listing_data.get("price"))
        try:
            existing = db.query(MarketListing).filter(
                MarketListing.external_id == listing_data.get("external_id"),
                MarketListing.platform == platform,
            ).first()
            if existing:
                existing.last_seen_at = datetime.now(timezone.utc)
                if price is not None:
                    existing.price = price
                db.commit()
                db.refresh(existing)
                return existing
            ml = MarketListing(
                category=category, brand=brand, platform=platform,
                external_id=listing_data.get("external_id"),
                title=listing_data.get("title", ""),
                features=listing_data.get("features", {}),
                price=price,
                currency=listing_data.get("currency", "EUR"),
                listed_at=listing_data.get("listed_at", datetime.now(timezone.utc)),
                last_seen_at=datetime.now(timezone.utc),
                source_url=listing_data.get("source_url"),
                thumbnail_url=listing_data.get("thumbnail_url"),
            )
            db.add(ml)
            db.commit()
            db.refresh(ml)
            return ml
        except Exception as exc:
            db.rollback()  # CRITIC: recupereaza sesiunea pentru urmatorul anunt
            print(f"[MLCollector] Insert skipped ({type(exc).__name__}): "
                  f"{str(exc)[:100]}")
            return None
