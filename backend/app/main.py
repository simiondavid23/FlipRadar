from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth, products, watchlist, alerts, dashboard, ai_chat, ai_analysis, admin, support
from app.routers import favorites, notifications, scraping, import_export
from app.routers import currency, inventory, sales

# Import all models
from app.models import user, product, price_history, product_source
from app.models import watchlist as watchlist_model
from app.models import alert, chat_message, support_ticket
from app.models import favorite, notification
from app.models import inventory as inventory_model
from app.models import sale as sale_model

# Create all database tables
Base.metadata.create_all(bind=engine)

# Apply any pending column-level migrations for existing tables
from app.utils.db_migrate import run_migrations
run_migrations()

from app.utils.alert_checker import check_alerts

scheduler = BackgroundScheduler(timezone="Europe/Bucharest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        check_alerts,
        "interval",
        minutes=15,
        id="check_alerts",
        replace_existing=True,
        next_run_time=None,
    )
    scheduler.start()
    print("[Scheduler] Started - check_alerts runs every 15 minutes.")

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
