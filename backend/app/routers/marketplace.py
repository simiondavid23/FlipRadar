"""Router HTTP pentru Modulul 1 Marketplace — cautare live pe platformele
generale (OLX, Vinted, LaJumate, Publi24, Okazii, eBay Kleinanzeigen).

Fiecare endpoint apeleaza scraperul asincron corespunzator. `filters` se
transmite ca JSON encodat in query string. /search-all ruleaza scraperele
selectate in paralel cu asyncio.gather.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.marketplace_saved import MarketplaceSaved
from app.models.marketplace_keyword_alert import MarketplaceKeywordAlert
from app.utils.auth import get_current_user
from app.scrapers.marketplace.olx_general import search_olx_general
from app.scrapers.marketplace.vinted_scraper import search_vinted
from app.scrapers.marketplace.lajumate_scraper import search_lajumate
from app.scrapers.marketplace.publi24_scraper import search_publi24
from app.scrapers.marketplace.okazii_scraper import search_okazii
from app.scrapers.marketplace.kleinanzeigen_scraper import search_kleinanzeigen

router = APIRouter(prefix="/api/marketplace", tags=["Marketplace"])


def _parse_filters(filters: Optional[str]) -> dict:
    """Decodeaza parametrul `filters` (JSON) intr-un dict; {} la eroare."""
    if not filters:
        return {}
    try:
        value = json.loads(filters)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


@router.get("/olx-general")
async def olx_general(
    q: str = Query(..., min_length=1),
    category: str = Query(""),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_olx_general(q, category, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "olx"}


@router.get("/vinted")
async def vinted(
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_vinted(q, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "vinted"}


@router.get("/lajumate")
async def lajumate(
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_lajumate(q, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "lajumate"}


@router.get("/publi24")
async def publi24(
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_publi24(q, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "publi24"}


@router.get("/okazii")
async def okazii(
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_okazii(q, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "okazii"}


@router.get("/kleinanzeigen")
async def kleinanzeigen(
    q: str = Query(..., min_length=1),
    category_id: str = Query(""),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    results = await search_kleinanzeigen(q, category_id, _parse_filters(filters))
    return {"results": results, "count": len(results), "source": "kleinanzeigen"}


@router.get("/search-all")
async def search_all(
    q: str = Query(..., min_length=1),
    platforms: str = Query("olx,vinted,okazii"),
    filters: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Cauta in paralel pe toate platformele selectate (asyncio.gather)."""
    f = _parse_filters(filters)
    builders = {
        "olx": lambda: search_olx_general(q, "", f),
        "vinted": lambda: search_vinted(q, f),
        "lajumate": lambda: search_lajumate(q, f),
        "publi24": lambda: search_publi24(q, f),
        "okazii": lambda: search_okazii(q, f),
        "kleinanzeigen": lambda: search_kleinanzeigen(q, "", f),
    }
    selected = [p.strip().lower() for p in (platforms or "").split(",") if p.strip() in builders]
    if not selected:
        return {"results": [], "by_platform": {}, "count": 0}

    coros = [builders[p]() for p in selected]
    settled = await asyncio.gather(*coros, return_exceptions=True)

    merged = []
    by_platform = {}
    for platform, res in zip(selected, settled):
        if isinstance(res, Exception):
            print(f"[search-all] {platform} error: {res}")
            by_platform[platform] = 0
            continue
        merged.extend(res)
        by_platform[platform] = len(res)

    return {"results": merged, "by_platform": by_platform, "count": len(merged)}


# ──────────────────────────────────────────────────────────────────────────────
# Anunturi salvate (marketplace_saved)
# ──────────────────────────────────────────────────────────────────────────────


class SavedCreate(BaseModel):
    platform: str
    external_id: Optional[str] = None
    title: str
    price: Optional[float] = None
    currency: str = "RON"
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


def _saved_to_dict(s: MarketplaceSaved) -> dict:
    return {
        "id": s.id,
        "platform": s.platform,
        "external_id": s.external_id,
        "title": s.title,
        "price": float(s.price) if s.price is not None else None,
        "currency": s.currency,
        "source_url": s.source_url,
        "thumbnail_url": s.thumbnail_url,
        "saved_at": s.saved_at.isoformat() if s.saved_at else None,
    }


@router.post("/saved")
def save_listing(
    data: SavedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (data.title or "").strip():
        raise HTTPException(status_code=400, detail="Titlul anuntului este obligatoriu.")

    # Evita duplicate: acelasi user + platforma + external_id (sau source_url).
    base = db.query(MarketplaceSaved).filter(
        MarketplaceSaved.user_id == current_user.id,
        MarketplaceSaved.platform == data.platform,
    )
    existing = None
    if data.external_id:
        existing = base.filter(MarketplaceSaved.external_id == data.external_id).first()
    elif data.source_url:
        existing = base.filter(MarketplaceSaved.source_url == data.source_url).first()
    if existing:
        return _saved_to_dict(existing)

    item = MarketplaceSaved(
        user_id=current_user.id,
        platform=data.platform,
        external_id=data.external_id,
        title=data.title.strip(),
        price=data.price,
        currency=data.currency or "RON",
        source_url=data.source_url,
        thumbnail_url=data.thumbnail_url,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _saved_to_dict(item)


@router.get("/saved")
def list_saved(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(MarketplaceSaved)
        .filter(MarketplaceSaved.user_id == current_user.id)
        .order_by(MarketplaceSaved.saved_at.desc())
        .all()
    )
    return [_saved_to_dict(s) for s in rows]


@router.delete("/saved/{saved_id}")
def delete_saved(
    saved_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(MarketplaceSaved)
        .filter(MarketplaceSaved.id == saved_id, MarketplaceSaved.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Anuntul salvat nu a fost gasit.")
    db.delete(item)
    db.commit()
    return {"message": "Anuntul a fost sters din salvate."}


# ──────────────────────────────────────────────────────────────────────────────
# Alerte keyword (marketplace_keyword_alerts)
# ──────────────────────────────────────────────────────────────────────────────


class KeywordAlertCreate(BaseModel):
    platform: str
    keyword: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    filters: Optional[dict] = None
    is_active: bool = True


class KeywordAlertUpdate(BaseModel):
    is_active: Optional[bool] = None
    keyword: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    filters: Optional[dict] = None


def _alert_to_dict(a: MarketplaceKeywordAlert) -> dict:
    return {
        "id": a.id,
        "platform": a.platform,
        "keyword": a.keyword,
        "category": a.category,
        "subcategory": a.subcategory,
        "filters": a.filters or {},
        "is_active": bool(a.is_active),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/keyword-alerts")
def list_keyword_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(MarketplaceKeywordAlert)
        .filter(MarketplaceKeywordAlert.user_id == current_user.id)
        .order_by(MarketplaceKeywordAlert.created_at.desc())
        .all()
    )
    return [_alert_to_dict(a) for a in rows]


@router.post("/keyword-alerts")
def create_keyword_alert(
    data: KeywordAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (data.keyword or "").strip():
        raise HTTPException(status_code=400, detail="Keyword-ul este obligatoriu.")
    if not (data.platform or "").strip():
        raise HTTPException(status_code=400, detail="Platforma este obligatorie.")
    alert = MarketplaceKeywordAlert(
        user_id=current_user.id,
        platform=data.platform,
        keyword=data.keyword.strip(),
        category=data.category or None,
        subcategory=data.subcategory or None,
        filters=data.filters or {},
        is_active=bool(data.is_active),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.put("/keyword-alerts/{alert_id}")
def update_keyword_alert(
    alert_id: int,
    data: KeywordAlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(MarketplaceKeywordAlert)
        .filter(MarketplaceKeywordAlert.id == alert_id, MarketplaceKeywordAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta nu a fost gasita.")
    if data.is_active is not None:
        alert.is_active = bool(data.is_active)
    if data.keyword is not None:
        alert.keyword = data.keyword.strip()
    if data.category is not None:
        alert.category = data.category or None
    if data.subcategory is not None:
        alert.subcategory = data.subcategory or None
    if data.filters is not None:
        alert.filters = data.filters or {}
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.delete("/keyword-alerts/{alert_id}")
def delete_keyword_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(MarketplaceKeywordAlert)
        .filter(MarketplaceKeywordAlert.id == alert_id, MarketplaceKeywordAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta nu a fost gasita.")
    db.delete(alert)
    db.commit()
    return {"message": "Alerta a fost stearsa."}
