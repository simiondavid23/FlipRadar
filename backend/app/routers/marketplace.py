"""Router HTTP pentru Modulul 1 Marketplace — cautare live pe platformele
generale (OLX, Vinted, LaJumate, Publi24, Okazii, eBay Kleinanzeigen).

Fiecare endpoint apeleaza scraperul asincron corespunzator. `filters` se
transmite ca JSON encodat in query string. /search-all ruleaza scraperele
selectate in paralel cu asyncio.gather.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.marketplace_saved import MarketplaceSaved
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


def _paginate(all_results: list, page: int, per_page: int) -> tuple:
    """MODIFICARE 17 — paginare in memorie peste setul intors de scraper.
    Scraperele aduc tot setul (cateva pagini), deci feliem aici pentru butonul
    "Încarcă mai multe". Returneaza (felie, has_more)."""
    page = max(1, page)
    per_page = max(1, per_page)
    start = (page - 1) * per_page
    end = page * per_page
    sliced = all_results[start:end]
    has_more = len(all_results) > end
    return sliced, has_more


@router.get("/olx-general")
@limiter.limit("5/minute")
async def olx_general(
    request: Request,
    q: str = Query(..., min_length=1),
    category: str = Query(""),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_olx_general(q, category, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "olx",
            "page": page, "has_more": has_more}


@router.get("/vinted")
@limiter.limit("5/minute")
async def vinted(
    request: Request,
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_vinted(q, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "vinted",
            "page": page, "has_more": has_more}


@router.get("/lajumate")
@limiter.limit("5/minute")
async def lajumate(
    request: Request,
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_lajumate(q, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "lajumate",
            "page": page, "has_more": has_more}


@router.get("/publi24")
@limiter.limit("5/minute")
async def publi24(
    request: Request,
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_publi24(q, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "publi24",
            "page": page, "has_more": has_more}


@router.get("/okazii")
@limiter.limit("5/minute")
async def okazii(
    request: Request,
    q: str = Query(..., min_length=1),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_okazii(q, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "okazii",
            "page": page, "has_more": has_more}


@router.get("/kleinanzeigen")
@limiter.limit("5/minute")
async def kleinanzeigen(
    request: Request,
    q: str = Query(..., min_length=1),
    category_id: str = Query(""),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    results = await search_kleinanzeigen(q, category_id, _parse_filters(filters))
    sliced, has_more = _paginate(results, page, per_page)
    return {"results": sliced, "count": len(sliced), "source": "kleinanzeigen",
            "page": page, "has_more": has_more}


@router.get("/search-all")
@limiter.limit("5/minute")
async def search_all(
    request: Request,
    q: str = Query(..., min_length=1),
    platforms: str = Query("olx,vinted,okazii"),
    filters: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
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

    sliced, has_more = _paginate(merged, page, per_page)
    return {"results": sliced, "by_platform": by_platform, "count": len(sliced),
            "page": page, "has_more": has_more}


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
