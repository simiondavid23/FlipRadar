import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.user import User
from app.models.product import Product
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.models.price_history import PriceHistory
from app.models.inventory import InventoryItem
from app.models.sale import Sale
from app.schemas.ai import ProductAnalysisRequest, ListingGenerationRequest, AIResponse
from app.utils.auth import get_current_user, require_feature

# Feature gate: every AI analysis endpoint requires `can_use_ai`.
_ai_user = require_feature("can_use_ai")
from app.services.ai_service import analyze_product_with_ai, generate_product_listing, generate_ai_report

router = APIRouter(prefix="/api/ai", tags=["AI Analysis"])


@router.post("/analyze-product", response_model=AIResponse)
async def analyze_product(
    request: ProductAnalysisRequest,
    current_user: User = Depends(_ai_user),
):
    """Analyze a product for profitability using AI, personalized for the user."""
    result = await analyze_product_with_ai(
        product_name=request.product_name,
        category=request.category,
        price=request.price,
        source=request.source,
        currency=getattr(request, "currency", "EUR") or "EUR",
        user_name=current_user.full_name or current_user.username,
    )
    return AIResponse(result=result, success=True)


@router.post("/generate-listing", response_model=AIResponse)
async def generate_listing(
    request: ListingGenerationRequest,
    current_user: User = Depends(_ai_user),
):
    """Generate an optimized product listing, personalized."""
    result = await generate_product_listing(
        product_name=request.product_name,
        category=request.category,
        features=request.features,
        price=request.price,
        currency=getattr(request, "currency", "EUR") or "EUR",
        user_name=current_user.full_name or current_user.username,
    )
    return AIResponse(result=result, success=True)


@router.get("/report")
async def get_ai_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(_ai_user),
):
    """Generate an AI-powered activity report tailored to the current user."""

    total_products = db.query(func.count(Product.id)).scalar()

    watchlist_count = (
        db.query(func.count(WatchlistItem.id))
        .filter(WatchlistItem.user_id == current_user.id)
        .scalar()
    )

    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == current_user.id, Alert.is_active == True)
        .scalar()
    )

    triggered_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == current_user.id, Alert.is_triggered == True)
        .scalar()
    )

    total_price_records = db.query(func.count(PriceHistory.id)).scalar()

    inventory_items = (
        db.query(InventoryItem)
        .filter(InventoryItem.user_id == current_user.id)
        .all()
    )

    sales = (
        db.query(Sale)
        .filter(Sale.user_id == current_user.id)
        .order_by(Sale.sold_at.desc())
        .limit(10)
        .all()
    )

    watchlist_items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id)
        .all()
    )
    watchlist_products = []
    for item in watchlist_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            watchlist_products.append(
                f"{product.name} ({product.current_price} {product.currency}, sursa: {product.source or 'n/a'})"
            )

    inventory_products = [
        f"{i.name} x{i.quantity} ({i.purchase_price} {i.currency})"
        for i in inventory_items[:10]
    ]
    recent_sales = [
        f"{s.product_name} x{s.quantity} la {s.sale_price} {s.currency}"
        for s in sales
    ]

    user_data = {
        "username": current_user.full_name or current_user.username,
        "email": current_user.email,
        "total_products": total_products,
        "watchlist_count": watchlist_count,
        "active_alerts": active_alerts,
        "triggered_alerts": triggered_alerts,
        "total_price_records": total_price_records,
        "watchlist_products": str(watchlist_products),
        "inventory_count": len(inventory_items),
        "inventory_products": str(inventory_products),
        "sales_count": len(sales),
        "recent_sales": str(recent_sales),
    }

    result = await generate_ai_report(user_data)

    return {"result": result, "success": True, "user_data": user_data}
