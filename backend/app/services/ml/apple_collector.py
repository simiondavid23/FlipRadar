"""Colector ML pentru Apple (electronics_apple). Scrapeaza OLX general + Vinted."""
import asyncio
import re
from datetime import datetime, timedelta, timezone

from app.services.ml.base_collector import BaseMLCollector


class AppleCollector(BaseMLCollector):
    CATEGORY = "electronics_apple"
    BRAND = "Apple"

    def _listing_data(self, r: dict, features: dict) -> dict:
        return {
            "external_id": r.get("platform_id"),
            "title": r.get("title"),
            "price": r.get("price"),
            "currency": r.get("currency", "EUR"),
            "source_url": r.get("source_url"),
            "thumbnail_url": r.get("thumbnail_url"),
            "features": features,
        }

    async def collect_new_listings(self, db) -> int:
        from app.scrapers.marketplace.olx_general import search_olx_general
        from app.scrapers.marketplace.vinted_scraper import search_vinted

        total = 0

        def _ingest(results, platform):
            nonlocal total
            for r in results or []:
                if not r.get("platform_id"):
                    continue
                features = self._extract_apple_features(r.get("title", ""), r.get("price", 0))
                self._save_listing(db, self._listing_data(r, features), self.CATEGORY, self.BRAND, platform)
                total += 1

        # OLX — iPhone / iPad / MacBook (3 query-uri separate)
        for query in ["iPhone", "iPad", "MacBook"]:
            try:
                _ingest(await search_olx_general(query=query), "olx")
            except Exception as exc:
                print(f"[AppleCollector] olx '{query}' error: {exc}")

        # Vinted — Apple iPhone
        try:
            _ingest(await search_vinted(query="Apple iPhone"), "vinted")
        except Exception as exc:
            print(f"[AppleCollector] vinted error: {exc}")

        print(f"[AppleCollector] {total} anunturi Apple colectate/actualizate.")
        return total

    def _extract_apple_features(self, title: str, price: float) -> dict:
        """Extrage features din titlul anuntului Apple."""
        features = {"brand": "Apple"}
        title_lower = (title or "").lower()

        # Detecteaza product line
        if "iphone" in title_lower:
            features["product_line"] = "iPhone"
        elif "ipad" in title_lower:
            features["product_line"] = "iPad"
        elif "macbook" in title_lower:
            features["product_line"] = "MacBook"
        elif "airpods" in title_lower:
            features["product_line"] = "AirPods"
        elif "watch" in title_lower:
            features["product_line"] = "Apple Watch"

        # Detecteaza storage
        storage_match = re.search(r'(\d+)\s*(?:gb|tb)', title_lower)
        if storage_match:
            val = int(storage_match.group(1))
            unit = title_lower[storage_match.start():storage_match.end() + 2]
            features["storage_gb"] = val * 1024 if "tb" in unit else val

        # Detecteaza SOH baterie
        battery_match = re.search(r'(?:baterie|battery|soh)\s*[:\s]*(\d{1,3})\s*%', title_lower)
        if battery_match:
            features["battery_health_pct"] = int(battery_match.group(1))

        features["price"] = price
        return features

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
        print(f"[AppleCollector] {updated} anunturi marcate ca vandute.")
        return updated
