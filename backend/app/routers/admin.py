from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from app.database import get_db
from app.models.user import User
from app.models.product import Product
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.models.inventory import InventoryItem
from app.models.sale import Sale
from app.models.support_ticket import SupportTicket, TicketMessage
from app.models.chat_message import ChatMessage
from app.models.notification import Notification
from app.models.favorite import FavoriteItem
from app.schemas.admin import (
    AdminStats, RecentUser, TicketSummary, TicketUser,
    TicketDetail, TicketMessageResponse, SimpleMessage, AlertCheckResult,
    AdminUserSummary, AdminUserDetail, UserFeatureUpdate, UserActiveUpdate,
    AdminProductItem, AdminWatchlistItem, AdminAlertItem, AdminMiniUser,
    AdminInventoryItem, AdminSaleItem, AdminFavoriteItem, AdminChatMessageItem,
)
from app.utils.auth import get_current_user
from app.utils.alert_checker import check_alerts

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependință care verifică că utilizatorul curent este administrator."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acces interzis. Doar administratorii pot accesa aceasta resursa.")
    return current_user


@router.get("/stats", response_model=AdminStats)
def get_admin_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Returnează statisticile panoului de administrare."""
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    total_products = db.query(func.count(Product.id)).scalar()
    total_watchlist = db.query(func.count(WatchlistItem.id)).scalar()
    total_alerts = db.query(func.count(Alert.id)).scalar()
    active_alerts = db.query(func.count(Alert.id)).filter(Alert.is_active == True).scalar()

    open_tickets = db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == "open").scalar()
    in_progress_tickets = db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == "in_progress").scalar()
    total_tickets = db.query(func.count(SupportTicket.id)).scalar()

    recent_users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(10)
        .all()
    )

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_products=total_products,
        total_watchlist=total_watchlist,
        total_alerts=total_alerts,
        active_alerts=active_alerts,
        open_tickets=open_tickets,
        in_progress_tickets=in_progress_tickets,
        total_tickets=total_tickets,
        recent_users=[RecentUser.model_validate(u) for u in recent_users],
    )


@router.get("/tickets", response_model=list[TicketSummary])
def get_all_tickets(
    user_id: Optional[int] = Query(None, description="Only tickets opened by this user"),
    status: Optional[str] = Query(None, description="open | in_progress | closed | all"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Returnează toate ticketele de suport. Filtrele opționale permit adminului să restrângă
    rezultatele la un anumit utilizator (pentru istoric) sau la un anumit status."""
    q = db.query(SupportTicket)
    if user_id is not None:
        q = q.filter(SupportTicket.user_id == user_id)
    if status and status != "all":
        q = q.filter(SupportTicket.status == status)
    tickets = q.order_by(SupportTicket.updated_at.desc()).all()
    return [
        TicketSummary(
            id=t.id,
            subject=t.subject,
            status=t.status,
            priority=t.priority,
            created_at=t.created_at,
            updated_at=t.updated_at,
            user=TicketUser.model_validate(t.user),
            message_count=len(t.messages),
        )
        for t in tickets
    ]


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Returnează detaliile unui ticket împreună cu mesajele asociate."""
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticketul nu a fost gasit")

    return TicketDetail(
        id=ticket.id,
        subject=ticket.subject,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
        user=TicketUser.model_validate(ticket.user),
        messages=[
            TicketMessageResponse(
                id=m.id,
                content=m.content,
                is_admin=m.is_admin,
                sender_name=m.sender.full_name or m.sender.username,
                created_at=m.created_at,
            )
            for m in ticket.messages
        ],
    )


class TicketReply(BaseModel):
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Mesajul nu poate fi gol")
        return v.strip()


@router.post("/tickets/{ticket_id}/reply", response_model=SimpleMessage)
def admin_reply_ticket(
    ticket_id: int,
    reply: TicketReply,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Răspunsul adminului la un ticket de suport."""
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticketul nu a fost gasit")

    msg = TicketMessage(
        ticket_id=ticket_id,
        sender_id=admin.id,
        content=reply.content,
        is_admin=True,
    )
    db.add(msg)
    ticket.status = "in_progress"
    db.commit()

    return SimpleMessage(message="Raspunsul a fost trimis")


@router.post("/run-alert-check", response_model=AlertCheckResult)
def run_alert_check(admin: User = Depends(require_admin)):
    """Declanșează manual verificatorul de alerte de preț (util pentru demo-uri)."""
    triggered = check_alerts()
    return AlertCheckResult(triggered=triggered)


@router.put("/tickets/{ticket_id}/close", response_model=SimpleMessage)
def close_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Închide un ticket de suport."""
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticketul nu a fost gasit")

    if ticket.status == "closed":
        return SimpleMessage(message="Ticketul este deja inchis")

    ticket.status = "closed"
    db.commit()
    return SimpleMessage(message="Ticketul a fost inchis")


# =========================================================================
# Listinguri de activitate globală (opțional filtrate pe un singur user)
# =========================================================================
# Alimentează cardurile de statistici clicabile din panoul de admin și
# tile-urile clicabile din pagina de detalii a unui utilizator specific.
# Fiecare endpoint acceptă un query param opțional `user_id` — când e prezent,
# rezultatele sunt filtrate pe acel user astfel încât adminul poate analiza fără o pagină separată.

_DEFAULT_LIMIT = 500  # Limită maximă pentru ca un cont abuziv să nu blocheze UI-ul.


def _mini_user(u: Optional[User]) -> Optional[AdminMiniUser]:
    if u is None:
        return None
    return AdminMiniUser(id=u.id, username=u.username, email=u.email, full_name=u.full_name)


def _product_item(p: Optional[Product]) -> Optional[AdminProductItem]:
    if p is None:
        return None
    return AdminProductItem(
        id=p.id, name=p.name, ean=p.ean, sku=p.sku, source=p.source,
        source_url=p.source_url, category=p.category,
        current_price=p.current_price, currency=p.currency,
        image_url=p.image_url, created_at=p.created_at,
        owner=_mini_user(p.user) if hasattr(p, "user") else None,
    )


@router.get("/products", response_model=list[AdminProductItem])
def list_products(
    user_id: Optional[int] = Query(None, description="Filter by owner user id"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Toate produsele înregistrate pe platformă, cele mai recente primele.

    Trimite `user_id=<N>` pentru a restricționa lista la produsele unui singur utilizator.
    """
    q = db.query(Product).options(joinedload(Product.user))
    if user_id is not None:
        q = q.filter(Product.user_id == user_id)
    products = q.order_by(Product.created_at.desc()).limit(limit).all()
    return [_product_item(p) for p in products]


@router.get("/products/report")
def products_report(
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date (inclusive)"),
    date_to: Optional[str] = Query(None, description="ISO date (inclusive)"),
    category: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Raport de produse cross-user cu filtre și sumar agregat."""
    from datetime import datetime as _dt

    q = db.query(Product).options(joinedload(Product.user))
    if price_min is not None:
        q = q.filter(Product.current_price >= price_min)
    if price_max is not None:
        q = q.filter(Product.current_price <= price_max)
    if category:
        q = q.filter(Product.category.ilike(f"%{category.strip()}%"))

    def _parse(value):
        if not value:
            return None
        try:
            return _dt.fromisoformat(value)
        except Exception:
            return None

    df = _parse(date_from)
    dt = _parse(date_to)
    if df is not None:
        q = q.filter(Product.created_at >= df)
    if dt is not None:
        q = q.filter(Product.created_at <= dt)

    products = q.order_by(Product.created_at.desc()).limit(limit).all()

    price_values = [float(p.current_price) for p in products if p.current_price is not None]
    roi_values: list[float] = []
    profit_estimat_total = 0.0
    for p in products:
        if p.current_price and p.resale_price and float(p.current_price) > 0:
            diff = float(p.resale_price) - float(p.current_price)
            roi_values.append((diff / float(p.current_price)) * 100.0)
            if diff > 0:
                profit_estimat_total += diff

    summary = {
        "count": len(products),
        "pret_mediu": round(sum(price_values) / len(price_values), 2) if price_values else 0.0,
        "pret_min": round(min(price_values), 2) if price_values else 0.0,
        "pret_max": round(max(price_values), 2) if price_values else 0.0,
        "roi_mediu": round(sum(roi_values) / len(roi_values), 2) if roi_values else 0.0,
        "profit_estimat_total": round(profit_estimat_total, 2),
    }

    rows = []
    for p in products:
        roi = None
        if p.current_price and p.resale_price and float(p.current_price) > 0:
            roi = round(((float(p.resale_price) - float(p.current_price)) / float(p.current_price)) * 100.0, 2)
        rows.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.current_price,
            "resale_price": p.resale_price,
            "currency": p.currency,
            "roi": roi,
            "source": p.source,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "owner_email": p.user.email if p.user else None,
        })

    return {"products": rows, "summary": summary}


@router.get("/products/report/pdf")
def products_report_pdf(
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date (inclusive)"),
    date_to: Optional[str] = Query(None, description="ISO date (inclusive)"),
    category: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """FlipRadar — ITEM 17: acelasi raport de produse, exportat ca PDF (ReportLab)."""
    from datetime import datetime as _dt
    import io
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.pdfgen import canvas as _canvas

    # --- Acelasi filtru ca /products/report ---
    q = db.query(Product).options(joinedload(Product.user))
    if price_min is not None:
        q = q.filter(Product.current_price >= price_min)
    if price_max is not None:
        q = q.filter(Product.current_price <= price_max)
    if category:
        q = q.filter(Product.category.ilike(f"%{category.strip()}%"))

    def _parse(value):
        if not value:
            return None
        try:
            return _dt.fromisoformat(value)
        except Exception:
            return None

    df = _parse(date_from)
    dt = _parse(date_to)
    if df is not None:
        q = q.filter(Product.created_at >= df)
    if dt is not None:
        q = q.filter(Product.created_at <= dt)

    products = q.order_by(Product.created_at.desc()).limit(limit).all()

    price_values = [float(p.current_price) for p in products if p.current_price is not None]
    roi_values: list[float] = []
    profit_estimat_total = 0.0
    for p in products:
        if p.current_price and p.resale_price and float(p.current_price) > 0:
            diff = float(p.resale_price) - float(p.current_price)
            roi_values.append((diff / float(p.current_price)) * 100.0)
            if diff > 0:
                profit_estimat_total += diff

    pret_mediu = round(sum(price_values) / len(price_values), 2) if price_values else 0.0
    roi_mediu = round(sum(roi_values) / len(roi_values), 2) if roi_values else 0.0

    # --- Footer cu numerotare "pagina X din Y" ---
    class _NumberedCanvas(_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_states = []

        def showPage(self):
            self._saved_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_states)
            for state in self._saved_states:
                self.__dict__.update(state)
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.HexColor("#94a3b8"))
                self.drawCentredString(
                    A4[0] / 2.0, 1.0 * cm,
                    f"FlipRadar Admin - pagina {self._pageNumber} din {total}",
                )
                super().showPage()
            super().save()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18, spaceAfter=6, textColor=colors.HexColor("#1e40af"))
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475569"))

    # Descrierea filtrelor active
    active_filters = []
    if price_min is not None:
        active_filters.append(f"pret min: {price_min}")
    if price_max is not None:
        active_filters.append(f"pret max: {price_max}")
    if date_from:
        active_filters.append(f"de la: {date_from}")
    if date_to:
        active_filters.append(f"pana la: {date_to}")
    if category:
        active_filters.append(f"categorie: {category}")
    filters_text = ", ".join(active_filters) if active_filters else "niciun filtru aplicat"

    elements = []
    elements.append(Paragraph("Raport Produse - FlipRadar Admin", title_style))
    elements.append(Paragraph(
        f"Data generare: {_dt.now().strftime('%d.%m.%Y %H:%M')}<br/>"
        f"Filtre active: {filters_text}",
        sub_style,
    ))
    elements.append(Spacer(1, 0.5 * cm))

    # Tabel summary
    summary_data = [
        ["Total produse", f"{len(products)}"],
        ["Pret mediu", f"{pret_mediu:.2f}"],
        ["ROI mediu", f"{roi_mediu:.2f}%"],
        ["Profit estimat total", f"{round(profit_estimat_total, 2):.2f}"],
    ]
    summary_tbl = Table(summary_data, colWidths=[6 * cm, 4 * cm])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(summary_tbl)
    elements.append(Spacer(1, 0.6 * cm))

    # Tabel produse (8 coloane, font 8pt)
    header = ["Produs", "Categorie", "Pret", "Pret rev.", "ROI%", "Sursa", "Proprietar", "Adaugat"]
    rows = [header]
    for p in products:
        roi = None
        if p.current_price and p.resale_price and float(p.current_price) > 0:
            roi = round(((float(p.resale_price) - float(p.current_price)) / float(p.current_price)) * 100.0, 2)
        cur = p.currency or ""
        rows.append([
            (p.name or "-")[:35],
            (p.category or "-")[:20],
            f"{float(p.current_price):.2f} {cur}" if p.current_price is not None else "-",
            f"{float(p.resale_price):.2f} {cur}" if p.resale_price is not None else "-",
            f"{roi:.2f}%" if roi is not None else "-",
            (p.source or "-")[:14],
            (p.user.email if p.user else "-")[:24],
            p.created_at.strftime("%d.%m.%Y") if p.created_at else "-",
        ])

    if len(rows) == 1:
        elements.append(Paragraph("Niciun produs in intervalul/filtru selectat.", sub_style))
    else:
        tbl = Table(
            rows,
            colWidths=[4.4 * cm, 2.2 * cm, 1.9 * cm, 1.9 * cm, 1.2 * cm, 2.0 * cm, 3.0 * cm, 1.6 * cm],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 1), (4, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(tbl)

    doc.build(elements, canvasmaker=_NumberedCanvas)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=raport_admin_{_dt.now().strftime('%Y%m%d_%H%M')}.pdf"},
    )


@router.get("/watchlist", response_model=list[AdminWatchlistItem])
def list_watchlist(
    user_id: Optional[int] = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Toate intrările din watchlist de pe platformă (sau pentru un singur utilizator)."""
    q = (
        db.query(WatchlistItem)
        .options(joinedload(WatchlistItem.user), joinedload(WatchlistItem.product))
    )
    if user_id is not None:
        q = q.filter(WatchlistItem.user_id == user_id)
    items = q.order_by(WatchlistItem.added_at.desc()).limit(limit).all()

    return [
        AdminWatchlistItem(
            id=it.id,
            notes=it.notes,
            added_at=it.added_at,
            product=_product_item(it.product),
            owner=_mini_user(it.user),
        )
        for it in items
    ]


@router.get("/alerts", response_model=list[AdminAlertItem])
def list_alerts(
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Filter: active | triggered | inactive | all"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Toate alertele de preț (opțional filtrate după utilizator și/sau status)."""
    q = db.query(Alert).options(joinedload(Alert.user), joinedload(Alert.product))
    if user_id is not None:
        q = q.filter(Alert.user_id == user_id)
    if status == "active":
        q = q.filter(Alert.is_active == True)
    elif status == "triggered":
        q = q.filter(Alert.is_triggered == True)
    elif status == "inactive":
        q = q.filter(Alert.is_active == False)
    # "all" sau None: fără filtru pe status.
    alerts = q.order_by(Alert.created_at.desc()).limit(limit).all()

    return [
        AdminAlertItem(
            id=a.id,
            target_price=a.target_price,
            currency=a.currency,
            alert_type=a.alert_type,
            is_active=a.is_active,
            is_triggered=a.is_triggered,
            triggered_at=a.triggered_at,
            created_at=a.created_at,
            product=_product_item(a.product),
            owner=_mini_user(a.user),
        )
        for a in alerts
    ]


@router.get("/inventory", response_model=list[AdminInventoryItem])
def list_inventory(
    user_id: Optional[int] = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Articolele din inventar de pe toată platforma (sau pentru un singur utilizator)."""
    q = db.query(InventoryItem).options(joinedload(InventoryItem.user))
    if user_id is not None:
        q = q.filter(InventoryItem.user_id == user_id)
    items = q.order_by(InventoryItem.created_at.desc()).limit(limit).all()
    return [
        AdminInventoryItem(
            id=it.id, name=it.name, category=it.category, sku=it.sku,
            quantity=it.quantity, purchase_price=it.purchase_price,
            currency=it.currency, source=it.source, notes=it.notes,
            purchased_at=it.purchased_at, created_at=it.created_at,
            owner=_mini_user(it.user),
        )
        for it in items
    ]


@router.get("/sales", response_model=list[AdminSaleItem])
def list_sales(
    user_id: Optional[int] = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Vânzările înregistrate pe toată platforma (sau pentru un singur utilizator)."""
    q = db.query(Sale).options(joinedload(Sale.user))
    if user_id is not None:
        q = q.filter(Sale.user_id == user_id)
    sales = q.order_by(Sale.sold_at.desc()).limit(limit).all()
    return [
        AdminSaleItem(
            id=s.id, product_name=s.product_name, quantity=s.quantity,
            sale_price=s.sale_price, currency=s.currency, cost_price=s.cost_price,
            platform=s.platform, buyer=s.buyer, notes=s.notes,
            sold_at=s.sold_at, created_at=s.created_at,
            owner=_mini_user(s.user),
        )
        for s in sales
    ]


@router.get("/favorites", response_model=list[AdminFavoriteItem])
def list_favorites(
    user_id: Optional[int] = Query(None),
    kind: Optional[str] = Query(None, description="favorite | blacklist | all"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Intrările de favorite + blacklist (același tabel, flag diferit)."""
    q = (
        db.query(FavoriteItem)
        .options(joinedload(FavoriteItem.user), joinedload(FavoriteItem.product))
    )
    if user_id is not None:
        q = q.filter(FavoriteItem.user_id == user_id)
    if kind == "favorite":
        q = q.filter(FavoriteItem.is_blacklisted == False)
    elif kind == "blacklist":
        q = q.filter(FavoriteItem.is_blacklisted == True)
    # "all" sau None: fără filtru.
    items = q.order_by(FavoriteItem.added_at.desc()).limit(limit).all()
    return [
        AdminFavoriteItem(
            id=it.id,
            is_blacklisted=bool(it.is_blacklisted),
            notes=it.notes,
            added_at=it.added_at,
            product=_product_item(it.product),
            owner=_mini_user(it.user),
        )
        for it in items
    ]


@router.get("/chat-messages", response_model=list[AdminChatMessageItem])
def list_chat_messages(
    user_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None, description="user | assistant | all"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=2000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Mesajele AI chat — opțional filtrate pe un singur utilizator sau rol."""
    q = db.query(ChatMessage).options(joinedload(ChatMessage.user))
    if user_id is not None:
        q = q.filter(ChatMessage.user_id == user_id)
    if role == "user":
        q = q.filter(ChatMessage.role == "user")
    elif role == "assistant":
        q = q.filter(ChatMessage.role == "assistant")
    messages = q.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    return [
        AdminChatMessageItem(
            id=m.id,
            role=m.role,
            content=m.content,
            needs_staff=bool(m.needs_staff),
            created_at=m.created_at,
            owner=_mini_user(m.user),
        )
        for m in messages
    ]


# =========================================================================
# Administrare per utilizator
# =========================================================================

def _count(db: Session, model, **filters) -> int:
    """Alias scurt pentru un query COUNT(*) cu filtre de egalitate."""
    q = db.query(func.count(model.id))
    for col, value in filters.items():
        q = q.filter(getattr(model, col) == value)
    return int(q.scalar() or 0)


def _user_summary_counts(db: Session, user_id: int) -> dict:
    """Sumar compact folosit pentru fiecare rând din tabelul de utilizatori."""
    return {
        "products_count": _count(db, Product, user_id=user_id),
        "watchlist_count": _count(db, WatchlistItem, user_id=user_id),
        "active_alerts_count": _count(db, Alert, user_id=user_id, is_active=True),
        "sales_count": _count(db, Sale, user_id=user_id),
    }


@router.get("/users", response_model=list[AdminUserSummary])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Returnează toți utilizatorii cu contorizări rapide de activitate.

    Numărătorile se fac cu câte un SQL per model per utilizator. La dimensiuni normale
    (zeci de utilizatori) e ieftin; dacă devine lent, se poate înlocui cu un agregat GROUP BY + LEFT JOIN.
    """
    users = db.query(User).order_by(User.created_at.desc()).all()

    rows: list[AdminUserSummary] = []
    for u in users:
        rows.append(
            AdminUserSummary(
                id=u.id,
                email=u.email,
                username=u.username,
                full_name=u.full_name,
                is_active=u.is_active,
                is_admin=u.is_admin,
                can_use_ai=u.can_use_ai,
                can_use_scraping=u.can_use_scraping,
                can_use_alerts=u.can_use_alerts,
                can_use_import_export=u.can_use_import_export,
                created_at=u.created_at,
                updated_at=u.updated_at,
                **_user_summary_counts(db, u.id),
            )
        )
    return rows


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Snapshot complet de activitate pentru un utilizator — alimentează panoul de detalii al adminului."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilizatorul nu a fost gasit")

    # Agregăm veniturile și profitul din vânzări. `cost_price` poate fi NULL, deci
    # facem coalesce la 0 înainte de înmulțire — altfel SUM returnează NULL.
    sales_agg = (
        db.query(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.sale_price * Sale.quantity), 0.0),
            func.coalesce(
                func.sum((Sale.sale_price - func.coalesce(Sale.cost_price, 0.0)) * Sale.quantity),
                0.0,
            ),
            func.max(Sale.sold_at),
        )
        .filter(Sale.user_id == user_id)
        .one()
    )
    sales_count, sales_revenue, sales_profit, last_sale_at = sales_agg

    # Valoarea inventarului — același guard pentru NULL.
    inventory_agg = (
        db.query(
            func.count(InventoryItem.id),
            func.coalesce(func.sum(InventoryItem.purchase_price * InventoryItem.quantity), 0.0),
        )
        .filter(InventoryItem.user_id == user_id)
        .one()
    )
    inventory_count, inventory_value = inventory_agg

    last_chat_at = (
        db.query(func.max(ChatMessage.created_at))
        .filter(ChatMessage.user_id == user_id)
        .scalar()
    )

    favorites_count = (
        db.query(func.count(FavoriteItem.id))
        .filter(FavoriteItem.user_id == user_id, FavoriteItem.is_blacklisted == False)
        .scalar() or 0
    )
    blacklist_count = (
        db.query(func.count(FavoriteItem.id))
        .filter(FavoriteItem.user_id == user_id, FavoriteItem.is_blacklisted == True)
        .scalar() or 0
    )

    return AdminUserDetail(
        id=u.id,
        email=u.email,
        username=u.username,
        full_name=u.full_name,
        is_active=u.is_active,
        is_admin=u.is_admin,
        created_at=u.created_at,
        updated_at=u.updated_at,
        can_use_ai=u.can_use_ai,
        can_use_scraping=u.can_use_scraping,
        can_use_alerts=u.can_use_alerts,
        can_use_import_export=u.can_use_import_export,
        products_count=_count(db, Product, user_id=user_id),
        watchlist_count=_count(db, WatchlistItem, user_id=user_id),
        favorites_count=int(favorites_count),
        blacklist_count=int(blacklist_count),
        total_alerts=_count(db, Alert, user_id=user_id),
        active_alerts=_count(db, Alert, user_id=user_id, is_active=True),
        triggered_alerts=_count(db, Alert, user_id=user_id, is_triggered=True),
        inventory_count=int(inventory_count or 0),
        inventory_value=float(inventory_value or 0.0),
        sales_count=int(sales_count or 0),
        sales_revenue=float(sales_revenue or 0.0),
        sales_profit=float(sales_profit or 0.0),
        tickets_count=_count(db, SupportTicket, user_id=user_id),
        open_tickets=_count(db, SupportTicket, user_id=user_id, status="open"),
        chat_messages_count=_count(db, ChatMessage, user_id=user_id),
        unread_notifications=_count(db, Notification, user_id=user_id, is_read=False),
        last_sale_at=last_sale_at,
        last_chat_at=last_chat_at,
    )


def _guard_self(admin: User, user_id: int):
    """Un admin nu se poate bloca singur prin modificarea propriilor flag-uri/status activ."""
    if admin.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Nu iti poti modifica propriile drepturi de cont. Cere altui admin.",
        )


@router.put("/users/{user_id}/active", response_model=AdminUserSummary)
def set_user_active(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Activează sau dezactivează un cont de utilizator.

    Dezactivarea face ca `get_current_user` să returneze 403 la următoarea cerere,
    chiar dacă utilizatorul mai deține un JWT valid — accesul este revocat imediat.
    """
    _guard_self(admin, user_id)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilizatorul nu a fost gasit")

    u.is_active = bool(payload.is_active)
    db.commit()
    db.refresh(u)

    return AdminUserSummary(
        id=u.id, email=u.email, username=u.username, full_name=u.full_name,
        is_active=u.is_active, is_admin=u.is_admin,
        can_use_ai=u.can_use_ai, can_use_scraping=u.can_use_scraping,
        can_use_alerts=u.can_use_alerts,
        can_use_import_export=u.can_use_import_export,
        created_at=u.created_at, updated_at=u.updated_at,
        **_user_summary_counts(db, u.id),
    )


@router.put("/users/{user_id}/features", response_model=AdminUserSummary)
def update_user_features(
    user_id: int,
    payload: UserFeatureUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Actualizează unul sau mai multe flag-uri de funcționalitate ale unui utilizator.

    Doar câmpurile trimise de apelant sunt scrise — celelalte rămân cu valorile curente.
    Permite UI-ului să trimită câte un PUT per checkbox fără round-trip complet.
    """
    _guard_self(admin, user_id)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilizatorul nu a fost gasit")

    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            continue
        setattr(u, key, bool(value))

    if not changes:
        raise HTTPException(status_code=400, detail="Nu ai trimis niciun flag de actualizat.")

    db.commit()
    db.refresh(u)

    return AdminUserSummary(
        id=u.id, email=u.email, username=u.username, full_name=u.full_name,
        is_active=u.is_active, is_admin=u.is_admin,
        can_use_ai=u.can_use_ai, can_use_scraping=u.can_use_scraping,
        can_use_alerts=u.can_use_alerts,
        can_use_import_export=u.can_use_import_export,
        created_at=u.created_at, updated_at=u.updated_at,
        **_user_summary_counts(db, u.id),
    )
