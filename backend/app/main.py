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
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.instance_lock import asigura_instanta_unica

# LAUNCH-2 — inaintea lui create_all/run_migrations de mai jos: pana la lifespan
# un al doilea proces ar fi scris deja in baza.
asigura_instanta_unica()
from app.routers import auth, products, alerts, dashboard
from app.routers import license  # KEY-1 — licentiere cu cheie de activare (mod desktop)
from app.routers import scraping
from app.routers import currency, inventory, sales, reports, radar
from app.routers import user_settings  # FlipRadar — ITEM 16: setari Flash Deal
from app.routers import marketplace  # FlipRadar — Modulul 1 Marketplace (scrapere live)
from app.routers import auto  # FlipRadar — Loturi & Licitatii (Copart/IAAI/SCA/OpenLane)
from app.routers import real_estate  # FlipRadar — Modul Imobiliare (OLX/Storia/Imobiliare.ro)
from app.routers import resale  # FASHION-3a — referinte de revanzare + profiluri de taxe
from app.routers.facebook_groups import router as facebook_groups_router  # FlipRadar — Grupuri Facebook
from app.routers.tracked_products import router as tracked_router  # FlipRadar — Produse Urmarite (model unificat TrackedProduct)
from app.routers.logs import router as logs_router  # FlipRadar — Jurnale Live (SSE)
from app.routers.auto_listings_keywords import router as auto_listings_router  # FlipRadar — Auto Anunturi (keyword-uri + feed)
from app.routers.auto_lot_keywords import router as auto_lot_router  # FlipRadar — Loturi Auto (keyword-uri + feed monitorizat)
from app.routers.real_estate_keywords import router as re_monitor_router  # FlipRadar — Imobiliare Monitor (keyword-uri + feed)
from app.routers.deals import router as deals_router  # SHOP-2a — deal-uri Shopify

# Import all models
from app.models import user, product, price_history, product_source
# FlipRadar — sugestii cross-shop (potrivire pe nume, asteapta confirmare)
from app.models import product_source_suggestion
from app.models import tracked_product  # Catalog (CAT-3a) — unifica favorite + watchlist
from app.models import alert
from app.models import inventory as inventory_model
from app.models import sale as sale_model
from app.models import radar_keyword, radar_listing, radar_seen_id
from app.models import radar_settings
from app.models import vinted_catalog  # RP-2 — arbore dinamic de categorii Vinted
from app.models import radar_message_template, push_subscription
# FlipRadar — tabele noi pentru modulele auto/imobiliare (doar schema, populate ulterior)
from app.models import real_estate_listing, auto_lot, auto_listing
# FlipRadar — Modulul 1 Marketplace: anunturi salvate
# (alertele keyword marketplace au fost eliminate: cod mort fara UI si fara
#  evaluator; functionalitatea e acoperita de Radar keywords)
from app.models import marketplace_saved
# FlipRadar — Grupuri Facebook (config + postari)
from app.models import facebook_group_config, facebook_group_post
# MODIFICARE 7 — coada Discord persistenta (tabel discord_queue)
from app.models import discord_queue_db
# MODIFICARE 12 — persistare optionala log-uri SSE (tabel log_entries)
from app.models import log_entry
# FASHION-3a — referinta de revanzare + profilul de taxe (fara migrare: tabele noi)
from app.models import resale_fee_profile, resale_reference
# SHOP-2a — scannerul de deal-uri Shopify: observatii globale + memoria de pret
# care alimenteaza referinta R2 + starea de sanatate per magazin.
from app.models import deal, fb_pool, fb_scan_state, shop_price_memory, shop_scan_state

# Create all database tables
Base.metadata.create_all(bind=engine)

# Apply any pending column-level migrations for existing tables
from app.utils.db_migrate import run_migrations
run_migrations()

from app.utils.alert_checker import check_alerts
from app.utils.radar_scanner import run_radar_scan_platform, RADAR_PLATFORMS

# SCHED-1 — job_defaults pentru TOATE joburile: misfire_grace_time implicit e 1s, deci
# o rulare intarziata (thread pool ocupat) era sarita tacut; coalesce comprima rulari
# ratate multiple intr-una; max_instances=1 impiedica suprapunerea aceluiasi job.
scheduler = BackgroundScheduler(
    timezone="Europe/Bucharest",
    job_defaults={"coalesce": True, "misfire_grace_time": 300, "max_instances": 1},
)


def _check_rotator_config() -> None:
    """NET-5.2b — configuratia rotatorului se valideaza la BOOT, nu la primul scrape.

    `MODEM_ROTATION_METHOD` scris gresit face `build_rotator()` sa arunce ValueError, iar
    `get_rotator()` nu prinde nimic si lasa `_instance` pe None — deci fiecare apel
    ulterior re-arunca. Simptomul ar aparea abia dupa 5 minute, pe toate platformele
    legate deodata, ca „bind indisponibil". Aici se vede la pornire, o data.

    Nu opreste procesul: o configuratie gresita de rotatie nu trebuie sa impiedice
    pornirea aplicatiei — restul functioneaza fara ea. Bonus: incalzeste singletonul,
    deci primul scrape nu mai plateste constructia.
    """
    try:
        from app.services.network.rotator import get_rotator
        _rot = get_rotator()
        print(f"[Network] Rotator: {type(_rot).__name__}")
        # NET-5.3 §7 — capcana 4: un proces mort intre dataswitch=0 si =1 lasa modemul
        # OFFLINE. Repararea (`available()` -> `_recover_data_off`) a ramas fara apelant
        # dupa 5.2c. E cross-proces, deci boot-ul e momentul exact. Verifica intai
        # link-ul, ca sa nu intarzie pornirea cu 30s cand modemul e configurat dar absent.
        from app.services.network.triggers import recover_data_if_link_up
        if recover_data_if_link_up():
            print("[Network] Modem: date verificate/repornite la boot")
    except Exception as exc:
        print(f"[Network] CONFIGURATIE INVALIDA pentru rotatie IP: {exc}")
        print("[Network] Verifica MODEM_ROTATION_METHOD in .env "
              "(valori valide: dataswitch, reboot). Rotatia ramane inactiva.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Instaleaza Chromium pentru Playwright la prima pornire (idempotent — sare
    # peste daca e deja instalat). check=False ca sa nu blocheze startup-ul.
    # PKG-3b: sub PyInstaller, sys.executable = FlipRadar.exe, deci acest subprocess
    # ar re-lansa RECURSIV launcher-ul (fork bomb, uvicorn nu mai devine ready) — il
    # sarim sub frozen. In exe browserul vine din Chrome real / bundle (vezi --selfcheck).
    #
    # BR-3: lifespan descarca DOAR binarul browserului — neprivilegiat, idempotent, in
    # cache-ul userului. Asta e auto-vindecarea REALA, care merge pe orice masina,
    # inclusiv sub systemd ca user normal. Dependentele de sistem (`--with-deps`) cer
    # root si apartin pasului de instalare din ghid, unde ruleaza interactiv cu sudo.
    # Motivul eliminarii, masurat in driver: `installDeps` ruleaza INAINTEA descarcarii
    # browserului, deci sub systemd fara TTY sudo pica cu "no tty present" si opreste
    # TOT apelul — inclusiv descarcarea care ar fi mers neprivilegiat. Cu `--with-deps`,
    # pe un Pi rulat ca user normal, lifespan-ul n-a instalat NICIODATA vreun browser.
    if not getattr(sys, "frozen", False):
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=False, capture_output=True,
            )
        except Exception as exc:
            print(f"[Playwright] install skip: {exc}")

        # BR-2: harness-ul BR-1 (browser_fetch) foloseste PATCHRIGHT, ale carui
        # revizii de Chromium difera de ale playwright (1208 vs 1228 la audit), iar
        # rezolvarea se face pe numele exact al directorului — deci instalarea de
        # mai sus nu-l acopera. Pe linux/arm64 (Pi) Chrome real nici nu exista, deci
        # Chromium-ul bundled e SINGURA ramura din _lanseaza; fara el, toate cele
        # patru domenii browser pica tacut (fetch_failed, pretul anterior pastrat).
        # Idempotent ca fratele lui: sare peste daca e deja instalat.
        try:
            subprocess.run(
                [sys.executable, "-m", "patchright", "install", "chromium"],
                check=False, capture_output=True,
            )
        except Exception as exc:
            print(f"[Patchright] install skip: {exc}")

    scheduler.add_job(
        check_alerts,
        "interval",
        minutes=15,
        id="check_alerts",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    # SCHED-1 — un job per platforma Radar (independente; un scraper lent/agatat nu
    # le mai blocheaza pe celelalte). Start esalonat cu 15s ca sa nu porneasca 8
    # scanari simultan la boot.
    for _i, _p in enumerate(RADAR_PLATFORMS):
        # FAST-1: tick la 1 minut — decizia reala ramane per (keyword, platforma) in
        # _platform_scan_due (poll_interval_minutes, implicit 5). Keyword-urile cu
        # interval 1 min (permise doar pe platformele rapide, vezi routers/radar.py)
        # sunt scanate ~la minut; restul exact ca inainte. Enrichmenturile de fundal
        # raman plafonate la 5 min (radar_scanner._enrich_due).
        scheduler.add_job(
            run_radar_scan_platform, "interval", minutes=1, args=[_p],
            id=f"radar_scan_{_p}", replace_existing=True,
            next_run_time=datetime.now() + timedelta(seconds=15 * _i),
        )

    _check_rotator_config()

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
        from app.services.auto_listings_scanner import run_auto_scan, AUTO_PLATFORMS

        def _run_auto_scan(platform: str):
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_auto_scan(_db, platform=platform)
            except Exception as exc:
                print(f"[AutoScan:{platform}] eroare: {exc}")
            finally:
                _db.close()

        # SCHED-2 — un job per platforma Auto (mirror SCHED-1): mobile_de blocat de
        # Imperva sau facebook_auto (Playwright, lent) nu mai intarzie Autovit/OLX Auto.
        # Prima rulare esalonata cu 20s ca joburile sa nu porneasca simultan.
        for _i, _p in enumerate(AUTO_PLATFORMS):
            scheduler.add_job(
                _run_auto_scan, "interval", minutes=10, args=[_p],
                id=f"auto_scan_{_p}", replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=10, seconds=20 * _i),
            )
        print(f"[Scheduler] Auto listings scan per platforma ({len(AUTO_PLATFORMS)} joburi, 10m) inregistrat.")
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

    # SHOP-2a — scannerul de deal-uri Shopify: enumerare completa a catalogelor,
    # deci interval larg (6h). Prima rulare e amanata cu 5 minute ca sa nu se
    # suprapuna peste rafala de scanari de la boot.
    try:
        from app.services.deal_scanner import run_deal_scan

        def _run_deal_scan():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_deal_scan(_db)
            except Exception as exc:
                print(f"[DealScan] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(
            _run_deal_scan,
            "interval",
            hours=6,
            id="deal_scan",
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(minutes=5),
        )
        print("[Scheduler] Deal scan Shopify (6h) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] Deal scan setup failed: {exc}")

    # DEAL-2 — scannerul de listari HTML: parcurge paginile de reduceri ale
    # magazinelor non-Shopify. Interval mult mai larg decat la Shopify (24h),
    # fiindca o pagina HTML e de ordinul megabaitilor, iar cele 4 domenii pilot
    # inseamna sute de pagini per rulare. Prima rulare e amanata cu 10 minute, dupa
    # cea de deal-uri, ca sa nu porneasca amandoua peste rafala de la boot.
    try:
        from app.services.listing_scanner import run_listing_scan

        def _run_listing_scan():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_listing_scan(_db)
            except Exception as exc:
                print(f"[ListingScan] eroare: {exc}")
            finally:
                _db.close()

        scheduler.add_job(
            _run_listing_scan,
            "interval",
            hours=24,
            id="listing_scan",
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(minutes=10),
        )
        print("[Scheduler] Listing scan HTML (24h) inregistrat.")
    except Exception as exc:
        print(f"[Scheduler] Listing scan setup failed: {exc}")

    # VAL D — `api_enum`: enumerarea catalogului prin API-ul de catalog VTEX.
    # IMPLICIT OPRIT (garda de mediu API_ENUM_SCAN, tiparul FB_EXECUTOR): un scan
    # complet inseamna ~1.100-1.300 de cereri si 33-48 de minute pe un singur
    # domeniu, deci pornirea lui e o DECIZIE, nu un efect al unui deploy.
    # Decalat +20 min fata de boot, adica la 10 minute DUPA scanul de listari,
    # ca cele trei surse sa nu porneasca peste rafala de la pornire.
    try:
        if (os.getenv("API_ENUM_SCAN") or "").strip().lower() in ("1", "true"):
            from app.services.api_scanner import run_api_scan

            def _run_api_scan():
                from app.database import SessionLocal
                _db = SessionLocal()
                try:
                    run_api_scan(_db)
                except Exception as exc:
                    print(f"[ApiScan] eroare: {exc}")
                finally:
                    _db.close()

            scheduler.add_job(
                _run_api_scan,
                "interval",
                hours=24,
                id="api_enum_scan",
                replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=20),
            )
            print("[Scheduler] API catalog scan (24h) inregistrat.")
        else:
            print("[Scheduler] API catalog scan OPRIT (API_ENUM_SCAN nesetat).")
    except Exception as exc:
        print(f"[Scheduler] API catalog scan setup failed: {exc}")

    # FlipRadar — Imobiliare Monitor: scan (tick 5m, polling per keyword) + cleanup (12:30).
    try:
        from app.services.real_estate_scanner import run_real_estate_scan, RE_PLATFORMS

        def _run_re_scan(platform: str):
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_real_estate_scan(_db, platform=platform)
            except Exception as exc:
                print(f"[REScan:{platform}] eroare: {exc}")
            finally:
                _db.close()

        # SCHED-2 — un job per platforma Imobiliare (mirror SCHED-1): FB Marketplace
        # (Playwright sincron, lent) nu mai intarzie OLX/Storia. Tick des (5 min);
        # decizia de a scana ramane per keyword, in _polling_due. Prima rulare esalonata.
        for _i, _p in enumerate(RE_PLATFORMS):
            scheduler.add_job(
                _run_re_scan, "interval", minutes=5, args=[_p],
                id=f"re_scan_{_p}", replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=5, seconds=15 * _i),
            )
        print(f"[Scheduler] Real estate scan per platforma ({len(RE_PLATFORMS)} joburi, "
              f"tick 5m, polling per keyword) inregistrat.")
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

    # DEAL-4 — curatenia zilnica a feed-ului de deal-uri: garda de stale, apoi
    # retentia celor incheiate. Ora e aleasa ca sa NU se suprapuna cu ceilalti
    # scriitori de noapte: 03:00 cleanup-ul de log-uri, 03:30 coada Discord,
    # 04:00 backup-ul. 03:15 e singura fereastra libera dintre ele, iar pe SQLite
    # doi stergatori in masa simultan inseamna "database is locked".
    try:
        from app.services.deal_retention import run_deal_cleanup

        def _run_deal_cleanup():
            from app.database import SessionLocal
            _db = SessionLocal()
            try:
                run_deal_cleanup(_db)
            except Exception as exc:
                print(f"[DealCleanup] eroare: {exc}")
            finally:
                _db.close()

        # D11 — pornit implicit; se opreste doar setand explicit DEAL_CLEANUP=0.
        if (os.getenv("DEAL_CLEANUP") or "1").strip().lower() not in ("0", "false", "no", "off"):
            scheduler.add_job(_run_deal_cleanup, "cron", hour=3, minute=15,
                              id="deal_daily_cleanup", replace_existing=True)
            print("[Scheduler] Deal cleanup (03:15) inregistrat.")
        else:
            print("[Scheduler] Deal cleanup OPRIT (DEAL_CLEANUP=0).")
    except Exception as exc:
        print(f"[Scheduler] Deal cleanup setup failed: {exc}")

    # FlipRadar — cleanup zilnic (12:00): sterge definitiv anunturile disparute
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

    # CLEAN-1 — verificarea sold/removed era "la 10 cicluri" de radar_scan, adica
    # imprevizibil de rar cand ciclurile sunt lente. Acum e job propriu, la 30 min.
    def _radar_sold_check():
        from app.database import SessionLocal
        from app.services.radar.cleanup_service import cleanup_sold_listings
        _db = SessionLocal()
        try:
            cleanup_sold_listings(_db)
        except Exception as exc:
            print(f"[RadarSoldCheck] eroare: {exc}")
        finally:
            _db.close()

    scheduler.add_job(
        _radar_sold_check, "interval", minutes=30,
        id="radar_sold_check", replace_existing=True,
    )

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

    # FB-6a — executorul Marketplace logat-out: consuma planificatorul pe perechi
    # (keyword x ancora) si umple bazinul `fb_pool`. Implicit OPRIT: volumul porneste
    # doar cand David il porneste explicit cu FB_EXECUTOR=1. Prima rulare e amanata
    # cu 2 minute ca sa nu intre in rafala de la boot.
    try:
        if (os.getenv("FB_EXECUTOR") or "").strip().lower() in ("1", "true"):
            from app.scrapers.facebook.executor import tick as _fb_tick

            def _run_fb_executor():
                from app.database import SessionLocal
                _db = SessionLocal()
                try:
                    _fb_tick(_db)
                except Exception as exc:
                    print(f"[FBExecutor] eroare: {exc}")
                finally:
                    _db.close()

            _fb_tick_min = int(os.getenv("FB_EXECUTOR_TICK_MIN") or 5)
            # JITTER pe tick: un job care porneste la fix, la fiecare 5 minute, e un
            # tipar de ceas — exact ce se distinge cel mai usor de partea cealalta.
            #
            # ATENTIE la semantica: APScheduler NU face `±jitter`. Sursa
            # (`BaseTrigger._apply_jitter`) e `next_fire_time + uniform(0, jitter)` —
            # o INTARZIERE, mereu pozitiva, in SECUNDE. Deci 40% din interval nu
            # inseamna „±40%", ci „+0..40%", cu media +20%: perioada efectiva devine
            # ~6 min la un interval de 5. E acceptabil (mai putin trafic, nu mai mult),
            # dar trebuie stiut cand se citesc cererile pe ora din baseline.
            _fb_jitter = int(os.getenv("FB_TICK_JITTER_S")
                             or round(_fb_tick_min * 60 * 0.40))
            scheduler.add_job(
                _run_fb_executor,
                "interval",
                minutes=_fb_tick_min,
                jitter=_fb_jitter,
                id="fb_executor",
                replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=2),
            )
            print(f"[Scheduler] FB executor logat-out ({_fb_tick_min}m, "
                  f"jitter +0..{_fb_jitter}s) inregistrat.")
        else:
            print("[Scheduler] FB executor dezactivat (FB_EXECUTOR absent).")
    except Exception as exc:
        print(f"[Scheduler] FB executor setup failed: {exc}")

    # FBS-4 — atingerea sesiunii. NU e re-login (R5 ramane in vigoare): incarca o
    # sesiune deja valida, o foloseste cateva zeci de secunde si o re-salveaza.
    # Garda proprie, implicit OPRITA, separata de cea a executorului: atingerea
    # deschide un browser real, deci nu porneste fara ca David s-o ceara.
    try:
        if (os.getenv("FB_ATINGERE") or "").strip().lower() in ("1", "true"):
            from app.scrapers.facebook.atingere import atinge as _fb_atinge

            def _run_fb_atingere():
                try:
                    _fb_atinge()
                except Exception as exc:
                    print(f"[FBAtingere] eroare: {exc}")

            # CELE 12 ORE SUNT O PRESUPUNERE, ca forma orara de la FBS-3. Nimeni nu
            # stie cat de des se roteste `xs`. Ce o calibreaza, din liniile
            # FBATINGERE din jurnal:
            #   · `xs_schimbat=1` la FIECARE atingere -> intervalul e prea mare,
            #     coboara-l;
            #   · `ceva_schimbat=0` dupa cateva zile -> mecanismul nu rezolva nimic,
            #     opreste-l cu FB_ATINGERE=0 in loc sa-l rarefiezi.
            _fb_at_ore = int(os.getenv("FB_ATINGERE_ORE") or 12)
            # Acelasi jitter unilateral ca la FBS-3: APScheduler face
            # `+uniform(0, jitter)`, nu `±`.
            _fb_at_jitter = int(os.getenv("FB_ATINGERE_JITTER_S")
                                or round(_fb_at_ore * 3600 * 0.20))
            scheduler.add_job(
                _run_fb_atingere,
                "interval",
                hours=_fb_at_ore,
                jitter=_fb_at_jitter,
                id="fb_atingere",
                replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=7),
            )
            print(f"[Scheduler] FB atingere sesiune ({_fb_at_ore}h, "
                  f"jitter +0..{_fb_at_jitter}s) inregistrata.")
        else:
            print("[Scheduler] FB atingere dezactivata (FB_ATINGERE absent).")
    except Exception as exc:
        print(f"[Scheduler] FB atingere setup failed: {exc}")

    # FBS-5 — retentia bazinului. GARDA IMPLICIT PORNITA, spre deosebire de restul
    # seriei: un bazin care creste nemarginit e o problema GARANTATA, deci stergerea
    # e comportamentul sigur, nu cel riscant. `FB_BAZIN_RETENTIE=0` o opreste.
    try:
        if (os.getenv("FB_BAZIN_RETENTIE") or "1").strip().lower() not in                 ("0", "false", "no", "off"):
            def _run_fb_retentie():
                from app.database import SessionLocal
                from app.scrapers.facebook.bazin import sterge_vechi
                _db = SessionLocal()
                try:
                    zile = float(os.getenv("FB_BAZIN_RETENTIE_ZILE") or 7)
                    n = sterge_vechi(_db, zile)
                    from app.services.log_manager import log_manager as _lm
                    _lm.emit("radar", "INFO",
                             f"FBBAZIN retentie: {n} randuri sterse, prag {zile:g} zile "
                             f"pe `ultima_vedere_at`")
                except Exception as exc:
                    print(f"[FBBazin] retentie esuata: {exc}")
                finally:
                    _db.close()

            scheduler.add_job(
                _run_fb_retentie,
                "cron", hour=4, minute=20,
                id="fb_bazin_retentie",
                replace_existing=True,
                next_run_time=datetime.now() + timedelta(minutes=11),
            )
            print("[Scheduler] FB retentie bazin (04:20) inregistrata.")
        else:
            print("[Scheduler] FB retentie bazin OPRITA (FB_BAZIN_RETENTIE=0).")
    except Exception as exc:
        print(f"[Scheduler] FB retentie setup failed: {exc}")

    # MODIFICARE 7 — cleanup zilnic (03:30) al cozii Discord: sterge itemele
    # trimise mai vechi de 7 zile (istoricul nu trebuie pastrat la nesfarsit).
    def _cleanup_discord_queue():
        from datetime import datetime, timezone, timedelta
        from app.database import SessionLocal
        from app.models.discord_queue_db import DiscordQueueItem
        from app.services.discord_service import cleanup_old_queue_rows
        db = SessionLocal()
        try:
            cleanup_old_queue_rows(db)
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
        from datetime import datetime, timezone, timedelta
        from app.database import SessionLocal
        from app.models.log_entry import LogEntry
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            db.query(LogEntry).filter(
                LogEntry.created_at < cutoff,
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    scheduler.add_job(
        _cleanup_log_entries, "cron", hour=3, minute=0,
        id="log_entries_cleanup", replace_existing=True,
    )

    # BK-1 — backup zilnic (04:00) al bazei SQLite, cu rotatie si alerta la esec.
    def _run_db_backup():
        from app.database import SessionLocal
        from app.services.backup_service import run_db_backup
        db = SessionLocal()
        try:
            run_db_backup(db)
        finally:
            db.close()

    scheduler.add_job(
        _run_db_backup, "cron", hour=4, minute=0,
        id="db_backup", replace_existing=True,
    )

    scheduler.start()
    print(
        "[Scheduler] Started - check_alerts (15m) + radar_scan_<platforma> (8 joburi, 5m)"
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

    # DISC-1 — worker-ul Discord porneste abia acum: schema exista
    # (create_all + run_migrations au rulat) si coada e curatata de stale.
    from app.services.discord_service import discord_service as _discord_svc
    _discord_svc.start()

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
app.include_router(license.router)  # KEY-1
app.include_router(products.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(scraping.router)
app.include_router(currency.router)
app.include_router(inventory.router)
app.include_router(sales.router)
app.include_router(reports.router)
app.include_router(radar.router)
app.include_router(user_settings.router)
app.include_router(marketplace.router)
app.include_router(auto.router)
app.include_router(real_estate.router)
app.include_router(resale.router)  # FASHION-3a
app.include_router(facebook_groups_router)
app.include_router(tracked_router, prefix="/api/tracked-products")
app.include_router(logs_router)
app.include_router(auto_listings_router)
app.include_router(auto_lot_router)
app.include_router(re_monitor_router)
app.include_router(deals_router, prefix="/api/deals")  # SHOP-2a


# ────────────────────────────────────────────────────────────────────────────
# PKG-1 — frontend static exportat (frontend/out) servit direct din FastAPI.
# Se inregistreaza ULTIMUL (catch-all peste toate rutele). Daca out/ lipseste,
# backend-ul ramane API-only (dev cu `next dev` pe :3000 neschimbat).
# ────────────────────────────────────────────────────────────────────────────
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

def _resolve_frontend_out() -> Path:
    """Sub PyInstaller (onedir), frontend-ul static sta in folderul
    frontend_out/ de langa executabil (copiat de build — PKG-3b);
    in dev, in frontend/out din repo (generat de npm run build)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "frontend_out"
    return Path(__file__).resolve().parents[2] / "frontend" / "out"


FRONTEND_OUT = _resolve_frontend_out()

if (FRONTEND_OUT / "_next").is_dir():
    app.mount(
        "/_next",
        StaticFiles(directory=str(FRONTEND_OUT / "_next")),
        name="next_static",
    )


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    # /api/* nu e frontend: 404 JSON, niciodata HTML.
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    base = FRONTEND_OUT
    if not base.is_dir():
        return JSONResponse(
            {"detail": "Frontend static absent — ruleaza `npm run build` "
                       "in frontend/ sau porneste `next dev`."},
            status_code=404,
        )
    base_r = base.resolve()
    target = (base / full_path).resolve() if full_path else base_r / "index.html"
    # guard path-traversal: orice iese din out/ -> 404
    if not target.is_relative_to(base_r):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if target.is_file():
        return FileResponse(target)
    # conventia FLAT a exportului: /login -> login.html, /dashboard/alerts -> dashboard/alerts.html
    html = Path(str(target) + ".html")
    if html.is_file() and html.resolve().is_relative_to(base_r):
        return FileResponse(html)
    nf = base_r / "404.html"
    if nf.is_file():
        return FileResponse(nf, status_code=404)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


