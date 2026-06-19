"""Router /api/auto — calculator import + loturi din licitatii (Copart/IAAI/SCA/OpenLane)."""
import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.auto_lot import AutoLot
from app.models.auto_listing import AutoListing
from app.utils.auth import get_current_user
from app.services.ai_service import extract_auto_features_from_description
from app.scrapers.auto.lots.copart_public import search_copart_lots
from app.scrapers.auto.lots.iaai_public import search_iaai_lots
from app.scrapers.auto.lots.sca_auctions import search_sca_lots
from app.scrapers.auto.lots.openlane_scraper import search_openlane_lots
from app.scrapers.auto.listings.olx_auto import search_olx_auto
from app.scrapers.auto.listings.autovit_scraper import search_autovit
from app.scrapers.auto.listings.mobile_de_scraper import search_mobile_de
from app.scrapers.auto.listings.autoscout24_scraper import search_autoscout24
from app.scrapers.auto.listings.facebook_auto_scraper import search_facebook_auto
from app.scrapers.auto.listings.kleinanzeigen_auto import search_kleinanzeigen_auto

router = APIRouter(prefix="/api/auto", tags=["Auto"])


# ──────────────────────────────────────────────────────────────────────────────
# Calculator import
# ──────────────────────────────────────────────────────────────────────────────


class ImportCalculatorInput(BaseModel):
    bid_price_usd: float
    buyers_fee_pct: float = 0.10        # 10% default Copart
    transport_eur: float = 1200         # estimat
    repair_cost_eur: float = 0
    registration_cost_eur: float = 300  # estimat Romania
    usd_to_eur_rate: float = 0.92


@router.post("/calculate-import")
def calculate_import(
    data: ImportCalculatorInput,
    current_user: User = Depends(get_current_user),
):
    """Estimeaza costul total de import al unui vehicul din licitatie (USA -> RO)."""
    bid_eur = round(data.bid_price_usd * data.usd_to_eur_rate, 2)
    buyers_fee_eur = round(bid_eur * data.buyers_fee_pct, 2)
    subtotal_before_customs = round(bid_eur + buyers_fee_eur + data.transport_eur, 2)
    customs_duty = round(subtotal_before_customs * 0.065, 2)   # 6.5% taxa vamala auto
    vat = round((subtotal_before_customs + customs_duty) * 0.19, 2)  # TVA 19%
    total_import_cost = round(
        subtotal_before_customs + customs_duty + vat
        + data.repair_cost_eur + data.registration_cost_eur,
        2,
    )

    breakdown = [
        {"label": "Pret licitatie (EUR)", "amount": bid_eur},
        {"label": f"Comision casa licitatie ({round(data.buyers_fee_pct * 100, 1)}%)", "amount": buyers_fee_eur},
        {"label": "Transport estimat", "amount": round(data.transport_eur, 2)},
        {"label": "Taxa vamala (6.5%)", "amount": customs_duty},
        {"label": "TVA (19%)", "amount": vat},
        {"label": "Reparatii", "amount": round(data.repair_cost_eur, 2)},
        {"label": "Inmatriculare", "amount": round(data.registration_cost_eur, 2)},
    ]

    return {
        "bid_eur": bid_eur,
        "buyers_fee_eur": buyers_fee_eur,
        "transport_eur": round(data.transport_eur, 2),
        "customs_duty_eur": customs_duty,
        "vat_eur": vat,
        "repair_cost_eur": round(data.repair_cost_eur, 2),
        "registration_cost_eur": round(data.registration_cost_eur, 2),
        "total_cost_eur": total_import_cost,
        "breakdown": breakdown,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Loturi din licitatii
# ──────────────────────────────────────────────────────────────────────────────


def _parse_filters(filters: Optional[str]) -> dict:
    if not filters:
        return {}
    try:
        v = json.loads(filters)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


@router.get("/lots/search")
async def search_lots(
    q: str = Query("", description="Cuvant cheie (marca/model)"),
    platforms: str = Query("copart,iaai", description="Lista platforme separate prin virgula"),
    filters: Optional[str] = Query(None, description="JSON encodat cu filtre (make, model, ...)"),
    current_user: User = Depends(get_current_user),
):
    """Cauta loturi pe platformele selectate, in paralel (asyncio.gather)."""
    f = _parse_filters(filters)
    builders = {
        "copart": lambda: search_copart_lots(q, f),
        "iaai": lambda: search_iaai_lots(q, f),
        "sca": lambda: search_sca_lots(q, f),
        "openlane": lambda: search_openlane_lots(q, f),
    }
    selected = [p.strip().lower() for p in (platforms or "").split(",") if p.strip() in builders]
    if not selected:
        return {"results": [], "by_platform": {}, "count": 0}

    settled = await asyncio.gather(*[builders[p]() for p in selected], return_exceptions=True)
    merged, by_platform = [], {}
    for platform, res in zip(selected, settled):
        if isinstance(res, Exception):
            print(f"[auto/lots/search] {platform} error: {res}")
            by_platform[platform] = 0
            continue
        merged.extend(res)
        by_platform[platform] = len(res)

    return {"results": merged, "by_platform": by_platform, "count": len(merged)}


class LotSave(BaseModel):
    platform: str
    lot_number: Optional[str] = None
    title: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    odometer: Optional[int] = None
    damage_primary: Optional[str] = None
    damage_secondary: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    auction_date: Optional[str] = None
    thumbnail_url: Optional[str] = None
    source_url: Optional[str] = None
    current_bid: Optional[float] = None
    buy_now_price: Optional[float] = None
    title_type: Optional[str] = None
    starts: Optional[bool] = None
    drives: Optional[bool] = None
    keys_present: Optional[bool] = None
    vin: Optional[str] = None
    ai_description_extract: Optional[dict] = None


def _lot_to_dict(lot: AutoLot) -> dict:
    return {
        "id": lot.id,
        "platform": lot.platform,
        "lot_number": lot.lot_number,
        "title": lot.title,
        "make": lot.make,
        "model": lot.model,
        "year": lot.year,
        "odometer": lot.odometer,
        "damage_primary": lot.damage_primary,
        "damage_secondary": lot.damage_secondary,
        "location_city": lot.location_city,
        "location_state": lot.location_state,
        "auction_date": lot.auction_date.isoformat() if lot.auction_date else None,
        "thumbnail_url": lot.thumbnail_url,
        "source_url": lot.source_url,
        "current_bid": float(lot.current_bid) if lot.current_bid is not None else None,
        "buy_now_price": float(lot.buy_now_price) if lot.buy_now_price is not None else None,
        "title_type": lot.title_type,
        "starts": lot.starts,
        "drives": lot.drives,
        "keys_present": lot.keys_present,
        "vin": lot.vin,
        "ai_description_extract": lot.ai_description_extract,
        "saved": bool(lot.saved),
        "created_at": lot.created_at.isoformat() if lot.created_at else None,
    }


def _parse_auction_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


@router.post("/lots/save")
def save_lot(
    data: LotSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Salveaza un lot in tabela auto_lot cu saved=True."""
    if not (data.platform or "").strip():
        raise HTTPException(status_code=400, detail="Platforma este obligatorie.")

    # Dedup pe (user, platform, lot_number) cand lot_number e prezent.
    existing = None
    if data.lot_number:
        existing = (
            db.query(AutoLot)
            .filter(
                AutoLot.user_id == current_user.id,
                AutoLot.platform == data.platform,
                AutoLot.lot_number == data.lot_number,
            )
            .first()
        )
    if existing:
        existing.saved = True
        db.commit()
        db.refresh(existing)
        return _lot_to_dict(existing)

    lot = AutoLot(
        user_id=current_user.id,
        platform=data.platform,
        lot_number=data.lot_number,
        title=data.title,
        make=data.make,
        model=data.model,
        year=data.year,
        odometer=data.odometer,
        damage_primary=data.damage_primary,
        damage_secondary=data.damage_secondary,
        location_city=data.location_city,
        location_state=data.location_state,
        auction_date=_parse_auction_date(data.auction_date),
        thumbnail_url=data.thumbnail_url,
        source_url=data.source_url,
        current_bid=data.current_bid,
        buy_now_price=data.buy_now_price,
        title_type=data.title_type,
        starts=data.starts,
        drives=data.drives,
        keys_present=data.keys_present,
        vin=data.vin,
        ai_description_extract=data.ai_description_extract,
        saved=True,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return _lot_to_dict(lot)


@router.get("/lots/saved")
def list_saved_lots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(AutoLot)
        .filter(AutoLot.user_id == current_user.id, AutoLot.saved == True)  # noqa: E712
        .order_by(AutoLot.created_at.desc())
        .all()
    )
    return [_lot_to_dict(lot) for lot in rows]


@router.delete("/lots/saved/{lot_id}")
def delete_saved_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lot = (
        db.query(AutoLot)
        .filter(AutoLot.id == lot_id, AutoLot.user_id == current_user.id)
        .first()
    )
    if not lot:
        raise HTTPException(status_code=404, detail="Lotul salvat nu a fost gasit.")
    db.delete(lot)
    db.commit()
    return {"message": "Lotul a fost sters din salvate."}


# ──────────────────────────────────────────────────────────────────────────────
# Anunturi auto (auto_listing) + extractie AI din descriere
# ──────────────────────────────────────────────────────────────────────────────


class ExtractDescriptionInput(BaseModel):
    description: str
    km: Optional[int] = None
    year: Optional[int] = None


@router.post("/listings/extract-description")
async def extract_description(
    data: ExtractDescriptionInput,
    current_user: User = Depends(get_current_user),
):
    """Extrage informatii structurate (ITP, curea, istoric service etc.) din descriere."""
    existing = {}
    if data.km is not None:
        existing["km"] = data.km
    if data.year is not None:
        existing["year"] = data.year
    result = await extract_auto_features_from_description(data.description, existing)
    return {"extracted": result}


@router.get("/listings/search")
async def search_listings(
    q: str = Query("", description="Cuvant cheie / marca"),
    platforms: str = Query("autovit,olx_auto", description="Lista platforme separate prin virgula"),
    filters: Optional[str] = Query(None, description="JSON encodat cu filtre"),
    current_user: User = Depends(get_current_user),
):
    """Cauta anunturi auto pe platformele selectate, in paralel (asyncio.gather)."""
    f = _parse_filters(filters)
    make = f.get("make", "") or q
    builders = {
        "olx_auto": lambda: search_olx_auto(q, f),
        "autovit": lambda: search_autovit(make, f.get("model", ""), f),
        "mobile_de": lambda: search_mobile_de(f.get("make_id", "") or make, f),
        "autoscout24": lambda: search_autoscout24(make, f),
        "facebook_auto": lambda: search_facebook_auto(q, f),
        "kleinanzeigen_auto": lambda: search_kleinanzeigen_auto(q, make, f),
    }
    selected = [p.strip().lower() for p in (platforms or "").split(",") if p.strip() in builders]
    if not selected:
        return {"results": [], "by_platform": {}, "count": 0}

    settled = await asyncio.gather(*[builders[p]() for p in selected], return_exceptions=True)
    merged, by_platform = [], {}
    for platform, res in zip(selected, settled):
        if isinstance(res, Exception):
            print(f"[auto/listings/search] {platform} error: {res}")
            by_platform[platform] = 0
            continue
        merged.extend(res)
        by_platform[platform] = len(res)

    return {"results": merged, "by_platform": by_platform, "count": len(merged)}


class ListingSave(BaseModel):
    platform: str
    external_id: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    km: Optional[int] = None
    engine_type: Optional[str] = None
    gearbox: Optional[str] = None
    body_type: Optional[str] = None
    color: Optional[str] = None
    pret: Optional[float] = None
    moneda: str = "EUR"
    locatie: Optional[str] = None
    titlu: Optional[str] = None
    descriere: Optional[str] = None
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    ai_extract: Optional[dict] = None


def _listing_to_dict(li: AutoListing) -> dict:
    return {
        "id": li.id,
        "platform": li.platform,
        "external_id": li.external_id,
        "make": li.make,
        "model": li.model,
        "year": li.year,
        "km": li.km,
        "engine_type": li.engine_type,
        "gearbox": li.gearbox,
        "body_type": li.body_type,
        "color": li.color,
        "pret": float(li.pret) if li.pret is not None else None,
        "moneda": li.moneda,
        "locatie": li.locatie,
        "titlu": li.titlu,
        "descriere": li.descriere,
        "source_url": li.source_url,
        "thumbnail_url": li.thumbnail_url,
        "ai_extract": li.ai_extract,
        "saved": bool(li.saved),
        "created_at": li.created_at.isoformat() if li.created_at else None,
    }


@router.post("/listings/save")
def save_listing(
    data: ListingSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Salveaza un anunt auto in tabela auto_listing cu saved=True."""
    if not (data.platform or "").strip():
        raise HTTPException(status_code=400, detail="Platforma este obligatorie.")

    existing = None
    if data.external_id:
        existing = (
            db.query(AutoListing)
            .filter(
                AutoListing.user_id == current_user.id,
                AutoListing.platform == data.platform,
                AutoListing.external_id == data.external_id,
            )
            .first()
        )
    elif data.source_url:
        existing = (
            db.query(AutoListing)
            .filter(
                AutoListing.user_id == current_user.id,
                AutoListing.platform == data.platform,
                AutoListing.source_url == data.source_url,
            )
            .first()
        )
    if existing:
        existing.saved = True
        db.commit()
        db.refresh(existing)
        return _listing_to_dict(existing)

    li = AutoListing(
        user_id=current_user.id,
        platform=data.platform,
        external_id=data.external_id,
        make=data.make,
        model=data.model,
        year=data.year,
        km=data.km,
        engine_type=data.engine_type,
        gearbox=data.gearbox,
        body_type=data.body_type,
        color=data.color,
        pret=data.pret,
        moneda=data.moneda or "EUR",
        locatie=data.locatie,
        titlu=data.titlu,
        descriere=data.descriere,
        source_url=data.source_url,
        thumbnail_url=data.thumbnail_url,
        ai_extract=data.ai_extract,
        saved=True,
    )
    db.add(li)
    db.commit()
    db.refresh(li)
    return _listing_to_dict(li)


@router.get("/listings/saved")
def list_saved_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(AutoListing)
        .filter(AutoListing.user_id == current_user.id, AutoListing.saved == True)  # noqa: E712
        .order_by(AutoListing.created_at.desc())
        .all()
    )
    return [_listing_to_dict(li) for li in rows]


@router.delete("/listings/saved/{listing_id}")
def delete_saved_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    li = (
        db.query(AutoListing)
        .filter(AutoListing.id == listing_id, AutoListing.user_id == current_user.id)
        .first()
    )
    if not li:
        raise HTTPException(status_code=404, detail="Anuntul salvat nu a fost gasit.")
    db.delete(li)
    db.commit()
    return {"message": "Anuntul a fost sters din salvate."}
