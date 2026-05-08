from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app.models.favorite import FavoriteItem
from app.models.product import Product
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoriteResponse
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/favorites", tags=["Favorites & Blacklist"])


@router.get("/", response_model=List[FavoriteResponse])
def get_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all favorite products (not blacklisted)."""
    items = (
        db.query(FavoriteItem)
        .options(joinedload(FavoriteItem.product))
        .filter(FavoriteItem.user_id == current_user.id, FavoriteItem.is_blacklisted == False)
        .order_by(FavoriteItem.added_at.desc())
        .all()
    )
    return items


@router.get("/blacklist", response_model=List[FavoriteResponse])
def get_blacklist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all blacklisted products."""
    items = (
        db.query(FavoriteItem)
        .options(joinedload(FavoriteItem.product))
        .filter(FavoriteItem.user_id == current_user.id, FavoriteItem.is_blacklisted == True)
        .order_by(FavoriteItem.added_at.desc())
        .all()
    )
    return items


@router.post("/", response_model=FavoriteResponse)
def add_favorite(
    data: FavoriteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a product to favorites or blacklist."""
    product = (
        db.query(Product)
        .filter(Product.id == data.product_id, Product.user_id == current_user.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    existing = (
        db.query(FavoriteItem)
        .filter(FavoriteItem.user_id == current_user.id, FavoriteItem.product_id == data.product_id)
        .first()
    )
    if existing:
        existing.is_blacklisted = data.is_blacklisted
        existing.notes = data.notes
        db.commit()
        db.refresh(existing, ["product"])
        return existing

    item = FavoriteItem(
        user_id=current_user.id,
        product_id=data.product_id,
        is_blacklisted=data.is_blacklisted,
        notes=data.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item, ["product"])
    return item


@router.delete("/{item_id}")
def remove_favorite(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove from favorites or blacklist."""
    item = (
        db.query(FavoriteItem)
        .filter(FavoriteItem.id == item_id, FavoriteItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Elementul nu a fost gasit")

    db.delete(item)
    db.commit()
    return {"message": "Eliminat cu succes"}
