import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from app.database import get_db
from app.models.user import User
from app.models.sale import Sale
from app.models.inventory import InventoryItem
from app.schemas.sale import SaleCreate, SaleUpdate, SaleResponse
from app.utils.auth import get_current_user
from app.utils.pdf_fonts import ensure_pdf_fonts
from app.services.currency_service import convert

router = APIRouter(prefix="/api/sales", tags=["Sales"])


@router.get("/", response_model=List[SaleResponse])
def get_sales(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all sales recorded by the current user."""
    return (
        db.query(Sale)
        .filter(Sale.user_id == current_user.id)
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .all()
    )


@router.get("/stats")
def get_sales_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summary: sales count, units, revenue and profit (EUR reference)."""
    rows = (
        db.query(
            Sale.currency,
            func.coalesce(func.sum(Sale.sale_price * Sale.quantity), 0.0),
            func.coalesce(func.sum(Sale.cost_price * Sale.quantity), 0.0),
            func.coalesce(func.sum(Sale.extra_costs), 0.0),
            func.coalesce(func.sum(Sale.quantity), 0),
            func.count(Sale.id),
        )
        .filter(Sale.user_id == current_user.id)
        .group_by(Sale.currency)
        .all()
    )

    total_revenue_eur = 0.0
    total_cost_eur = 0.0
    total_extra_eur = 0.0
    total_units = 0
    total_sales = 0
    for currency, revenue, cost, extra, units, sale_count in rows:
        total_revenue_eur += convert(float(revenue or 0), currency or "EUR", "EUR")
        total_cost_eur += convert(float(cost or 0), currency or "EUR", "EUR")
        total_extra_eur += convert(float(extra or 0), currency or "EUR", "EUR")
        total_units += int(units or 0)
        total_sales += int(sale_count or 0)

    # extra_costs e total pe vanzare (nu per unitate): intra in profit, dar total_cost_eur
    # ramane doar costul de achizitie.
    total_profit_eur = total_revenue_eur - total_cost_eur - total_extra_eur

    sales_without_cost = (
        db.query(func.count(Sale.id))
        .filter(Sale.user_id == current_user.id, Sale.cost_price.is_(None))
        .scalar() or 0
    )

    return {
        "total_sales": total_sales,
        "total_units_sold": total_units,
        "total_revenue_eur": round(total_revenue_eur, 2),
        "total_cost_eur": round(total_cost_eur, 2),
        "total_extra_costs_eur": round(total_extra_eur, 2),
        "total_profit_eur": round(total_profit_eur, 2),
        "sales_without_cost": int(sales_without_cost),
    }


@router.post("/", response_model=SaleResponse)
def create_sale(
    data: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a new sale.

    Daca `inventory_item_id` este setat, datele despre produs (nume, cost,
    moneda) se preiau automat din articolul de inventar, iar cantitatea
    vanduta se scade din stocul curent. Daca stocul ramas este 0, articolul
    se sterge automat din inventar.
    """
    payload = data.model_dump(exclude_none=True)
    # GE-6a: NU mai scoatem inventory_item_id din payload — ramane pe calea de succes ca
    # Sale(**payload) sa persiste legatura. Vanzarile manuale nu-l au (exclude_none).
    inventory_id = payload.get("inventory_item_id")

    inventory_item = None
    if inventory_id is not None:
        inventory_item = (
            db.query(InventoryItem)
            .filter(InventoryItem.id == inventory_id, InventoryItem.user_id == current_user.id)
            .first()
        )
        if not inventory_item:
            raise HTTPException(status_code=404, detail="Articolul de inventar nu a fost gasit.")
        if data.quantity > inventory_item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stocul disponibil este {inventory_item.quantity}, nu poti vinde {data.quantity}.",
            )
        # Auto-completare campuri lipsa din inventar
        payload.setdefault("product_name", inventory_item.name)
        payload.setdefault("cost_price", float(inventory_item.purchase_price))
        payload.setdefault("currency", inventory_item.currency)
        payload.setdefault("category", inventory_item.category)

    if not payload.get("product_name"):
        raise HTTPException(status_code=400, detail="Numele produsului este obligatoriu.")
    payload.setdefault("currency", "EUR")

    sale = Sale(user_id=current_user.id, **payload)
    db.add(sale)

    # Decrementeaza stocul daca am preluat dintr-un articol de inventar
    if inventory_item is not None:
        inventory_item.quantity -= data.quantity
        if inventory_item.quantity <= 0:
            db.delete(inventory_item)

    db.commit()
    db.refresh(sale)
    return sale


@router.put("/{sale_id}", response_model=SaleResponse)
def update_sale(
    sale_id: int,
    data: SaleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit an existing sale."""
    sale = (
        db.query(Sale)
        .filter(Sale.id == sale_id, Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Vanzarea nu a fost gasita")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sale, key, value)
    db.commit()
    db.refresh(sale)
    return sale


@router.get("/export-pdf")
def export_sales_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a PDF report of the current user's sales."""
    font_regular, font_bold = ensure_pdf_fonts()
    sales = (
        db.query(Sale)
        .filter(Sale.user_id == current_user.id)
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .all()
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18, spaceAfter=6, textColor=colors.HexColor("#1e40af"), fontName=font_bold)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#475569"), fontName=font_regular)

    elements = []
    elements.append(Paragraph("Raport Vanzari - FlipRadar", title_style))
    elements.append(Paragraph(
        f"Utilizator: {current_user.full_name or current_user.username} ({current_user.email})<br/>"
        f"Data generare: {datetime.now().strftime('%d.%m.%Y %H:%M')}<br/>"
        f"Total vanzari: {len(sales)}",
        sub_style,
    ))
    elements.append(Spacer(1, 0.5 * cm))

    # Summary totals (EUR)
    total_revenue_eur = 0.0
    total_cost_eur = 0.0
    total_extra_eur = 0.0
    total_units = 0
    for s in sales:
        total_revenue_eur += convert(float(s.sale_price or 0) * int(s.quantity or 0), s.currency or "EUR", "EUR")
        total_cost_eur += convert(float(s.cost_price or 0) * int(s.quantity or 0), s.currency or "EUR", "EUR")
        total_extra_eur += convert(float(s.extra_costs or 0), s.currency or "EUR", "EUR")
        total_units += int(s.quantity or 0)
    fara_cost = sum(1 for s in sales if s.cost_price is None)
    total_profit_eur = total_revenue_eur - total_cost_eur - total_extra_eur

    summary_data = [
        ["Venit total (EUR)", f"{total_revenue_eur:.2f}"],
        ["Cost total (EUR)", f"{total_cost_eur:.2f}"],
        ["Costuri suplimentare (EUR)", f"{total_extra_eur:.2f}"],
        ["Profit total (EUR)", f"{total_profit_eur:.2f}"],
        ["Unitati vandute", f"{total_units}"],
        ["Vanzari fara cost declarat", f"{fara_cost}"],
    ]
    summary_tbl = Table(summary_data, colWidths=[6 * cm, 4 * cm])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 0), (-1, -1), font_regular),
        ("FONTNAME", (0, 0), (0, -1), font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(summary_tbl)
    elements.append(Spacer(1, 0.6 * cm))

    # Details table
    header = ["Data", "Produs", "Cant.", "Pret vanzare", "Cost", "Extra", "Moneda", "Profit"]
    rows = [header]
    for s in sales:
        revenue = float(s.sale_price or 0) * int(s.quantity or 0)
        cost = float(s.cost_price or 0) * int(s.quantity or 0)
        extra = float(s.extra_costs or 0)
        profit = revenue - cost - extra
        rows.append([
            s.sold_at.strftime("%d.%m.%Y") if s.sold_at else "-",
            (s.product_name or "-")[:40],
            str(s.quantity or 0),
            f"{float(s.sale_price or 0):.2f}",
            f"{float(s.cost_price or 0):.2f}",
            f"{extra:.2f}" if s.extra_costs is not None else "-",
            s.currency or "EUR",
            f"{profit:.2f}",
        ])

    if len(rows) == 1:
        elements.append(Paragraph("Nu exista vanzari inregistrate.", sub_style))
    else:
        tbl = Table(rows, colWidths=[2.2 * cm, 3.9 * cm, 1.3 * cm, 2.3 * cm, 2.3 * cm, 1.6 * cm, 1.8 * cm, 2 * cm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_regular),
            ("FONTNAME", (0, 0), (-1, 0), font_bold),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(tbl)

    doc.build(elements)
    buf.seek(0)

    filename = f"vanzari_{current_user.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{sale_id}")
def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a sale."""
    sale = (
        db.query(Sale)
        .filter(Sale.id == sale_id, Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Vanzarea nu a fost gasita")

    # GE-6a: restituim stocul daca vanzarea a fost legata de un articol de inventar.
    if sale.inventory_item_id:
        item = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.id == sale.inventory_item_id,
                InventoryItem.user_id == current_user.id,
            )
            .first()
        )
        if item:
            item.quantity += sale.quantity
        else:
            # Articolul a fost auto-sters la stoc 0: il recreem din datele vanzarii.
            db.add(InventoryItem(
                user_id=current_user.id,
                name=sale.product_name,
                category=sale.category,
                quantity=sale.quantity,
                purchase_price=float(sale.cost_price) if sale.cost_price is not None else 0.0,
                currency=sale.currency or "RON",
                notes=f"Recreat automat la stergerea vanzarii #{sale.id}",
            ))

    db.delete(sale)
    db.commit()
    return {"message": "Vanzarea a fost stearsa"}
