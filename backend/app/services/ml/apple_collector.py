"""Colector ML pentru Apple (electronics_apple). Scrapeaza OLX general + Vinted."""
import asyncio
import re
from datetime import datetime, timedelta, timezone

from app.services.ml.base_collector import BaseMLCollector, _safe_price
from app.services.ml.relevance_filter import is_relevant_apple

# Query-uri specifice pe model — colectare tintita de produse complete.
APPLE_QUERIES_OLX = [
    "iPhone 12", "iPhone 12 Pro", "iPhone 12 Pro Max",
    "iPhone 13", "iPhone 13 Pro", "iPhone 13 Pro Max",
    "iPhone 14", "iPhone 14 Pro", "iPhone 14 Pro Max",
    "iPhone 15", "iPhone 15 Pro", "iPhone 15 Pro Max",
    "iPhone 16", "iPhone 16 Pro",
    "MacBook Air M1", "MacBook Air M2", "MacBook Air M3",
    "MacBook Pro M1", "MacBook Pro M2", "MacBook Pro M3",
    "iPad Pro", "iPad Air",
]

APPLE_QUERIES_VINTED = [
    "iPhone 12", "iPhone 13", "iPhone 14",
    "iPhone 15", "iPhone 16",
]


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

    @staticmethod
    def _normalize_vinted(results) -> list:
        """Mapeaza formatul scraperului Radar (external_id/url/images) la forma
        asteptata de _ingest/_listing_data (platform_id/source_url/thumbnail_url)."""
        out = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            images = r.get("images") or []
            out.append({
                "platform_id": r.get("external_id"),
                "title": r.get("title"),
                "price": r.get("price"),
                "currency": r.get("currency", "EUR"),
                "source_url": r.get("url"),
                "thumbnail_url": images[0] if images else None,
                "description": r.get("description"),
            })
        return out

    async def collect_new_listings(self, db) -> int:
        from app.scrapers.marketplace.olx_general import search_olx_general
        from app.services.radar.vinted_scraper import search_vinted

        total = 0

        def _ingest(results, platform):
            nonlocal total
            for r in results or []:
                if not r.get("platform_id"):
                    continue
                title = r.get("title", "")
                price = r.get("price")
                # Filtru de relevanta — sare peste piese/accesorii.
                if not is_relevant_apple(title, price):
                    continue
                features = self._extract_apple_features(
                    title, price, r.get("description", ""))
                self._save_listing(db, self._listing_data(r, features), self.CATEGORY, self.BRAND, platform)
                total += 1

        # OLX — query-uri specifice pe model (delay politicos intre cereri).
        for query in APPLE_QUERIES_OLX:
            try:
                _ingest(await search_olx_general(query=query), "olx")
                await asyncio.sleep(1.5)
            except Exception as exc:
                print(f"[AppleCollector] olx {query!r}: {exc}")

        # Vinted — refoloseste scraperul din Radar Piata (libraria vinted-scraper
        # cu gestionare DataDome + fallback pe cookie). search_vinted e SINCRON si
        # intoarce formatul radar (external_id/url/images), deci il rulam intr-un
        # thread (sa nu blocam event loop-ul) si normalizam la forma _ingest.
        for query in APPLE_QUERIES_VINTED:
            try:
                raw = await asyncio.to_thread(
                    search_vinted,
                    keyword=query,
                    max_price=None,
                    exclude_words=["piese", "schimb display", "dezmembrez", "carcasa"],
                )
                _ingest(self._normalize_vinted(raw), "vinted")
                await asyncio.sleep(1.0)
            except Exception as exc:
                print(f"[AppleCollector] vinted {query!r}: {exc}")

        print(f"[AppleCollector] {total} anunturi Apple colectate/actualizate.")
        return total

    def _extract_apple_features(
        self, title: str, price: float, description: str = ""
    ) -> dict:
        import re as _re
        text = f"{title} {description}".lower()
        f_out = {"brand": "Apple"}

        # ── Product line ──
        if "iphone" in text:
            f_out["product_line"] = "iPhone"
        elif "ipad" in text:
            f_out["product_line"] = "iPad"
        elif "macbook" in text:
            f_out["product_line"] = "MacBook"
        elif "airpod" in text:
            f_out["product_line"] = "AirPods"
        elif "watch" in text:
            f_out["product_line"] = "Apple Watch"

        # ── Model year ──
        m = _re.search(r"iphone\s*(\d{1,2})", text)
        if m:
            f_out["model_year"] = int(m.group(1))

        # ── Variant ──
        if "pro max" in text or "promax" in text:
            f_out["variant"] = "pro_max"
        elif " pro" in text:
            f_out["variant"] = "pro"
        elif " plus" in text or " max" in text:
            f_out["variant"] = "plus"
        elif " mini" in text:
            f_out["variant"] = "mini"
        else:
            f_out["variant"] = "standard"

        # ── Storage ──
        sm = _re.search(r"(\d+)\s*(gb|tb)", text)
        if sm:
            val = int(sm.group(1))
            f_out["storage_gb"] = val * 1024 if sm.group(2) == "tb" else val

        # ── Battery ──
        bm = _re.search(
            r"(?:baterie|battery|soh|autonomie)[:\s]*(\d{1,3})\s*%", text)
        if bm:
            pct = int(bm.group(1))
            f_out["battery_pct"] = pct
            f_out["is_battery_degraded"] = 1 if pct < 80 else 0
        else:
            f_out["is_battery_degraded"] = 0

        # ── iCloud ──
        if any(w in text for w in [
                "blocat icloud", "icloud blocat", "icloud lock", "locked icloud"]):
            f_out["icloud_status"] = "blocked"
        elif any(w in text for w in [
                "icloud curat", "fara icloud", "icloud ok", "icloud free", "icloud liber"]):
            f_out["icloud_status"] = "clean"
        else:
            f_out["icloud_status"] = "unknown"

        # ── Screen condition ──
        if any(w in text for w in [
                "ecran fisurat", "fisura ecran", "spart ecran", "display spart", "touch spart"]):
            f_out["screen_condition_score"] = 1
        elif any(w in text for w in ["ecran zgariet", "zgariat ecran", "linie ecran"]):
            f_out["screen_condition_score"] = 3
        elif any(w in text for w in [
                "ecran perfect", "display perfect", "fara zgarieturi ecran", "ecran impecabil"]):
            f_out["screen_condition_score"] = 5
        else:
            f_out["screen_condition_score"] = 3

        # ── Accessories ──
        f_out["has_box"] = 1 if any(w in text for w in [
            "cu cutie", "cutie originala", "box original", "vine cu cutie"]) else 0
        f_out["has_charger"] = 0
        if any(w in text for w in ["cu incarcator", "cu cablu", "charger inclus"]):
            f_out["has_charger"] = 1

        # ── Unlock status ──
        if any(w in text for w in [
                "liber de retea", "deblocat", "unlocked", "free network", "orice retea"]):
            f_out["unlocked_code"] = "unlocked"
        elif any(w in text for w in ["blocat", "locked", "orange only", "vodafone only", "digi only"]):
            f_out["unlocked_code"] = "locked"
        else:
            f_out["unlocked_code"] = "unknown"

        # ── Warranty ──
        wm = _re.search(
            r"garantie\s*(?:pana\s*(?:in|la)\s*|valabil[a\s]*)?"
            r"(\d{1,4})", text)
        if wm:
            f_out["has_warranty"] = 1
            val = int(wm.group(1))
            if val > 100:   # it's a year (2025, 2026…)
                from datetime import datetime
                f_out["warranty_months"] = max(0, (val - datetime.now().year) * 12)
            else:
                f_out["warranty_months"] = val
        else:
            f_out["has_warranty"] = 0
            f_out["warranty_months"] = 0

        f_out["price"] = _safe_price(price)
        return f_out

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
