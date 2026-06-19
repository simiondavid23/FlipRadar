"""Colector ML pentru BMW (auto_bmw). Scrapeaza AutoVit / OLX Auto / Mobile.de.

NOTA: scraperele auto returneaza chei in romana (titlu/pret/moneda/locatie/external_id),
deci mapam explicit catre forma asteptata de _save_listing (title/price/currency).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.services.ml.base_collector import BaseMLCollector


class BMWCollector(BaseMLCollector):
    CATEGORY = "auto_bmw"
    BRAND = "BMW"

    @staticmethod
    def _features(r: dict) -> dict:
        return {
            "make": "BMW",
            "year": r.get("year"),
            "km": r.get("km"),
            "engine_type": r.get("engine_type"),
            "gearbox": r.get("gearbox"),
            "color": r.get("color"),
            "location": r.get("locatie"),
            "price": r.get("pret"),
        }

    @staticmethod
    def _listing_data(r: dict, features: dict) -> dict:
        return {
            "external_id": r.get("external_id"),
            "title": r.get("titlu"),
            "price": r.get("pret"),
            "currency": r.get("moneda", "EUR"),
            "source_url": r.get("source_url"),
            "thumbnail_url": r.get("thumbnail_url"),
            "features": features,
        }

    async def collect_new_listings(self, db) -> int:
        from app.scrapers.auto.listings.autovit_scraper import search_autovit
        from app.scrapers.auto.listings.olx_auto import search_olx_auto
        from app.scrapers.auto.listings.mobile_de_scraper import search_mobile_de

        total = 0

        async def _ingest(results, platform):
            nonlocal total
            for r in results or []:
                if not r.get("external_id"):
                    continue  # fara id stabil nu putem deduplica corect
                self._save_listing(db, self._listing_data(r, self._features(r)), self.CATEGORY, self.BRAND, platform)
                total += 1

        # AutoVit — make=BMW
        try:
            await _ingest(await search_autovit(make="BMW", filters={"sort": "newest"}), "autovit")
        except Exception as exc:
            print(f"[BMWCollector] autovit error: {exc}")
        # OLX Auto — query "BMW"
        try:
            await _ingest(await search_olx_auto(query="BMW"), "olx_auto")
        except Exception as exc:
            print(f"[BMWCollector] olx_auto error: {exc}")
        # Mobile.de — make_id 3500, pret < 50.000 EUR (import relevant)
        try:
            await _ingest(await search_mobile_de(make_id="3500", filters={"price_max": 50000}), "mobile_de")
        except Exception as exc:
            print(f"[BMWCollector] mobile_de error: {exc}")

        print(f"[BMWCollector] {total} anunturi BMW colectate/actualizate.")
        return total

    async def check_sold_status(self, db) -> int:
        """Verifica daca anunturile vechi mai exista (404/410 -> vandut)."""
        import httpx
        from app.models.market_listing import MarketListing

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        old_listings = db.query(MarketListing).filter(
            MarketListing.category == self.CATEGORY,
            MarketListing.sold_at.is_(None),
            MarketListing.listed_at < cutoff,
        ).limit(100).all()

        updated = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            for listing in old_listings:
                if not listing.source_url:
                    continue
                try:
                    resp = await client.head(listing.source_url, follow_redirects=True)
                    if resp.status_code in (404, 410):
                        listing.sold_at = datetime.now(timezone.utc)
                        listing.days_to_sell = (listing.sold_at - listing.listed_at).days
                        updated += 1
                except Exception:
                    pass
                await asyncio.sleep(0.3)

        if updated > 0:
            db.commit()
        print(f"[BMWCollector] {updated} anunturi marcate ca vandute.")
        return updated
