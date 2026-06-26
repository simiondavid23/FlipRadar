"""Colector ML pentru BMW (auto_bmw). Scrapeaza AutoVit / OLX Auto / Mobile.de.

NOTA: scraperele auto returneaza chei in romana (titlu/pret/moneda/locatie/external_id),
deci mapam explicit catre forma asteptata de _save_listing (title/price/currency).
"""
import asyncio
import re as _re
from datetime import datetime, timedelta, timezone

from app.services.ml.base_collector import BaseMLCollector, _safe_price
from app.services.ml.relevance_filter import is_relevant_bmw

BMW_QUERIES_OLX = [
    "BMW E46", "BMW E90", "BMW E91",
    "BMW E60", "BMW E61", "BMW E87",
    "BMW F30", "BMW F31", "BMW F10",
    "BMW F20", "BMW G20", "BMW G30",
]

BMW_SERIES_AUTOVIT = [
    "E46", "E90", "E60", "F30", "F10", "G20",
]


class BMWCollector(BaseMLCollector):
    CATEGORY = "auto_bmw"
    BRAND = "BMW"

    @staticmethod
    def _features(r: dict) -> dict:
        title = str(r.get("titlu") or r.get("title") or "")
        desc = str(r.get("description") or "")
        text = f"{title} {desc}".lower()

        # ── Series ──
        series = None
        for code in ["g20", "g21", "g22", "g30", "g11", "f30", "f31", "f32", "f20",
                     "f10", "f11", "f01", "e90", "e91", "e92", "e46", "e87", "e60",
                     "e61", "e36", "e34", "e30"]:
            if code in text:
                series = code.upper()
                break

        # ── Motor ──
        m = _re.search(r"\b(3\d{2})[di]?\b", text)
        motor = m.group(1) if m else None

        # ── Diesel / Petrol ──
        is_diesel = any(w in text for w in [
            "diesel", "motorina", " d ", " td ", "320d", "318d", "316d", "330d", "335d"])

        # ── Automatic ──
        is_automatic = any(w in text for w in [
            "automat", "automatic", "automata", "cutie automata", "steptronic"])

        # ── Horsepower ──
        hp_m = _re.search(r"(\d{2,3})\s*(?:cp|cai\s*putere|hp)", text)
        hp = int(hp_m.group(1)) if hp_m else None

        # ── Body type ──
        body = "sedan"
        for k, v in [("touring", "touring"), ("combi", "touring"), ("break", "touring"),
                     ("coupe", "coupe"), ("cabrio", "cabrio"),
                     ("suv", "suv"), ("gran coupe", "gran coupe"), ("hatchback", "hatchback")]:
            if k in text:
                body = v
                break

        # ── ITP ──
        has_itp = bool(_re.search(r"itp\s*(valabil|ok|20\d{2})", text))

        # ── Service book ──
        has_service_book = any(w in text for w in [
            "carte service", "cs la zi", "service history", "revizie la zi"])
        if any(w in text for w in ["fara carte", "fara service", "fara cs"]):
            has_service_book = False

        # ── Owners ──
        own_m = _re.search(r"(\w+)\s*(proprietar|owner|posesor)", text)
        num_owners = None
        if own_m:
            word = own_m.group(1)
            num_owners = {"un": 1, "unu": 1, "o": 1, "doi": 2, "doua": 2, "trei": 3,
                          "one": 1, "two": 2, "three": 3}.get(word)
            if num_owners is None and word.isdigit():
                num_owners = int(word)

        # ── Defects ──
        has_defects = any(w in text for w in [
            "necesita reparatie", "lovit", "avariat", "accident", "tocit",
            "corodat", "rugina", "problema mare"])

        # ── Options ──
        has_xenon = any(w in text for w in ["xenon", "full led", "bixenon"])
        has_navi = any(w in text for w in ["navi", "navigatie", "gps profesional", "idrive"])
        has_leather = any(w in text for w in ["piele", "leather", "scaune piele", "tapiterie piele"])
        has_sunroof = any(w in text for w in ["trapa", "panorama", "panoramic", "sunroof"])

        # ── Import ──
        is_imported = any(w in text for w in [
            "import", "din germania", "din italia", "din franta", "din olanda",
            "aus deutschland", "tara de origine"])

        return {
            "make": "BMW",
            "series": series,
            "motor": motor,
            "is_diesel": is_diesel,
            "is_automatic": is_automatic,
            "hp": hp,
            "year": r.get("year"),
            "km": r.get("km"),
            "body_type": body,
            "color": r.get("color") or r.get("culoare"),
            "has_itp": has_itp,
            "has_service_book": has_service_book,
            "num_owners": num_owners,
            "has_defects": has_defects,
            "has_xenon": has_xenon,
            "has_navi": has_navi,
            "has_leather": has_leather,
            "has_sunroof": has_sunroof,
            "is_imported": is_imported,
            "platform": r.get("platform"),
            "price": _safe_price(r.get("pret") or r.get("price")),
            "location": r.get("locatie"),
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

        async def _ingest_autovit(results, platform):
            nonlocal total
            for r in results or []:
                if not r.get("external_id"):
                    continue
                has_year_km = (
                    r.get("year") is not None and
                    r.get("km") is not None
                )
                # Pe Autovit: prezenta year+km = garantie de masina completa.
                if not is_relevant_bmw(
                    r.get("titlu", ""),
                    price=r.get("pret"),
                    year=r.get("year"),
                    has_year_and_km=has_year_km,
                ):
                    continue
                self._save_listing(db, self._listing_data(r, self._features(r)), self.CATEGORY, self.BRAND, platform)
                total += 1

        async def _ingest_generic(results, platform):
            nonlocal total
            for r in results or []:
                if not r.get("external_id"):
                    continue
                if not is_relevant_bmw(
                    r.get("titlu", "") or r.get("title", ""),
                    price=r.get("pret") or r.get("price"),
                    year=r.get("year"),
                    has_year_and_km=False,
                ):
                    continue
                self._save_listing(db, self._listing_data(r, self._features(r)), self.CATEGORY, self.BRAND, platform)
                total += 1

        # Autovit — cautare per serie pentru tintire mai buna.
        for series in BMW_SERIES_AUTOVIT:
            try:
                results = await search_autovit(make="BMW", filters={"model": series, "sort": "newest"})
                await _ingest_autovit(results, "autovit")
                await asyncio.sleep(2.0)
            except Exception as exc:
                print(f"[BMWCollector] autovit {series}: {exc}")

        # OLX Auto — cautare per serie.
        for query in BMW_QUERIES_OLX:
            try:
                results = await search_olx_auto(query=query)
                await _ingest_generic(results, "olx_auto")
                await asyncio.sleep(1.5)
            except Exception as exc:
                print(f"[BMWCollector] olx_auto {query!r}: {exc}")

        # Mobile.de — BMW cu filtru de pret.
        try:
            results = await search_mobile_de(make_id="3500", filters={"price_min": 500, "price_max": 50000})
            await _ingest_generic(results, "mobile_de")
        except Exception as exc:
            print(f"[BMWCollector] mobile_de: {exc}")

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
