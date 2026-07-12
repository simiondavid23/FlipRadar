# MODIFICARE 1 — validarea variabilelor de mediu obligatorii ruleaza prima,
# inainte de orice alt import din app (care ar declansa conectarea la DB).
from app.startup_checks import validate_env
validate_env()

import asyncio
import os
import subprocess
import sys
import threading
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
from app.routers.auto_lot_keywords import router as auto_lot_router  # FlipRadar — Loturi Auto (keyword-uri + feed monitorizat)
from app.routers.real_estate_keywords import router as re_monitor_router  # FlipRadar — Imobiliare Monitor (keyword-uri + feed)

# Import all models
from app.models import user, product, price_history, product_source
# FlipRadar — sugestii cross-shop (potrivire pe nume, asteapta confirmare)
from app.models import product_source_suggestion
from app.models import watchlist as watchlist_model
from app.models import alert, chat_message, support_ticket
from app.models import favorite, notification
from app.models import inventory as inventory_model
from app.models import sale as sale_model
from app.models import radar_keyword, radar_listing, radar_seen_id
from app.models import radar_settings
from app.models import vinted_catalog  # RP-2 — arbore dinamic de categorii Vinted
from app.models import radar_message_template, push_subscription
from app.models import market_listing  # FlipRadar — date reale de piata pentru Consilier AI
# FlipRadar — tabele noi pentru modulele auto/imobiliare (doar schema, populate ulterior)
from app.models import real_estate_listing, auto_lot, auto_listing
# FlipRadar — Modulul 1 Marketplace: anunturi salvate + alerte keyword
from app.models import marketplace_saved, marketplace_keyword_alert
# FlipRadar — Grupuri Facebook (config + postari)
from app.models import facebook_group_config, facebook_group_post
# MODIFICARE 7 — coada Discord persistenta (tabel discord_queue)
from app.models import discord_queue_db
# MODIFICARE 12 — persistare optionala log-uri SSE (tabel log_entries)
from app.models import log_entry

# Create all database tables
Base.metadata.create_all(bind=engine)

# Apply any pending column-level migrations for existing tables
from app.utils.db_migrate import run_migrations
run_migrations()

from app.utils.alert_checker import check_alerts
from app.utils.radar_scanner import run_radar_scan

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

    # RP-2 — refresh arbore categorii Vinted: săptămânal (duminică 04:30) + o singură
    # încercare la startup dacă tabelul e gol. Eșecul (block Vinted) NU blochează app-ul.
    def _run_vinted_catalog_refresh():
        from app.database import SessionLocal
        from app.services.radar.vinted_catalog_service import refresh_catalog_tree
        _db = SessionLocal()
        try:
            refresh_catalog_tree(_db)
        except Exception as exc:
            print(f"[VintedCatalog] refresh esuat: {exc}")
        finally:
            _db.close()

    scheduler.add_job(
        _run_vinted_catalog_refresh, "cron", day_of_week="sun", hour=4, minute=30,
        id="vinted_catalog_refresh", replace_existing=True,
    )
    try:
        from app.database import SessionLocal
        from app.models.vinted_catalog import VintedCatalog
        _cdb = SessionLocal()
        try:
            _catalog_empty = _cdb.query(VintedCatalog.id).first() is None
        finally:
            _cdb.close()
        if _catalog_empty:
            scheduler.add_job(
                _run_vinted_catalog_refresh, "date", run_date=datetime.now(),
                id="vinted_catalog_bootstrap", replace_existing=True,
            )
    except Exception as exc:
        print(f"[VintedCatalog] verificare bootstrap eșuată: {exc}")

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

    # FlipRadar — Loturi Auto: scaneaza keyword-urile de loturi la fiecare 15 min.
    try:
        from app.services.auto_lot_scanner import run_auto_lot_scan_global

        def _run_auto_lot_scan():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_auto_lot_scan_global(_db)
            except Exception as exc:
                print(f"[AutoLotScan] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(
            _run_auto_lot_scan,
            "interval",
            minutes=15,
            id="auto_lots_scan",
            replace_existing=True,
        )
        print("[Scheduler] Auto lots scan (15m) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] Auto lots scan setup failed: {exc}")

    # FlipRadar — Imobiliare Monitor: scan (tick 5m, polling per keyword) + cleanup (12:30).
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

        # Tick des (5 min); decizia de a scana e per keyword, in _polling_due (mirror radar_scan).
        scheduler.add_job(_run_re_scan, "interval", minutes=5,
            id="real_estate_scan", replace_existing=True)
        print("[Scheduler] Real estate scan (tick 5m, polling per keyword) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] RE scan setup failed: {exc}")

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

    # MODIFICARE 7 — cleanup zilnic (03:30) al cozii Discord: sterge itemele
    # trimise mai vechi de 7 zile (istoricul nu trebuie pastrat la nesfarsit).
    def _cleanup_discord_queue():
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text(
                "DELETE FROM discord_queue WHERE status='sent' AND sent_at < NOW() - INTERVAL '7 days'"
            ))
            db.commit()
        finally:
            db.close()

    scheduler.add_job(
        _cleanup_discord_queue, "cron", hour=3, minute=30,
        id="discord_queue_cleanup", replace_existing=True,
    )

    # MODIFICARE 12 — cleanup zilnic (03:00) al log-urilor persistate: sterge
    # intrarile mai vechi de 24h. No-op daca LOG_DB_PERSISTENCE nu e activ.
    def _cleanup_log_entries():
        import os
        if os.getenv("LOG_DB_PERSISTENCE", "false").lower() != "true":
            return
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM log_entries WHERE created_at < NOW() - INTERVAL '24 hours'"))
            db.commit()
        finally:
            db.close()

    scheduler.add_job(
        _cleanup_log_entries, "cron", hour=3, minute=0,
        id="log_entries_cleanup", replace_existing=True,
    )

    scheduler.start()
    print(
        "[Scheduler] Started - check_alerts (15m) + radar_scan (5m)"
        + (" + ML collectors (6h/12h) + retrain (luni 03:00)" if _ml_jobs_ok else "")
        + (" + facebook_group_checks (30m) + cookie_expiry (09:00)." if _fb_jobs_ok else ".")
    )

    # FlipRadar — pre-warm curs BNR EUR->RON: prima cerere de stats dupa restart altfel
    # blocheaza pana la ~10s pe fetch-ul sincron. Fire-and-forget; gardat pentru teste.
    if os.getenv("FLIPRADAR_TESTING") != "1":
        def _prewarm_bnr():
            try:
                from app.services.currency_service import get_eur_ron_rate
                get_eur_ron_rate()
            except Exception:
                pass  # doar incalzim cache-ul; esecul nu blocheaza pornirea
        threading.Thread(target=_prewarm_bnr, daemon=True, name="bnr-prewarm").start()

    # MODIFICARE 7 — la pornire marcam ca 'failed' itemele Discord ramase 'pending'
    # mai vechi de 1h (dintr-un run anterior intrerupt), ca sa nu blocheze coada.
    try:
        from app.database import SessionLocal as _SL
        from app.services.discord_service import discord_service as _ds
        _ddb = _SL()
        try:
            _ds.cleanup_stale(_ddb)
        finally:
            _ddb.close()
    except Exception as exc:
        print(f"[Discord] cleanup_stale la startup esuat: {exc}")

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

# MODIFICARE 5 — rate limiting pe endpoint-urile de scraping manual (slowapi).
# Limiter-ul e definit în app.rate_limit; aici îl atașăm de app + handler 429 în română.
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse
from app.rate_limit import limiter

app.state.limiter = limiter


def _rate_limit_handler(request, exc):
    """Răspuns 429 cu mesaj în română la depășirea limitei."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Prea multe cereri într-un interval scurt. Așteaptă un minut și încearcă din nou."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Register all routers
# MODIFICARE 2 — health check montat primul, fara middleware de autentificare.
from app.routers import health
app.include_router(health.router)
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
app.include_router(auto_lot_router)
app.include_router(re_monitor_router)


@app.get("/")
def root():
    return {
        "name": "FlipRadar API",
        "version": "1.0.0",
        "status": "running",
        "message": "Bine ai venit la FlipRadar API! Viziteaza /docs pentru documentatie.",
    }


