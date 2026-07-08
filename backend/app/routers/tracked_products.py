from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.favorite import FavoriteItem
from app.models.watchlist import WatchlistItem
from app.models.product import Product
from app.models.price_history import PriceHistory
from app.models.user import User
from app.utils.auth import get_current_user

# Prefixul /api/tracked-products este aplicat la include_router in main.py.
router = APIRouter(tags=["Tracked Products"])


@router.get("/")
def get_tracked_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returneaza lista unificata: favorite + watchlist, cu statusul
    de monitorizare per produs. Deduplicare dupa product_id."""

    # Preia favoritele (doar cele reale, nu produsele din blacklist)
    favorites = db.query(FavoriteItem).filter(
        FavoriteItem.user_id == current_user.id,
        FavoriteItem.is_blacklisted == False,
    ).all()

    # Preia watchlist-ul
    watchlist = db.query(WatchlistItem).filter(
        WatchlistItem.user_id == current_user.id
    ).all()

    # Combina si deduplica
    tracked = {}

    for fav in favorites:
        product = db.query(Product).filter(Product.id == fav.product_id).first()
        if product:
            tracked[product.id] = {
                "product": product,
                "saved_at": fav.added_at,
                "monitoring_active": False,
                "alert_threshold": None,
                "source": "favorite",
            }

    for item in watchlist:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            if product.id in tracked:
                tracked[product.id]["monitoring_active"] = True
                tracked[product.id]["alert_threshold"] = getattr(item, "alert_price", None)
                tracked[product.id]["source"] = "both"
            else:
                tracked[product.id] = {
                    "product": product,
                    "saved_at": item.added_at,
                    "monitoring_active": True,
                    "alert_threshold": getattr(item, "alert_price", None),
                    "source": "watchlist",
                }

    # BH-02 — istoricul de preț pentru sparkline, într-un SINGUR query (evită N+1).
    pids = list(tracked.keys())
    history_by_pid: dict = {}
    if pids:
        _hist_rows = (
            db.query(PriceHistory)
            .filter(PriceHistory.product_id.in_(pids))
            .order_by(PriceHistory.product_id, PriceHistory.recorded_at.asc())
            .all()
        )
        for _h in _hist_rows:
            history_by_pid.setdefault(_h.product_id, []).append(_h)

    result = []
    for pid, data in tracked.items():
        p = data["product"]
        result.append({
            "id": p.id,
            "name": p.name,
            "current_price": float(p.current_price) if p.current_price else None,
            "original_price": float(p.original_price) if p.original_price else None,
            "currency": p.currency,
            "source": p.source,
            "source_url": p.source_url,
            "image_url": getattr(p, "image_url", None),
            "category": p.category,
            "subcategory": getattr(p, "subcategory", None),
            "brand": getattr(p, "brand", None),
            "saved_at": data["saved_at"].isoformat() if data["saved_at"] else None,
            "monitoring_active": data["monitoring_active"],
            "alert_threshold": float(data["alert_threshold"])
                if data["alert_threshold"] else None,
            "tracked_source": data["source"],
            "price_history": [
                {"price": float(h.price),
                 "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None}
                for h in history_by_pid.get(pid, [])[-7:]
            ],
        })

    return sorted(result, key=lambda x: x["saved_at"] or "", reverse=True)


@router.patch("/{product_id}/monitoring")
def toggle_monitoring(
    product_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activeaza sau dezactiveaza monitorizarea pentru un produs."""
    activate = body.get("active", False)
    alert_threshold = body.get("alert_threshold")

    existing = db.query(WatchlistItem).filter(
        WatchlistItem.user_id == current_user.id,
        WatchlistItem.product_id == product_id,
    ).first()

    if activate and not existing:
        new_item = WatchlistItem(
            user_id=current_user.id,
            product_id=product_id,
        )
        if alert_threshold:
            setattr(new_item, "alert_price", alert_threshold)
        db.add(new_item)
    elif not activate and existing:
        db.delete(existing)
    elif activate and existing and alert_threshold is not None:
        setattr(existing, "alert_price", alert_threshold)

    db.commit()
    return {"status": "ok", "monitoring_active": activate}


@router.delete("/{product_id}")
def remove_from_tracked(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina produsul din favorite SI din watchlist."""
    db.query(FavoriteItem).filter(
        FavoriteItem.user_id == current_user.id,
        FavoriteItem.product_id == product_id,
    ).delete()
    db.query(WatchlistItem).filter(
        WatchlistItem.user_id == current_user.id,
        WatchlistItem.product_id == product_id,
    ).delete()
    db.commit()
    return {"status": "ok"}
