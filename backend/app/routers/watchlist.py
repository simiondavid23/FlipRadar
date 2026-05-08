from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List
from app.database import get_db
from app.models.watchlist import WatchlistItem
from app.models.product import Product
from app.models.user import User
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemUpdate, WatchlistItemResponse
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


@router.get("/", response_model=List[WatchlistItemResponse])
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all products in the current user watchlist."""

    items = (
        db.query(WatchlistItem)
        .options(joinedload(WatchlistItem.product))
        .filter(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.added_at.desc())
        .all()
    )
    return items


@router.post("/", response_model=WatchlistItemResponse)
def add_to_watchlist(
    item_data: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a product to the user watchlist.

    Duplicate rules:
    - The exact same product row cannot be added twice.
    - A product with the same *name* already in watchlist is also a duplicate,
      *unless* the two products come from different source sites. This lets users
      track the same item across Altex/Sole/Farmaciatei but not add the same listing twice.
    """

    product = (
        db.query(Product)
        .filter(Product.id == item_data.product_id, Product.user_id == current_user.id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produsul nu a fost gasit"
        )

    existing_same_id = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.product_id == item_data.product_id,
        )
        .first()
    )
    if existing_same_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produsul este deja in watchlist"
        )

    # Check for a product with the same name already in the watchlist.
    # Allow duplicates only if the sources differ.
    duplicate_by_name = (
        db.query(WatchlistItem)
        .join(Product, WatchlistItem.product_id == Product.id)
        .filter(WatchlistItem.user_id == current_user.id)
        .filter(func.lower(Product.name) == (product.name or "").lower())
        .all()
    )
    for item in duplicate_by_name:
        existing_product = item.product
        if (existing_product.source or "") == (product.source or ""):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ai deja acest produs din aceeasi sursa in watchlist",
            )

    new_item = WatchlistItem(
        user_id=current_user.id,
        product_id=item_data.product_id,
        notes=item_data.notes,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    db.refresh(new_item, ["product"])

    return new_item


@router.put("/{item_id}", response_model=WatchlistItemResponse)
def update_watchlist_item(
    item_id: int,
    item_data: WatchlistItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the notes on a watchlist item."""
    item = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Elementul nu a fost gasit in watchlist",
        )

    if item_data.notes is not None:
        item.notes = item_data.notes
    db.commit()
    db.refresh(item, ["product"])
    return item


@router.delete("/{item_id}")
def remove_from_watchlist(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a product from the user watchlist."""

    item = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Elementul nu a fost gasit in watchlist"
        )

    db.delete(item)
    db.commit()

    return {"message": "Produsul a fost eliminat din watchlist"}
