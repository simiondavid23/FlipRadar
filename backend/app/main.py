import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth, products, watchlist, alerts, dashboard, ai_chat, ai_analysis, admin, support
from app.routers import favorites, notifications, scraping, import_export
from app.routers import currency, inventory, sales, reports, radar
from app.routers import user_settings  # FlipRadar — ITEM 16: setari Flash Deal
from app.routers import marketplace  # FlipRadar — Modulul 1 Marketplace (scrapere live)
from app.routers import auto  # FlipRadar — Loturi & Licitatii (Copart/IAAI/SCA/OpenLane)
from app.routers import real_estate  # FlipRadar — Modul Imobiliare (OLX/Storia/Imobiliare.ro)
from app.routers import ml  # FlipRadar — ML: predictie pret + timp de vanzare
from app.routers.facebook_groups import router as facebook_groups_router  # FlipRadar — Grupuri Facebook
from app.routers.tracked_products import router as tracked_router  # FlipRadar — Produse Urmarite (favorite + watchlist)
from app.routers.logs import router as logs_router  # FlipRadar — Jurnale Live (SSE)
from app.routers.auto_listings_keywords import router as auto_listings_router  # FlipRadar — Auto Anunturi (keyword-uri + feed)
from app.routers.real_estate_keywords import router as re_monitor_router  # FlipRadar — Imobiliare Monitor (keyword-uri + feed)

# Import all models
from app.models import user, product, price_history, product_source
from app.models import watchlist as watchlist_model
from app.models import alert, chat_message, support_ticket
from app.models import favorite, notification
from app.models import inventory as inventory_model
from app.models import sale as sale_model
from app.models import radar_keyword, radar_listing, radar_seen_id
from app.models import radar_blocked_seller, radar_settings
from app.models import radar_message_template, push_subscription
from app.models import market_listing  # FlipRadar — date reale de piata pentru Consilier AI
# FlipRadar — tabele noi pentru modulele auto/imobiliare (doar schema, populate ulterior)
from app.models import real_estate_listing, auto_lot, auto_listing
# FlipRadar — Modulul 1 Marketplace: anunturi salvate + alerte keyword
from app.models import marketplace_saved, marketplace_keyword_alert
# FlipRadar — Modul Imobiliare: alerte keyword
from app.models import real_estate_alert
# FlipRadar — Grupuri Facebook (config + postari)
from app.models import facebook_group_config, facebook_group_post

# Create all database tables
Base.metadata.create_all(bind=engine)

# Apply any pending column-level migrations for existing tables
from app.utils.db_migrate import run_migrations
run_migrations()

from app.utils.alert_checker import check_alerts
from app.utils.radar_scanner import run_radar_scan
from app.utils.real_estate_scanner import check_real_estate_alerts

scheduler = BackgroundScheduler(timezone="Europe/Bucharest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Instaleaza Chromium pentru Playwright la prima pornire (idempotent — sare
    # peste daca e deja instalat). check=False ca sa nu blocheze startup-ul.
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            check=False, capture_output=True,
        )
    except Exception as exc:
        print(f"[Playwright] install skip: {exc}")

    scheduler.add_job(
        check_alerts,
        "interval",
        minutes=15,
        id="check_alerts",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.add_job(
        run_radar_scan,
        "interval",
        minutes=5,
        id="radar_scan",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    # FlipRadar — Auto Anunturi: scaneaza keyword-urile auto la fiecare 10 min.
    try:
        from app.services.auto_listings_scanner import run_auto_scan

        def _run_auto_scan():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_auto_scan(_db)
            except Exception as exc:
                print(f"[AutoScan] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(
            _run_auto_scan,
            "interval",
            minutes=10,
            id="auto_listings_scan",
            replace_existing=True,
        )
        print("[Scheduler] Auto listings scan (10m) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] Auto scan setup failed: {exc}")

    # FlipRadar — Imobiliare Monitor: scan (30m) + pHash (1h) + cleanup (12:30).
    try:
        from app.services.real_estate_scanner import run_real_estate_scan

        def _run_re_scan():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_real_estate_scan(_db)
            except Exception as exc:
                print(f"[REScan] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(_run_re_scan, "interval", minutes=30,
            id="real_estate_scan", replace_existing=True)
        print("[Scheduler] Real estate scan (30m) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] RE scan setup failed: {exc}")

    try:
        from app.services.real_estate.phash_job import run_phash_job

        def _run_phash():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_phash_job(_db)
            except Exception as exc:
                print(f"[pHash] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(_run_phash, "interval", hours=1,
            id="re_phash_job", replace_existing=True)
        print("[Scheduler] pHash job (1h) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] pHash setup failed: {exc}")

    try:
        from app.services.real_estate_scanner import run_cleanup

        def _run_re_cleanup():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_cleanup(_db)
            except Exception as exc:
                print(f"[RECleanup] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(_run_re_cleanup, "cron", hour=12, minute=30,
            id="re_daily_cleanup", replace_existing=True)
        print("[Scheduler] RE cleanup (12:30) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] RE cleanup setup failed: {exc}")

    # FlipRadar — Imobiliare: scaneaza alertele la fiecare 30 minute (prima rulare
    # nu e imediata, ca sa nu scrapeze la fiecare restart).
    scheduler.add_job(
        check_real_estate_alerts,
        "interval",
        minutes=30,
        id="real_estate_alerts",
        replace_existing=True,
    )

    # FlipRadar — cleanup zilnic (04:00): sterge definitiv anunturile disparute
    # de pe marketplace (404 / sold/removed), inclusiv cele salvate/ignorate.
    def _daily_radar_cleanup():
        from app.database import SessionLocal
        from app.services.radar.cleanup_service import cleanup_removed_listings_daily
        _db = SessionLocal()
        try:
            cleanup_removed_listings_daily(_db)
        finally:
            _db.close()

    scheduler.add_job(
        _daily_radar_cleanup,
        "cron",
        hour=12,
        minute=0,
        id="radar_daily_cleanup",
        replace_existing=True,
    )

    # ML sold detection — runs daily at 13:00
    # Checks market_listings for sold status → generates training labels
    try:
        from app.services.ml.sold_detector import run_sold_detection

        def _run_sold_detection():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_sold_detection(_db, batch_size=100)
            except Exception as exc:
                print(f"[ML SoldDetector] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(
            _run_sold_detection,
            "cron",
            hour=13,
            minute=0,
            id="ml_sold_detection",
            replace_existing=True,
        )
        print("[Scheduler] ML sold detection (13:00 zilnic) înregistrat.")
    except Exception as exc:
        print(f"[Scheduler] ML sold detection setup failed: {exc}")

    # FlipRadar — ML: colectare date piata (BMW/Apple) la 6h, verificare vandute la
    # 12h, reantrenare modele lunea la 03:00. Izolat in try/except ca lipsa
    # dependintelor ML (scikit-learn etc.) sa nu impiedice pornirea aplicatiei.
    try:
        import asyncio
        from app.database import SessionLocal
        # ML collectors disabled — data now collected via feed scanners
        # (Radar Piață → electronics_apple, Auto Anunțuri → auto_bmw).
        # To re-enable: uncomment the imports, instantiation and jobs below.
        # from app.services.ml.bmw_collector import BMWCollector
        # from app.services.ml.apple_collector import AppleCollector
        from app.services.ml.price_predictor import (
            train_ml_models_if_ready, models_available, MODELS_DIR,
        )

        # bmw_collector = BMWCollector()
        # apple_collector = AppleCollector()

        # def _run_async_collector(coro_fn):
        #     db = SessionLocal()
        #     try:
        #         asyncio.run(coro_fn(db))
        #     except Exception as exc:
        #         print(f"[ML job] eroare: {exc}")
        #     finally:
        #         db.close()

        # ML collectors disabled — data now collected via feed scanners
        # (Radar Piață → electronics_apple, Auto Anunțuri → auto_bmw)
        # To re-enable: uncomment and restart
        # scheduler.add_job(lambda: _run_async_collector(bmw_collector.collect_new_listings),
        #                   "interval", hours=6, id="collect_bmw", replace_existing=True)
        # scheduler.add_job(lambda: _run_async_collector(apple_collector.collect_new_listings),
        #                   "interval", hours=6, id="collect_apple", replace_existing=True)
        # scheduler.add_job(lambda: _run_async_collector(bmw_collector.check_sold_status),
        #                   "interval", hours=12, id="check_sold_bmw", replace_existing=True)
        # scheduler.add_job(lambda: _run_async_collector(apple_collector.check_sold_status),
        #                   "interval", hours=12, id="check_sold_apple", replace_existing=True)
        scheduler.add_job(train_ml_models_if_ready,
                          "cron", day_of_week="mon", hour=3, id="retrain_models", replace_existing=True)

        # Initial ML collection disabled — feed scanners handle this now
        # import threading as _threading
        #
        # async def _delayed_initial_collect():
        #     await asyncio.sleep(60)
        #     _cdb = SessionLocal()
        #     try:
        #         print("[ML] Colectare initiala pornita dupa startup...")
        #         await bmw_collector.collect_new_listings(_cdb)
        #         await apple_collector.collect_new_listings(_cdb)
        #         print("[ML] Colectare initiala finalizata.")
        #     except Exception as exc:
        #         print(f"[ML] Eroare colectare initiala: {exc}")
        #     finally:
        #         _cdb.close()
        #
        # def _run_initial():
        #     asyncio.run(_delayed_initial_collect())
        #
        # _threading.Thread(target=_run_initial, daemon=True).start()

        if models_available():
            print(f"[ML] Modele ML gasite in {MODELS_DIR}.")
        else:
            print("[ML] Modelele ML nu sunt disponibile inca.")
        _ml_jobs_ok = True
    except Exception as exc:
        _ml_jobs_ok = False
        print(f"[ML] Setup ML esuat (dependinte lipsa?): {exc}")

    # FlipRadar — Grupuri Facebook: verifica la 30 min daca e timpul pentru vreun
    # grup (interval per-config) + avertizare zilnica expirare cookies (09:00).
    try:
        from app.services.facebook_group_service import (
            run_facebook_group_checks,
            check_cookie_expiry,
        )
        scheduler.add_job(
            lambda: asyncio.run(run_facebook_group_checks()),
            "interval", minutes=30, id="facebook_group_checks", replace_existing=True,
        )
        scheduler.add_job(
            check_cookie_expiry,
            "cron", hour=9, minute=0, id="facebook_cookie_expiry_check", replace_existing=True,
        )
        _fb_jobs_ok = True
    except Exception as exc:
        _fb_jobs_ok = False
        print(f"[Scheduler] Setup joburi Grupuri Facebook esuat: {exc}")

    scheduler.start()
    print(
        "[Scheduler] Started - check_alerts (15m) + radar_scan (5m) + real_estate_alerts (30m)"
        + (" + ML collectors (6h/12h) + retrain (luni 03:00)" if _ml_jobs_ok else "")
        + (" + facebook_group_checks (30m) + cookie_expiry (09:00)." if _fb_jobs_ok else ".")
    )

    # Jurnale Live — emit de pornire pentru fiecare modul, ca tab-urile sa nu fie
    # goale inainte sa ruleze primul scraper.
    from app.services.log_manager import log_manager as _lm
    for _mod in ["radar", "catalog", "auto_lots", "auto_listings", "real_estate"]:
        _lm.emit(_mod, "INFO", f"FlipRadar pornit — modul {_mod} initializat")

    # Diagnostic SMTP la fiecare pornire — ca sa fie clar daca alertele
    # vor putea trimite email atunci cand se declanseaza.
    from app.services.email_service import is_configured as _smtp_ok
    if _smtp_ok():
        print("[Scheduler] SMTP configurat — email-urile pentru alerte se vor trimite.")
    else:
        print("[Scheduler] ATENTIE: SMTP NU este configurat (.env). Alertele vor crea doar notificari in-app, fara email.")

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")


app = FastAPI(
    title="FlipRadar API",
    description="API pentru automatizarea research-ului de produse profitabile in comertul online",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(ai_chat.router)
app.include_router(ai_analysis.router)
app.include_router(admin.router)
app.include_router(support.router)
app.include_router(favorites.router)
app.include_router(notifications.router)
app.include_router(scraping.router)
app.include_router(import_export.router)
app.include_router(currency.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(reports.router)
app.include_router(radar.router)
app.include_router(user_settings.router)
app.include_router(marketplace.router)
app.include_router(auto.router)
app.include_router(real_estate.router)
app.include_router(ml.router)
app.include_router(facebook_groups_router)
app.include_router(tracked_router, prefix="/api/tracked-products")
app.include_router(logs_router)
app.include_router(auto_listings_router)
app.include_router(re_monitor_router)


@app.get("/")
def root():
    return {
        "name": "FlipRadar API",
        "version": "1.0.0",
        "status": "running",
        "message": "Bine ai venit la FlipRadar API! Viziteaza /docs pentru documentatie.",
    }


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
