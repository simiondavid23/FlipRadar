import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tracked_product import TrackedProduct
from app.models.alert import Alert
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
    """Returneaza produsele urmarite de user, cu statusul de monitorizare si
    pragul de alerta (citit din modelul Alert, nu din randul de tracking)."""

    tracked_rows = (
        db.query(TrackedProduct)
        .filter(TrackedProduct.user_id == current_user.id)
        .all()
    )
    pids = [t.product_id for t in tracked_rows]

    # Produsele intr-un singur query (fara N+1).
    products_by_id = {}
    if pids:
        for p in db.query(Product).filter(Product.id.in_(pids)).all():
            products_by_id[p.id] = p

    # BH-02 — istoricul de preț pentru sparkline, într-un SINGUR query (evită N+1).
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

    # Pragul de alerta, batch: ultima alerta price_drop activa per produs.
    thresholds_by_pid: dict = {}
    if pids:
        _alert_rows = (
            db.query(Alert)
            .filter(
                Alert.user_id == current_user.id,
                Alert.product_id.in_(pids),
                Alert.alert_type == "price_drop",
                Alert.is_active == True,
                Alert.is_triggered == False,
            )
            .order_by(Alert.product_id, Alert.id)
            .all()
        )
        for _a in _alert_rows:
            # Ordonat crescator dupa id -> ultima alerta per produs castiga.
            thresholds_by_pid[_a.product_id] = float(_a.target_price)

    result = []
    for t in tracked_rows:
        p = products_by_id.get(t.product_id)
        if not p:
            continue
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
            "saved_at": t.added_at.isoformat() if t.added_at else None,
            "monitoring_active": t.monitoring_active,
            "alert_threshold": thresholds_by_pid.get(p.id),
            "price_history": [
                {"price": float(h.price),
                 "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None}
                for h in history_by_pid.get(p.id, [])[-7:]
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
    """Activeaza sau dezactiveaza monitorizarea pentru un produs.
    Pragul de alerta se persista in modelul Alert (price_drop), singurul citit
    de alert_checker — randul de tracking nu tine praguri."""
    activate = bool(body.get("active", False))
    alert_threshold = body.get("alert_threshold")

    # Ownership INTAI: un produs al altui user (sau inexistent) nu e atins.
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

    tracked = (
        db.query(TrackedProduct)
        .filter(
            TrackedProduct.user_id == current_user.id,
            TrackedProduct.product_id == product_id,
        )
        .first()
    )
    if not tracked:
        tracked = TrackedProduct(user_id=current_user.id, product_id=product_id)
        db.add(tracked)
    tracked.monitoring_active = activate

    if not activate:
        # C-18: toggle-ul OFF stinge si alertele price_drop ale produsului —
        # simetric cu re-arm-ul de la activare. Alert.is_active ramane unica
        # sursa de adevar pentru alert_checker (care NU filtreaza pe
        # monitoring_active), deci fara pasul asta alerta continua sa traga
        # dupa "oprirea monitorizarii", iar GET re-afisa pragul "sters".
        # price_rise si alertele altor produse nu sunt atinse; reactivarea
        # ramane posibila din pagina Alerte Pret sau prin toggle ON cu prag.
        db.query(Alert).filter(
            Alert.user_id == current_user.id,
            Alert.product_id == product_id,
            Alert.alert_type == "price_drop",
            Alert.is_active == True,
        ).update({"is_active": False}, synchronize_session=False)

    if activate and alert_threshold is not None:
        try:
            threshold = float(alert_threshold)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pragul de alerta trebuie sa fie un numar pozitiv",
            )
        if not math.isfinite(threshold) or threshold <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pragul de alerta trebuie sa fie un numar pozitiv",
            )

        existing_alert = (
            db.query(Alert)
            .filter(
                Alert.user_id == current_user.id,
                Alert.product_id == product_id,
                Alert.alert_type == "price_drop",
            )
            .order_by(Alert.id.desc())
            .first()
        )
        if existing_alert:
            existing_alert.target_price = threshold
            existing_alert.currency = product.currency or existing_alert.currency or "EUR"
            existing_alert.is_active = True
            existing_alert.is_triggered = False
            existing_alert.triggered_at = None
        else:
            db.add(Alert(
                user_id=current_user.id,
                product_id=product_id,
                target_price=threshold,
                currency=product.currency or "EUR",
                alert_type="price_drop",
                is_active=True,
                is_triggered=False,
                triggered_at=None,
            ))

    db.commit()
    return {"status": "ok", "monitoring_active": activate}


@router.delete("/{product_id}")
def remove_from_tracked(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina produsul din Produse Urmarite. Alertele raman (comportament vechi)."""
    db.query(TrackedProduct).filter(
        TrackedProduct.user_id == current_user.id,
        TrackedProduct.product_id == product_id,
    ).delete()
    db.commit()
    return {"status": "ok"}
