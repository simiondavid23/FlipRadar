from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword as RealEstateKeyword
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/real-estate-monitor", tags=["real-estate-monitor"])


# ── Pydantic schemas ────────────────────────────────────────────

class KeywordCreate(BaseModel):
    name: str
    platform: str
    property_type: Optional[str] = None
    rooms: Optional[int] = None
    area_min: Optional[int] = None
    area_max: Optional[int] = None
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


@router.post("/feed/{listing_id}/flag-duplicate")
def flag_duplicate(
    listing_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import uuid
    listing = db.query(RealEstateListing).filter(
        RealEstateListing.id == listing_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    dup_id = payload.get("duplicate_of_id")
    other = db.query(RealEstateListing).filter(
        RealEstateListing.id == dup_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not other:
        raise HTTPException(404, "Anunțul duplicat negăsit.")

    group_id = listing.duplicate_group_id or other.duplicate_group_id or str(uuid.uuid4())
    listing.user_flagged_duplicate_id = dup_id
    listing.duplicate_level = 2
    listing.duplicate_group_id = group_id
    other.duplicate_group_id = group_id
    if other.duplicate_level is None or other.duplicate_level > 2:
        other.duplicate_level = 2
    db.commit()
    return {"ok": True, "duplicate_group_id": group_id}


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
    # numarul de grupuri de duplicate distincte
    dup_groups = db.query(func.count(func.distinct(RealEstateListing.duplicate_group_id))).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.duplicate_group_id.isnot(None),
    ).scalar() or 0

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
        "duplicate_groups": dup_groups,
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
            run_real_estate_scan(_db)
        except Exception as exc:
            print(f"[REScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"ok": True, "message": "Scanare imobiliare pornită în background."}
