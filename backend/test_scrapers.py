import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results_summary = {}


async def main():
    # OLX (sync)
    print("=== OLX ===")
    try:
        from app.services.radar.olx_scraper import search_olx
        r = search_olx("iphone", max_price=5000, judet=None, oras=None,
                       condition="all", exclude_words=[], min_price=None, category=None)
        print(f"  OK: {len(r)} results")
        if r:
            print(f"  Sample: {r[0].get('title','')} — {r[0].get('price','')} RON")
        results_summary["OLX"] = "OK" if r else "BROKEN (0 results)"
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        results_summary["OLX"] = f"BROKEN ({type(e).__name__})"

    # Okazii (async — scraperul din scrapers/marketplace)
    print("=== Okazii ===")
    try:
        from app.scrapers.marketplace.okazii_scraper import search_okazii
        r = await search_okazii("iphone", filters={"max_price": 5000})
        print(f"  OK: {len(r)} results")
        if r:
            print(f"  Sample: {r[0].get('title','')}")
        results_summary["Okazii"] = "OK" if r else "BROKEN (0 results)"
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        results_summary["Okazii"] = f"BROKEN ({type(e).__name__})"

    # LaJumate
    print("=== LaJumate ===")
    try:
        from app.services.radar.lajumate_scraper import search_lajumate
        r = search_lajumate("iphone", max_price=5000, exclude_words=[],
                            min_price=None, category=None)
        print(f"  OK: {len(r)} results")
        if r:
            print(f"  Sample: {r[0].get('title','')}")
        results_summary["LaJumate"] = "OK" if r else "BROKEN (0 results)"
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        results_summary["LaJumate"] = f"BROKEN ({type(e).__name__})"

    # Publi24
    print("=== Publi24 ===")
    try:
        from app.services.radar.publi24_scraper import search_publi24
        r = search_publi24("iphone", max_price=5000, exclude_words=[], category=None)
        print(f"  OK: {len(r)} results")
        if r:
            print(f"  Sample: {r[0].get('title','')}")
        results_summary["Publi24"] = "OK" if r else "BROKEN (0 results)"
    except ImportError:
        print("  SKIP: scraper not found")
        results_summary["Publi24"] = "NOT IMPLEMENTED"
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        results_summary["Publi24"] = f"BROKEN ({type(e).__name__})"

    # Facebook
    print("=== Facebook ===")
    try:
        from app.services.radar.facebook_scraper import is_facebook_session_valid
        import glob
        session_files = (
            glob.glob("/home/**/*.json", recursive=True)
            + glob.glob("/tmp/**/*.json", recursive=True)
            + glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "*.json"))
        )
        fb_sessions = [f for f in session_files if "facebook" in f.lower() or "fb_" in f.lower()]
        if fb_sessions:
            any_valid = False
            for sf in fb_sessions:
                valid = is_facebook_session_valid(sf)
                any_valid = any_valid or valid
                print(f"  Session {sf}: {'VALID' if valid else 'EXPIRED'}")
            results_summary["Facebook"] = "SESSION VALID" if any_valid else "EXPIRED"
        else:
            print("  No Facebook session file found on disk")
            results_summary["Facebook"] = "NOT CONFIGURED"
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        results_summary["Facebook"] = f"ERROR ({type(e).__name__})"

    print()
    print("==================== SUMMARY ====================")
    print(f"  [OLX]      {results_summary.get('OLX', '?')}")
    print(f"  [Okazii]   {results_summary.get('Okazii', '?')}")
    print(f"  [LaJumate] {results_summary.get('LaJumate', '?')}")
    print(f"  [Publi24]  {results_summary.get('Publi24', '?')}")
    print(f"  [Facebook] {results_summary.get('Facebook', '?')}")
    print(f"  [Vinted]   REQUIRES COOKIE (tested separately via /vinted/test)")


asyncio.run(main())
