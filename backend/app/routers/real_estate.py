"""Router /api/real-estate — cautare imobiliare (OLX/Storia/Imobiliare.ro/Facebook),
anunturi salvate si alerte keyword.
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.real_estate_listing import RealEstateListing
from app.utils.auth import get_current_user
from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
from app.scrapers.real_estate.storia_scraper import search_storia
from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro

router = APIRouter(prefix="/api/real-estate", tags=["Real Estate"])


# ──────────────────────────────────────────────────────────────────────────────
# Cautare
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/search")
@limiter.limit("5/minute")
async def search(
    request: Request,
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
        # facebook SCOS (IM-5): search_facebook_real_estate e SINCRON (sync_playwright) — pasat
        # in asyncio.gather ar crapa, iar builder-ul il apela pozitional (filters ajungea drept
        # query). FB ramane disponibil prin monitorizarea cu keyword. platforms=facebook e acum
        # ignorat de filtrul "p.strip() in builders" => selected gol => raspuns gol, nu 500.
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
    """DEPRECAT (IM-5): UI-ul salveaza acum in tabelul MONITOR prin
    /api/real-estate-monitor/listings/save-manual. Acest endpoint + tabelul vechi
    (real_estate_listing) raman doar pentru datele istorice — de eliminat la un cleanup viitor."""
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
    """DEPRECAT (IM-5): salvarile din UI merg acum in tabelul MONITOR (vezi
    /api/real-estate-monitor). Ramane doar pentru datele istorice din tabelul vechi."""
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
    """DEPRECAT (IM-5): salvarile din UI merg acum in tabelul MONITOR (vezi
    /api/real-estate-monitor). Ramane doar pentru datele istorice din tabelul vechi."""
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
