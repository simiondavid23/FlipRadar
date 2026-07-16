from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from app.database import get_db
from app.models.product import Product
from app.models.tracked_product import TrackedProduct
from app.models.alert import Alert
from app.models.price_history import PriceHistory
from app.models.user import User
from app.models.inventory import InventoryItem
from app.models.sale import Sale
from app.utils.auth import get_current_user
from app.services.currency_service import convert

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# MODIFICARE 15 — status scheduler (joburi + next run) pentru widget-ul de dashboard.
@router.get("/scheduler-status")
def scheduler_status(current_user: User = Depends(get_current_user)):
    from app.main import scheduler
    # Nume prietenoase pentru ID-urile reale de joburi din lifespan.
    job_names = {
        "radar_scan": "Radar Piață",
        "auto_listings_scan": "Auto Anunțuri",
        "real_estate_scan": "Imobiliare",
        "re_daily_cleanup": "Cleanup imobiliare",
        "discord_queue_cleanup": "Cleanup Discord queue",
        "log_entries_cleanup": "Cleanup logs DB",
        "check_alerts": "Verificare alerte",
        "real_estate_alerts": "Alerte imobiliare",
        "radar_daily_cleanup": "Cleanup Radar",
        "ml_sold_detection": "ML detecție vânzări",
        "retrain_models": "Reantrenare ML",
        "facebook_group_checks": "Grupuri Facebook",
        "facebook_cookie_expiry_check": "Expirare cookies FB",
    }
    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job_names.get(job.id, job.id),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "running": scheduler.running,
        })
    return {"jobs": jobs_info, "scheduler_running": scheduler.running}


@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard statistics for the current user. All amounts are EUR."""

    total_products = (
        db.query(func.count(Product.id))
        .filter(Product.user_id == current_user.id)
        .scalar() or 0
    )

    monitored_count = (
        db.query(func.count(TrackedProduct.id))
        .filter(
            TrackedProduct.user_id == current_user.id,
            TrackedProduct.monitoring_active == True,
        )
        .scalar() or 0
    )

    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == current_user.id, Alert.is_active == True)
        .scalar() or 0
    )

    triggered_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == current_user.id, Alert.is_triggered == True)
        .scalar() or 0
    )

    total_price_records = (
        db.query(func.count(PriceHistory.id))
        .join(Product, PriceHistory.product_id == Product.id)
        .filter(Product.user_id == current_user.id)
        .scalar() or 0
    )

    # Inventory total per currency (single grouped SQL, then one convert() per currency)
    inventory_rows = (
        db.query(
            InventoryItem.currency,
            func.coalesce(func.sum(InventoryItem.purchase_price * InventoryItem.quantity), 0.0),
            func.count(InventoryItem.id),
        )
        .filter(InventoryItem.user_id == current_user.id)
        .group_by(InventoryItem.currency)
        .all()
    )
    inventory_total_eur = 0.0
    inventory_items_count = 0
    for currency, subtotal, count in inventory_rows:
        inventory_total_eur += convert(float(subtotal or 0), currency or "RON", "EUR")
        inventory_items_count += int(count or 0)

    # Sales total per currency
    sales_rows = (
        db.query(
            Sale.currency,
            func.coalesce(func.sum(Sale.sale_price * Sale.quantity), 0.0),
            func.count(Sale.id),
        )
        .filter(Sale.user_id == current_user.id)
        .group_by(Sale.currency)
        .all()
    )
    sales_total_eur = 0.0
    sales_count = 0
    for currency, subtotal, count in sales_rows:
        sales_total_eur += convert(float(subtotal or 0), currency or "RON", "EUR")
        sales_count += int(count or 0)

    # Total products value (user-scoped) grouped by currency
    products_rows = (
        db.query(
            Product.currency,
            func.coalesce(func.sum(Product.current_price), 0.0),
        )
        .filter(Product.user_id == current_user.id)
        .group_by(Product.currency)
        .all()
    )
    total_products_value = 0.0
    for currency, subtotal in products_rows:
        total_products_value += convert(float(subtotal or 0), currency or "EUR", "EUR")

    return {
        "total_products": total_products,
        "monitored_count": monitored_count,
        "active_alerts": active_alerts,
        "triggered_alerts": triggered_alerts,
        "total_price_records": total_price_records,
        "total_products_value_eur": round(total_products_value, 2),
        "inventory_total_eur": round(inventory_total_eur, 2),
        "inventory_items_count": inventory_items_count,
        "sales_total_eur": round(sales_total_eur, 2),
        "sales_count": sales_count,
        "user": {
            "username": current_user.username,
            "full_name": current_user.full_name,
            "member_since": current_user.created_at.isoformat() if current_user.created_at else None,
        },
    }


@router.get("/sales-timeseries")
def get_sales_timeseries(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sales aggregated per day for the last N days (EUR)."""
    start = (datetime.now() - timedelta(days=days - 1)).date()

    rows = (
        db.query(
            cast(Sale.sold_at, Date).label("day"),
            Sale.currency,
            func.coalesce(func.sum(Sale.sale_price * Sale.quantity), 0.0).label("revenue"),
            func.coalesce(func.sum(Sale.cost_price * Sale.quantity), 0.0).label("cost"),
            func.coalesce(func.sum(Sale.quantity), 0).label("units"),
        )
        .filter(Sale.user_id == current_user.id, cast(Sale.sold_at, Date) >= start)
        .group_by(cast(Sale.sold_at, Date), Sale.currency)
        .all()
    )

    by_day: dict[str, dict] = {}
    for day, currency, revenue, cost, units in rows:
        key = day.isoformat()
        bucket = by_day.setdefault(key, {"day": key, "revenue_eur": 0.0, "cost_eur": 0.0, "profit_eur": 0.0, "units": 0})
        rev_eur = convert(float(revenue or 0), currency or "EUR", "EUR")
        cost_eur = convert(float(cost or 0), currency or "EUR", "EUR")
        bucket["revenue_eur"] += rev_eur
        bucket["cost_eur"] += cost_eur
        bucket["profit_eur"] += rev_eur - cost_eur
        bucket["units"] += int(units or 0)

    # Fill missing days with zeros for a continuous chart
    result = []
    for offset in range(days):
        d = (start + timedelta(days=offset)).isoformat()
        bucket = by_day.get(d, {"day": d, "revenue_eur": 0.0, "cost_eur": 0.0, "profit_eur": 0.0, "units": 0})
        result.append({
            "day": bucket["day"],
            "revenue_eur": round(bucket["revenue_eur"], 2),
            "cost_eur": round(bucket["cost_eur"], 2),
            "profit_eur": round(bucket["profit_eur"], 2),
            "units": bucket["units"],
        })

    return {"days": days, "data": result}


@router.get("/top-products")
def get_top_products(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top products by revenue (EUR)."""
    rows = (
        db.query(
            Sale.product_name,
            Sale.currency,
            func.coalesce(func.sum(Sale.sale_price * Sale.quantity), 0.0).label("revenue"),
            func.coalesce(func.sum(Sale.quantity), 0).label("units"),
        )
        .filter(Sale.user_id == current_user.id)
        .group_by(Sale.product_name, Sale.currency)
        .all()
    )

    by_name: dict[str, dict] = {}
    for name, currency, revenue, units in rows:
        key = name or "Necunoscut"
        bucket = by_name.setdefault(key, {"name": key, "revenue_eur": 0.0, "units": 0})
        bucket["revenue_eur"] += convert(float(revenue or 0), currency or "EUR", "EUR")
        bucket["units"] += int(units or 0)

    sorted_products = sorted(by_name.values(), key=lambda x: x["revenue_eur"], reverse=True)[:limit]
    return [
        {"name": p["name"], "revenue_eur": round(p["revenue_eur"], 2), "units": p["units"]}
        for p in sorted_products
    ]
