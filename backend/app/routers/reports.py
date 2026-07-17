from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
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
        q = q.filter(func.date(Sale.sold_at) >= start)
    if end:
        q = q.filter(func.date(Sale.sold_at) <= end)
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
    vanzari_fara_cost = 0
    roi_cost_total = 0.0
    roi_profit_total = 0.0
    cat_buckets: dict[str, dict] = {}
    prod_buckets: dict[str, dict] = {}
    day_buckets: dict[str, dict] = {}

    for s in sales:
        qty = int(s.quantity or 1)
        rev = _to_eur(float(s.sale_price or 0) * qty, s.currency)
        cost = _to_eur(float(s.cost_price or 0) * qty, s.currency)
        # extra_costs = total pe vanzare (nu per unitate); intra in cost_linie pentru profit.
        extra = _to_eur(float(s.extra_costs or 0), s.currency)
        cost_linie = cost + extra
        profit = rev - cost_linie
        venit_total += rev
        cost_total += cost_linie

        if s.cost_price is None:
            vanzari_fara_cost += 1

        # ROI AGREGAT (GE-6b): acumulam cost si profit doar pentru vanzarile cu cost de
        # achizitie declarat (cele doar cu extra nu intra).
        if s.cost_price is not None and cost_linie > 0:
            roi_cost_total += cost_linie
            roi_profit_total += profit

        # Categoria denormalizata pe vanzare (GE-3); fallback pe join-ul de nume pentru
        # vanzarile vechi sau manuale fara categorie.
        category = s.category or name_to_category.get(s.product_name) or "Necunoscut"
        cb = cat_buckets.setdefault(category, {"categorie": category, "profit": 0.0, "cost": 0.0, "count": 0})
        cb["profit"] += profit
        cb["cost"] += cost_linie
        cb["count"] += qty

        pb = prod_buckets.setdefault(s.product_name or "Necunoscut", {"name": s.product_name or "Necunoscut", "profit": 0.0, "revenue": 0.0, "cost": 0.0})
        pb["profit"] += profit
        pb["revenue"] += rev
        pb["cost"] += cost_linie

        if s.sold_at:
            day_key = s.sold_at.date().isoformat()
            db_b = day_buckets.setdefault(day_key, {"data": day_key, "venit": 0.0, "profit": 0.0})
            db_b["venit"] += rev
            db_b["profit"] += profit

    profit_total = venit_total - cost_total

    # FlipRadar — adaugam `roi` per categorie (profit/cost*100) pe langa profit,
    # pentru graficul "Categorii dupa ROI mediu".
    top_categorii = sorted(
        (
            {
                "categorie": c["categorie"],
                "profit": round(c["profit"], 2),
                "count": c["count"],
                "roi": round((c["profit"] / c["cost"] * 100.0), 2) if c["cost"] > 0 else 0.0,
            }
            for c in cat_buckets.values()
        ),
        key=lambda x: x["profit"], reverse=True
    )[:5]

    # DASH-1 — categoria cu cel mai mare ROI, calculata pe TOATE categoriile cu
    # cost declarat (top_categorii e top-5 dupa profit, deci o categorie cu ROI
    # mare dar profit mic putea lipsi). None daca nu exista cost > 0 sau daca
    # ROI-ul maxim e <= 0 — cardul de pe dashboard se ascunde in acest caz.
    best_roi_categorie = None
    best_roi_val = 0.0
    for c in cat_buckets.values():
        if c["cost"] > 0:
            roi_c = c["profit"] / c["cost"] * 100.0
            if roi_c > best_roi_val:
                best_roi_val = roi_c
                best_roi_categorie = {
                    "categorie": c["categorie"],
                    "roi": round(roi_c, 2),
                    "profit": round(c["profit"], 2),
                    "count": c["count"],
                }

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
        "vanzari_fara_cost": vanzari_fara_cost,
        "venit_total": round(venit_total, 2),
        "profit_total": round(profit_total, 2),
        "roi_mediu": round((roi_profit_total / roi_cost_total * 100), 1) if roi_cost_total > 0 else 0,
        "top_categorii": top_categorii,
        "best_roi_categorie": best_roi_categorie,
        "top_produse": top_produse,
        "vanzari_pe_zi": vanzari_pe_zi,
    }
