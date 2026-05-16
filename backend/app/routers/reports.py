from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, func
from app.database import get_db
from app.models.user import User
from app.models.sale import Sale
from app.models.inventory import InventoryItem
from app.utils.auth import get_current_user
from app.services.currency_service import convert

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return None


def _to_eur(amount: float, currency: Optional[str]) -> float:
    try:
        return float(convert(float(amount or 0), currency or "EUR", "EUR"))
    except Exception:
        return float(amount or 0)


@router.get("/summary")
def get_reports_summary(
    date_from: Optional[str] = Query(None, description="ISO date — inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date — inclusive"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated profitability stats over the user's sales catalog.

    All amounts are reported in EUR. `top_categorii` joins sales against
    the user's inventory by name to infer a category (sales table itself
    doesn't carry one).
    """
    start = _parse_iso_date(date_from)
    end = _parse_iso_date(date_to)

    q = db.query(Sale).filter(Sale.user_id == current_user.id)
    if start:
        q = q.filter(cast(Sale.sold_at, Date) >= start)
    if end:
        q = q.filter(cast(Sale.sold_at, Date) <= end)
    sales = q.all()

    # Build a name -> category map from inventory for this user
    inventory_rows = (
        db.query(InventoryItem.name, InventoryItem.category)
        .filter(InventoryItem.user_id == current_user.id)
        .all()
    )
    name_to_category: dict[str, str] = {}
    for name, category in inventory_rows:
        if name and category and name not in name_to_category:
            name_to_category[name] = category

    total_vanzari = len(sales)
    venit_total = 0.0
    cost_total = 0.0
    roi_values: list[float] = []
    cat_buckets: dict[str, dict] = {}
    prod_buckets: dict[str, dict] = {}
    day_buckets: dict[str, dict] = {}

    for s in sales:
        qty = int(s.quantity or 1)
        rev = _to_eur(float(s.sale_price or 0) * qty, s.currency)
        cost = _to_eur(float(s.cost_price or 0) * qty, s.currency)
        profit = rev - cost
        venit_total += rev
        cost_total += cost

        if cost > 0:
            roi_values.append((profit / cost) * 100.0)

        category = name_to_category.get(s.product_name, "Necunoscut")
        cb = cat_buckets.setdefault(category, {"categorie": category, "profit": 0.0, "count": 0})
        cb["profit"] += profit
        cb["count"] += qty

        pb = prod_buckets.setdefault(s.product_name or "Necunoscut", {"name": s.product_name or "Necunoscut", "profit": 0.0, "revenue": 0.0, "cost": 0.0})
        pb["profit"] += profit
        pb["revenue"] += rev
        pb["cost"] += cost

        if s.sold_at:
            day_key = s.sold_at.date().isoformat()
            db_b = day_buckets.setdefault(day_key, {"data": day_key, "venit": 0.0, "profit": 0.0})
            db_b["venit"] += rev
            db_b["profit"] += profit

    profit_total = venit_total - cost_total
    roi_mediu = round(sum(roi_values) / len(roi_values), 2) if roi_values else 0.0

    top_categorii = sorted(
        ({"categorie": c["categorie"], "profit": round(c["profit"], 2), "count": c["count"]} for c in cat_buckets.values()),
        key=lambda x: x["profit"], reverse=True
    )[:5]

    top_produse = []
    for p in sorted(prod_buckets.values(), key=lambda x: x["profit"], reverse=True)[:5]:
        roi_p = (p["profit"] / p["cost"] * 100.0) if p["cost"] > 0 else 0.0
        top_produse.append({
            "name": p["name"],
            "profit": round(p["profit"], 2),
            "roi": round(roi_p, 2),
        })

    # Fill missing days between start/end with zeros for a continuous chart
    if start and end and end >= start:
        full_range = []
        cursor = start
        while cursor <= end:
            key = cursor.isoformat()
            bucket = day_buckets.get(key, {"data": key, "venit": 0.0, "profit": 0.0})
            full_range.append({"data": key, "venit": round(bucket["venit"], 2), "profit": round(bucket["profit"], 2)})
            cursor += timedelta(days=1)
        vanzari_pe_zi = full_range
    else:
        vanzari_pe_zi = sorted(
            ({"data": d["data"], "venit": round(d["venit"], 2), "profit": round(d["profit"], 2)} for d in day_buckets.values()),
            key=lambda x: x["data"],
        )

    return {
        "total_vanzari": total_vanzari,
        "venit_total": round(venit_total, 2),
        "profit_total": round(profit_total, 2),
        "roi_mediu": roi_mediu,
        "top_categorii": top_categorii,
        "top_produse": top_produse,
        "vanzari_pe_zi": vanzari_pe_zi,
    }
