"""TEMPORAR — compatibilitate frontend vechi, se elimina integral in CAT-3b.

Frontend-ul inca apeleaza POST /api/watchlist/ si POST /api/favorites/ (butoanele
Eye/Heart/Ban din catalog). Rutele vechi si modelele lor au disparut in CAT-3a;
aliasurile de mai jos le mapeaza peste TrackedProduct ca UI-ul sa nu pice intre pasi.
Blacklist-ul a fost eliminat definitiv (D1) — aliasul raspunde 410, nu simuleaza.

Devianta asumata: verificarea veche de duplicat dupa nume+sursa NU se replica
(logica moare in CAT-3b; aliasul traieste zile, nu luni).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.tracked_product import TrackedProduct
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(tags=["Legacy Compat (temporar)"])


class LegacyWatchlistCreate(BaseModel):
    product_id: int


class LegacyFavoriteCreate(BaseModel):
    product_id: int
    is_blacklisted: bool = False
    notes: Optional[str] = None


def _owned_product_or_404(db: Session, product_id: int, current_user: User) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == current_user.id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produsul nu a fost gasit",
        )
    return product


def _tracked_row(db: Session, product_id: int, current_user: User) -> Optional[TrackedProduct]:
    return (
        db.query(TrackedProduct)
        .filter(
            TrackedProduct.user_id == current_user.id,
            TrackedProduct.product_id == product_id,
        )
        .first()
    )


@router.post("/api/watchlist/")
def legacy_add_to_watchlist(
    data: LegacyWatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Alias vechi: adauga produsul in Produse Urmarite cu monitorizare activa."""
    _owned_product_or_404(db, data.product_id, current_user)

    tracked = _tracked_row(db, data.product_id, current_user)
    if tracked and tracked.monitoring_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produsul este deja in Produse Urmarite",
        )

    if not tracked:
        tracked = TrackedProduct(user_id=current_user.id, product_id=data.product_id)
        db.add(tracked)
    tracked.monitoring_active = True
    db.commit()
    return {"status": "ok"}


@router.post("/api/favorites/")
def legacy_add_favorite(
    data: LegacyFavoriteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Alias vechi: salveaza produsul in Produse Urmarite, fara monitorizare.
    Blacklist-ul nu mai exista (D1) -> 410, nu no-op tacut."""
    if data.is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Functia blacklist a fost eliminata.",
        )

    _owned_product_or_404(db, data.product_id, current_user)

    tracked = _tracked_row(db, data.product_id, current_user)
    if not tracked:
        # Produs nou in lista: salvat, dar fara monitorizare activa.
        db.add(TrackedProduct(
            user_id=current_user.id,
            product_id=data.product_id,
            monitoring_active=False,
        ))
        db.commit()
    return {"status": "ok"}
