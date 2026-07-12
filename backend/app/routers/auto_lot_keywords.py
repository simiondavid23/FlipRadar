"""Router pentru Loturi Auto (Copart/IAAI/SCA/OpenLane) — calchiat pe
auto_listings_keywords.py. Prefix /api/auto-lots.

CRUD keyword-uri + feed monitorizat (AutoLot) + stats + scan-now (scopat per-user).
Cautarea manuala punctuala ramane in routers/auto.py (/api/auto/lots/search)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.auto_lot_keyword import AutoLotKeyword
from app.models.auto_lot import AutoLot
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/auto-lots", tags=["auto-lots"])

_PLATFORMS = {"copart", "iaai", "sca", "openlane"}


# ── Pydantic schemas ────────────────────────────────────────────

class LotKeywordCreate(BaseModel):
    name: str
    platform: str
    make: Optional[str] = None
    model: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    damage_primary: Optional[str] = None
    bid_max: Optional[float] = None
    location_state: Optional[str] = None
    is_active: bool = True
    notify_email: bool = False
    notify_discord: bool = False
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    polling_interval_minutes: int = 15


class LotKeywordUpdate(LotKeywordCreate):
    pass


def _kw_dict(kw: AutoLotKeyword) -> dict:
    d = {c.name: getattr(kw, c.name) for c in kw.__table__.columns}
    if d.get("bid_max") is not None:
        d["bid_max"] = float(d["bid_max"])
    return d


def _lot_dict(lot: AutoLot) -> dict:
    d = {c.name: getattr(lot, c.name) for c in lot.__table__.columns}
    for money in ("current_bid", "buy_now_price"):
        if d.get(money) is not None:
            d[money] = float(d[money])
    for dt in ("auction_date", "created_at", "last_seen_at"):
        val = d.get(dt)
        if val is not None and hasattr(val, "isoformat"):
            d[dt] = val.isoformat()
    return d


def _validate_platform(platform: str) -> None:
    if (platform or "").lower() not in _PLATFORMS:
        raise HTTPException(
            400, f"Platformă invalidă. Valori permise: {', '.join(sorted(_PLATFORMS))}.")


# ── Keywords CRUD ───────────────────────────────────────────────

@router.get("/keywords")
def list_keywords(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kws = db.query(AutoLotKeyword).filter(
        AutoLotKeyword.user_id == current_user.id
    ).order_by(AutoLotKeyword.created_at.desc()).all()
    return [_kw_dict(k) for k in kws]


@router.post("/keywords", status_code=201)
def create_keyword(
    payload: LotKeywordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_platform(payload.platform)
    kw = AutoLotKeyword(user_id=current_user.id, **payload.model_dump())
    db.add(kw); db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.put("/keywords/{kw_id}")
def update_keyword(
    kw_id: int,
    payload: LotKeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_platform(payload.platform)
    kw = db.query(AutoLotKeyword).filter(
        AutoLotKeyword.id == kw_id,
        AutoLotKeyword.user_id == current_user.id,
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
    kw = db.query(AutoLotKeyword).filter(
        AutoLotKeyword.id == kw_id,
        AutoLotKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    db.delete(kw); db.commit()
    return {"ok": True}


# ── Feed ─────────────────────────────────────────────────────────

@router.get("/feed")
def get_feed(
    platform: Optional[str] = None,
    status: str = "active",
    keyword_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AutoLot).filter(
        AutoLot.user_id == current_user.id,
        AutoLot.status == status,
    )
    if platform:
        q = q.filter(AutoLot.platform == platform)
    if keyword_id:
        q = q.filter(AutoLot.keyword_id == keyword_id)
    total = q.count()
    items = q.order_by(AutoLot.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_lot_dict(i) for i in items]}


@router.patch("/feed/{lot_id}/status")
def update_lot_status(
    lot_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lot = db.query(AutoLot).filter(
        AutoLot.id == lot_id,
        AutoLot.user_id == current_user.id,
    ).first()
    if not lot:
        raise HTTPException(404, "Lot negăsit.")
    new_status = payload.get("status")
    if new_status not in ("active", "saved", "ignored"):
        raise HTTPException(400, "Status invalid (active/saved/ignored).")
    lot.status = new_status
    db.commit()
    return {"ok": True}


# ── Stats ────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(AutoLot).filter(
        AutoLot.user_id == current_user.id).count()
    active_keywords = db.query(AutoLotKeyword).filter(
        AutoLotKeyword.user_id == current_user.id,
        AutoLotKeyword.is_active == True,
    ).count()
    by_platform_rows = db.query(
        AutoLot.platform, func.count(AutoLot.id)
    ).filter(
        AutoLot.user_id == current_user.id,
        AutoLot.status == "active",
    ).group_by(AutoLot.platform).all()
    by_platform = {(p or "?"): int(c) for p, c in by_platform_rows}
    return {
        "total_lots": total,
        "active_keywords": active_keywords,
        "by_platform": by_platform,
    }


# ── Scan now (scopat pe current_user, NU global) ─────────────────

@router.post("/scan-now")
@limiter.limit("5/minute")
def scan_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pornește o scanare imediată DOAR pentru keyword-urile active de loturi ale
    userului curent, într-un thread de fundal (nu run_auto_lot_scan_global)."""
    import threading
    from app.database import SessionLocal
    from app.services.auto_lot_scanner import run_auto_lot_scan_for_user
    from app.services.log_manager import set_log_user

    user_id = current_user.id

    def _background_scan():
        set_log_user(user_id)  # MON-4 — jurnalele scanului manual apartin acestui user
        _db = SessionLocal()
        try:
            run_auto_lot_scan_for_user(_db, user_id)
        except Exception as exc:
            print(f"[AutoLotScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"ok": True, "message": "Scanare loturi pornită în background."}
