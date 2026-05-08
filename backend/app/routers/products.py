from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import SessionLocal, get_db
from app.models.product import Product
from app.models.price_history import PriceHistory
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductSaveResponse,
    ProductDetailResponse,
)
from app.utils.auth import get_current_user
from app.models.user import User
from app.services.scraper_service import fetch_ean_from_url

router = APIRouter(prefix="/api/products", tags=["Products"])


def _user_products_query(db: Session, user_id: int):
    return db.query(Product).filter(Product.user_id == user_id)


@router.get("/", response_model=List[ProductResponse])
def get_products(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    source: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List products owned by the current user."""
    query = _user_products_query(db, current_user.id)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if category:
        query = query.filter(Product.category == category)
    if min_price is not None:
        query = query.filter(Product.current_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.current_price <= max_price)
    if source:
        query = query.filter(Product.source == source)

    return query.offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    price_history = (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.recorded_at.desc())
        .all()
    )

    prices = [ph.price for ph in price_history]
    return {
        "product": product,
        "price_history": price_history,
        "lowest_price": min(prices) if prices else None,
        "highest_price": max(prices) if prices else None,
        "average_price": round(sum(prices) / len(prices), 2) if prices else None,
    }


def _normalize_name(name: str) -> str:
    return " ".join((name or "").lower().split())


def _build_save_response(product: Product, is_new: bool, previous_price: Optional[float]) -> dict:
    price_changed = (
        (not is_new)
        and previous_price is not None
        and product.current_price is not None
        and round(float(previous_price), 2) != round(float(product.current_price), 2)
    )
    return {
        "id": product.id,
        "name": product.name,
        "ean": product.ean,
        "sku": product.sku,
        "category": product.category,
        "image_url": product.image_url,
        "description": product.description,
        "source": product.source,
        "source_url": product.source_url,
        "current_price": product.current_price,
        "currency": product.currency,
        "created_at": product.created_at,
        "is_new": is_new,
        "previous_price": previous_price,
        "price_changed": price_changed,
    }


def _backfill_ean(product_id: int, source_url: str) -> None:
    """Fetch EAN from the product detail page in the background and persist it."""
    if not source_url:
        return
    db: Session = SessionLocal()
    try:
        ean = fetch_ean_from_url(source_url)
        if not ean:
            return
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and not product.ean:
            product.ean = ean
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"[EAN backfill] Eroare pentru product_id={product_id}: {e}")
    finally:
        db.close()


@router.post("/", response_model=ProductSaveResponse)
def create_product(
    product_data: ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a product for the current user.

    Deduplication is scoped per user:
    1. EAN match within user's products -> update price + price_history.
    2. SKU match within user's products -> update price + price_history.
    3. Same (name, source) within user's products -> update price + price_history.
    4. Otherwise -> create a new product row owned by this user.

    If no EAN is supplied, the EAN is fetched from the source page
    asynchronously so the POST request returns immediately.
    """

    def _update_existing(existing: Product) -> dict:
        old_price = existing.current_price
        if product_data.current_price is not None:
            existing.current_price = product_data.current_price
            existing.currency = product_data.currency or existing.currency
            if product_data.source_url:
                existing.source_url = product_data.source_url
            if product_data.image_url:
                existing.image_url = product_data.image_url
            if product_data.ean and not existing.ean:
                existing.ean = product_data.ean
            if product_data.sku and not existing.sku:
                existing.sku = product_data.sku

            db.add(PriceHistory(
                product_id=existing.id,
                price=product_data.current_price,
                currency=product_data.currency or "EUR",
                source=product_data.source or existing.source,
            ))
        db.commit()
        db.refresh(existing)
        return _build_save_response(existing, is_new=False, previous_price=old_price)

    user_products = _user_products_query(db, current_user.id)

    if product_data.ean:
        existing_ean = user_products.filter(Product.ean == product_data.ean).first()
        if existing_ean:
            return _update_existing(existing_ean)

    if product_data.sku:
        existing_sku = user_products.filter(Product.sku == product_data.sku).first()
        if existing_sku:
            return _update_existing(existing_sku)

    if product_data.source:
        normalized = _normalize_name(product_data.name)
        same_site_match = (
            user_products
            .filter(func.lower(Product.name) == normalized)
            .filter(Product.source == product_data.source)
            .first()
        )
        if same_site_match is not None:
            return _update_existing(same_site_match)

    new_product = Product(**product_data.model_dump(), user_id=current_user.id)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    if new_product.current_price:
        db.add(PriceHistory(
            product_id=new_product.id,
            price=new_product.current_price,
            currency=new_product.currency,
            source=new_product.source,
        ))
        db.commit()

    if not new_product.ean and new_product.source_url:
        background_tasks.add_task(_backfill_ean, new_product.id, new_product.source_url)

    return _build_save_response(new_product, is_new=True, previous_price=None)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update editable fields on a user's own product. Only sent fields change."""
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        new_name = (changes["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Numele produsului nu poate fi gol")
        changes["name"] = new_name

    price_changed = (
        "current_price" in changes
        and changes["current_price"] is not None
        and product.current_price != changes["current_price"]
    )

    for key, value in changes.items():
        setattr(product, key, value)

    if price_changed:
        db.add(PriceHistory(
            product_id=product.id,
            price=product.current_price,
            currency=product.currency or "EUR",
            source=product.source,
        ))

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        _user_products_query(db, current_user.id)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produsul nu a fost gasit")

    db.delete(product)
    db.commit()
    return {"message": "Produsul a fost sters din baza de date"}
