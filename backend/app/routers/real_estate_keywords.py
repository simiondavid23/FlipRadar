import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword as RealEstateKeyword
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing
from app.services.real_estate.excel_exporter import build_re_xlsx
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/real-estate-monitor", tags=["real-estate-monitor"])


# ── Pydantic schemas ────────────────────────────────────────────

class KeywordCreate(BaseModel):
    name: str
    platform: str
    property_type: Optional[str] = None
    tip_anunt: Optional[str] = "vanzare"
    rooms: Optional[int] = None
    area_min: Optional[int] = None
    area_max: Optional[int] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_currency: Optional[str] = "EUR"
    zone: Optional[str] = None
    city: Optional[str] = "București"
    floor_min: Optional[int] = None
    floor_max: Optional[int] = None
    furnished: Optional[bool] = None
    query: Optional[str] = None
    is_active: bool = True
    notify_email: bool = False
    notify_discord: bool = False
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    polling_interval_minutes: int = 30

class KeywordUpdate(KeywordCreate):
    pass


def _kw_dict(kw: RealEstateKeyword) -> dict:
    return {c.name: getattr(kw, c.name) for c in kw.__table__.columns}


@router.get("/categories")
def get_re_categories():
    """Campuri tehnice confirmate per platforma (pentru formularul dinamic de keyword +
    tab-ul de cautare manuala). GET /api/real-estate-monitor/categories.

    Nu exista categorii per-platforma distincte ca la Auto — tip_proprietate/tip_anunt sunt
    comune tuturor platformelor (frontend realEstateConstants.js), deci nu le duplicam aici.
    Doar campurile cu confirmed:True sunt de conectat; frontend-ul le foloseste pentru a sti
    ce filtre suporta fiecare platforma.
    """
    from app.scrapers.real_estate.re_categories import RE_TECHNICAL_FIELDS
    return {"technical_fields": RE_TECHNICAL_FIELDS}


# ── Keywords CRUD ───────────────────────────────────────────────

@router.get("/keywords")
def list_keywords(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kws = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id
    ).order_by(RealEstateKeyword.created_at.desc()).all()
    return [_kw_dict(k) for k in kws]


@router.post("/keywords", status_code=201)
def create_keyword(
    payload: KeywordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = RealEstateKeyword(user_id=current_user.id, **payload.model_dump())
    db.add(kw); db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.put("/keywords/{kw_id}")
def update_keyword(
    kw_id: int,
    payload: KeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.id == kw_id,
        RealEstateKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    for k, v in payload.model_dump().items():
        setattr(kw, k, v)
    db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.delete("/keywords/{kw_id}")
def delete_keyword(
    kw_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.id == kw_id,
        RealEstateKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    db.delete(kw); db.commit()
    return {"ok": True}


# ── Feed endpoints ───────────────────────────────────────────────

def _listing_dict(listing) -> dict:
    d = {c.name: getattr(listing, c.name) for c in listing.__table__.columns}
    d["price"] = float(d["price"]) if d["price"] is not None else None
    d["price_per_sqm"] = float(d["price_per_sqm"]) if d["price_per_sqm"] is not None else None
    return d


@router.get("/feed")
def get_feed(
    platform: Optional[str] = None,
    grade: Optional[str] = None,
    status: str = "active",
    zone: Optional[str] = None,
    rooms: Optional[int] = None,
    keyword_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == status,
    )
    if platform: q = q.filter(RealEstateListing.platform == platform)
    if grade:    q = q.filter(RealEstateListing.grade == grade)
    if zone:     q = q.filter(RealEstateListing.zone_normalized == zone)
    if rooms:    q = q.filter(RealEstateListing.rooms == rooms)
    if keyword_id: q = q.filter(RealEstateListing.keyword_id == keyword_id)
    total = q.count()
    items = q.order_by(RealEstateListing.found_at.desc())\
             .offset(offset).limit(limit).all()
    return {"total": total, "items": [_listing_dict(i) for i in items]}


# Definit ÎNAINTE de /feed/{listing_id}/... ca "export" să nu fie prins de rutele cu param.
@router.get("/feed/export")
def export_feed(
    platform: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export .xlsx al feed-ului Imobiliare — filtre platform/grad/status/keyword ca lista."""
    q = db.query(RealEstateListing).filter(RealEstateListing.user_id == current_user.id)
    if platform:
        q = q.filter(RealEstateListing.platform == platform)
    if grade:
        q = q.filter(RealEstateListing.grade == grade)
    if status and status != "all":
        q = q.filter(RealEstateListing.status == status)
    if keyword_id:
        q = q.filter(RealEstateListing.keyword_id == keyword_id)
    items = q.order_by(RealEstateListing.found_at.desc()).limit(5000).all()

    kw_ids = {i.keyword_id for i in items if i.keyword_id}
    kw_map = (
        {k.id: k.name for k in db.query(RealEstateKeyword).filter(RealEstateKeyword.id.in_(kw_ids)).all()}
        if kw_ids else {}
    )
    rows = [{
        "title": i.title, "platform": i.platform, "grade": i.grade,
        "price": float(i.price) if i.price is not None else None, "currency": i.currency,
        "price_per_sqm": float(i.price_per_sqm) if i.price_per_sqm is not None else None,
        "rooms": i.rooms, "area_sqm": i.area_sqm,
        "zone_normalized": i.zone_normalized, "zone_raw": i.zone_raw, "floor": i.floor,
        "seller_id": i.seller_id, "keyword_name": kw_map.get(i.keyword_id),
        "found_at": i.found_at, "status": i.status, "url": i.url,
    } for i in items]

    xlsx_bytes = build_re_xlsx(rows)
    filename = f"imobiliare_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/feed/{listing_id}/status")
def update_listing_status(
    listing_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(RealEstateListing).filter(
        RealEstateListing.id == listing_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    listing.status = payload.get("status", listing.status)
    db.commit()
    return {"ok": True}


@router.delete("/feed/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(RealEstateListing).filter(
        RealEstateListing.id == listing_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    db.delete(listing); db.commit()
    return {"ok": True}


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func
    total = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id).count()
    by_grade = db.query(
        RealEstateListing.grade, func.count(RealEstateListing.id)
    ).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == "active",
    ).group_by(RealEstateListing.grade).all()
    by_platform = db.query(
        RealEstateListing.platform, func.count(RealEstateListing.id)
    ).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == "active",
    ).group_by(RealEstateListing.platform).all()
    kw_count = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id,
        RealEstateKeyword.is_active == True,
    ).count()
    # Status sesiune Facebook — daca exista keyword FB Marketplace sau FB Groups.
    has_fb_keyword = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id,
        RealEstateKeyword.is_active == True,
        RealEstateKeyword.platform.in_(("facebook_marketplace", "facebook_groups")),
    ).first() is not None
    fb_session_valid = None
    if has_fb_keyword:
        try:
            import glob, os
            files = glob.glob("data/facebook_session_*.json")
            session_path = max(files, key=os.path.getmtime) if files else None
            if session_path:
                from app.scrapers.auto.listings.facebook_auto_scraper import _is_session_valid
                fb_session_valid = _is_session_valid(session_path)
            else:
                fb_session_valid = False
        except Exception:
            fb_session_valid = False

    return {
        "total_listings": total,
        "active_keywords": kw_count,
        "by_grade": {g: c for g, c in by_grade},
        "by_platform": {p: c for p, c in by_platform},
        "facebook_session_valid": fb_session_valid,
        "has_facebook_keywords": has_fb_keyword,
    }


# MODIFICARE 18 — impactul stergerii unui keyword imobiliar (listinguri asociate).
@router.get("/keywords/{keyword_id}/impact")
def get_keyword_impact(
    keyword_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_count = db.query(func.count(RealEstateListing.id)).filter(
        RealEstateListing.keyword_id == keyword_id,
        RealEstateListing.user_id == current_user.id,
    ).scalar() or 0
    return {"listing_count": listing_count, "seen_count": 0}


@router.post("/scan-now")
@limiter.limit("5/minute")
def scan_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger immediate background scan for real estate keywords."""
    import threading
    from app.database import SessionLocal
    from app.services.real_estate_scanner import run_real_estate_scan

    user_id = current_user.id

    def _background_scan():
        _db = SessionLocal()
        try:
            run_real_estate_scan(_db, user_id=user_id)
        except Exception as exc:
            print(f"[REScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"ok": True, "message": "Scanare imobiliare pornită în background."}
