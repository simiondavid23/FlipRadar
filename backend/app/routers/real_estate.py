"""Router /api/real-estate — cautare imobiliare (OLX/Storia/Imobiliare.ro/Facebook),
anunturi salvate si alerte keyword.
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.real_estate_listing import RealEstateListing
from app.models.real_estate_alert import RealEstateAlert
from app.utils.auth import get_current_user
from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
from app.scrapers.real_estate.storia_scraper import search_storia
from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro
from app.scrapers.real_estate.facebook_real_estate import search_facebook_real_estate

router = APIRouter(prefix="/api/real-estate", tags=["Real Estate"])


# ──────────────────────────────────────────────────────────────────────────────
# Cautare
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/search")
async def search(
    platforms: str = Query("olx,storia", description="Lista platforme separate prin virgula"),
    tip_anunt: str = Query("vanzare"),
    tip_proprietate: str = Query("apartament"),
    camere_min: Optional[int] = Query(None),
    camere_max: Optional[int] = Query(None),
    pret_min: Optional[float] = Query(None),
    pret_max: Optional[float] = Query(None),
    locatie: Optional[str] = Query(None),
    suprafata_min: Optional[float] = Query(None),
    current_user: User = Depends(get_current_user),
):
    filters = {"tip_anunt": tip_anunt, "tip_proprietate": tip_proprietate}
    if camere_min is not None:
        filters["camere_min"] = camere_min
    if pret_min is not None:
        filters["pret_min"] = pret_min
    if pret_max is not None:
        filters["pret_max"] = pret_max
    if locatie:
        filters["locatie"] = locatie
    if suprafata_min is not None:
        filters["suprafata_min"] = suprafata_min

    builders = {
        "olx": lambda: search_olx_real_estate(filters),
        "storia": lambda: search_storia(filters),
        "imobiliare": lambda: search_imobiliare_ro(filters),
        "facebook": lambda: search_facebook_real_estate(filters),
    }
    selected = [p.strip().lower() for p in (platforms or "").split(",") if p.strip() in builders]
    if not selected:
        return {"results": [], "by_platform": {}, "count": 0}

    def _keep(r: dict) -> bool:
        c = r.get("camere")
        if camere_min is not None and c is not None and c < camere_min:
            return False
        if camere_max is not None and c is not None and c > camere_max:
            return False
        return True

    settled = await asyncio.gather(*[builders[p]() for p in selected], return_exceptions=True)
    merged, by_platform = [], {}
    for platform, res in zip(selected, settled):
        if isinstance(res, Exception):
            print(f"[real-estate/search] {platform} error: {res}")
            by_platform[platform] = 0
            continue
        kept = [r for r in res if _keep(r)]
        merged.extend(kept)
        by_platform[platform] = len(kept)

    return {"results": merged, "by_platform": by_platform, "count": len(merged)}


# ──────────────────────────────────────────────────────────────────────────────
# Anunturi salvate
# ──────────────────────────────────────────────────────────────────────────────


class REListingSave(BaseModel):
    platform: str
    external_id: Optional[str] = None
    tip_anunt: Optional[str] = None
    tip_proprietate: Optional[str] = None
    camere: Optional[int] = None
    suprafata_mp: Optional[float] = None
    etaj: Optional[str] = None
    pret: Optional[float] = None
    moneda: str = "EUR"
    locatie_judet: Optional[str] = None
    locatie_oras: Optional[str] = None
    an_constructie: Optional[int] = None
    facilitati: Optional[dict] = None
    titlu: Optional[str] = None
    descriere: Optional[str] = None
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


def _listing_to_dict(li: RealEstateListing) -> dict:
    return {
        "id": li.id,
        "platform": li.platform,
        "external_id": li.external_id,
        "tip_anunt": li.tip_anunt,
        "tip_proprietate": li.tip_proprietate,
        "camere": li.camere,
        "suprafata_mp": float(li.suprafata_mp) if li.suprafata_mp is not None else None,
        "etaj": li.etaj,
        "pret": float(li.pret) if li.pret is not None else None,
        "moneda": li.moneda,
        "locatie_judet": li.locatie_judet,
        "locatie_oras": li.locatie_oras,
        "an_constructie": li.an_constructie,
        "facilitati": li.facilitati,
        "titlu": li.titlu,
        "descriere": li.descriere,
        "source_url": li.source_url,
        "thumbnail_url": li.thumbnail_url,
        "saved": bool(li.saved),
        "created_at": li.created_at.isoformat() if li.created_at else None,
    }


@router.post("/listings/save")
def save_listing(
    data: REListingSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (data.platform or "").strip():
        raise HTTPException(status_code=400, detail="Platforma este obligatorie.")

    existing = None
    if data.source_url:
        existing = (
            db.query(RealEstateListing)
            .filter(
                RealEstateListing.user_id == current_user.id,
                RealEstateListing.source_url == data.source_url,
            )
            .first()
        )
    if existing:
        existing.saved = True
        db.commit()
        db.refresh(existing)
        return _listing_to_dict(existing)

    li = RealEstateListing(
        user_id=current_user.id,
        platform=data.platform,
        external_id=data.external_id,
        tip_anunt=data.tip_anunt,
        tip_proprietate=data.tip_proprietate,
        camere=data.camere,
        suprafata_mp=data.suprafata_mp,
        etaj=data.etaj,
        pret=data.pret,
        moneda=data.moneda or "EUR",
        locatie_judet=data.locatie_judet,
        locatie_oras=data.locatie_oras,
        an_constructie=data.an_constructie,
        facilitati=data.facilitati,
        titlu=data.titlu,
        descriere=data.descriere,
        source_url=data.source_url,
        thumbnail_url=data.thumbnail_url,
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
        db.query(RealEstateListing)
        .filter(RealEstateListing.user_id == current_user.id, RealEstateListing.saved == True)  # noqa: E712
        .order_by(RealEstateListing.created_at.desc())
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
        db.query(RealEstateListing)
        .filter(RealEstateListing.id == listing_id, RealEstateListing.user_id == current_user.id)
        .first()
    )
    if not li:
        raise HTTPException(status_code=404, detail="Anuntul salvat nu a fost gasit.")
    db.delete(li)
    db.commit()
    return {"message": "Anuntul a fost sters din salvate."}


# ──────────────────────────────────────────────────────────────────────────────
# Alerte
# ──────────────────────────────────────────────────────────────────────────────


class REAlertCreate(BaseModel):
    platform: str
    tip_anunt: Optional[str] = None
    tip_proprietate: Optional[str] = None
    filters: Optional[dict] = None
    is_active: bool = True


class REAlertUpdate(BaseModel):
    is_active: Optional[bool] = None
    tip_anunt: Optional[str] = None
    tip_proprietate: Optional[str] = None
    filters: Optional[dict] = None


def _alert_to_dict(a: RealEstateAlert) -> dict:
    return {
        "id": a.id,
        "platform": a.platform,
        "tip_anunt": a.tip_anunt,
        "tip_proprietate": a.tip_proprietate,
        "filters": a.filters or {},
        "is_active": bool(a.is_active),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(RealEstateAlert)
        .filter(RealEstateAlert.user_id == current_user.id)
        .order_by(RealEstateAlert.created_at.desc())
        .all()
    )
    return [_alert_to_dict(a) for a in rows]


@router.post("/alerts")
def create_alert(
    data: REAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (data.platform or "").strip():
        raise HTTPException(status_code=400, detail="Platforma este obligatorie.")
    alert = RealEstateAlert(
        user_id=current_user.id,
        platform=data.platform,
        tip_anunt=data.tip_anunt,
        tip_proprietate=data.tip_proprietate,
        filters=data.filters or {},
        is_active=bool(data.is_active),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.put("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    data: REAlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(RealEstateAlert)
        .filter(RealEstateAlert.id == alert_id, RealEstateAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta nu a fost gasita.")
    if data.is_active is not None:
        alert.is_active = bool(data.is_active)
    if data.tip_anunt is not None:
        alert.tip_anunt = data.tip_anunt
    if data.tip_proprietate is not None:
        alert.tip_proprietate = data.tip_proprietate
    if data.filters is not None:
        alert.filters = data.filters or {}
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.delete("/alerts/{alert_id}")
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(RealEstateAlert)
        .filter(RealEstateAlert.id == alert_id, RealEstateAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta nu a fost gasita.")
    db.delete(alert)
    db.commit()
    return {"message": "Alerta a fost stearsa."}
