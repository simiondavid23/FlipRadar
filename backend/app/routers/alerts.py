from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app.models.alert import Alert
from app.models.product import Product
from app.models.user import User
from app.schemas.alert import AlertCreate, AlertResponse
from app.utils.auth import get_current_user, require_feature

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

# Doar CREAREA de alerte noi este protejată prin feature flag. Listarea / comutarea / ștergerea
# rămân accesibile chiar și după revocare, pentru ca utilizatorul să poată curăța alertele existente.
_alerts_user = require_feature("can_use_alerts")


@router.get("/", response_model=List[AlertResponse])
def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează toate alertele utilizatorului curent."""

    alerts = (
        db.query(Alert)
        .options(joinedload(Alert.product))
        .filter(Alert.user_id == current_user.id)
        .order_by(Alert.created_at.desc())
        .all()
    )
    return alerts


@router.post("/", response_model=AlertResponse)
def create_alert(
    alert_data: AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_alerts_user),
):
    """Creaza o alerta de pret noua pentru un produs."""

    product = (
        db.query(Product)
        .filter(Product.id == alert_data.product_id, Product.user_id == current_user.id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produsul nu a fost gasit"
        )

    new_alert = Alert(
        user_id=current_user.id,
        product_id=alert_data.product_id,
        target_price=alert_data.target_price,
        currency=alert_data.currency,
        alert_type=alert_data.alert_type,
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    db.refresh(new_alert, ["product"])

    return new_alert


@router.put("/{alert_id}/toggle")
def toggle_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activează sau dezactivează o alertă."""

    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nu a fost gasita"
        )

    alert.is_active = not alert.is_active
    db.commit()

    status_text = "activata" if alert.is_active else "dezactivata"
    return {"message": f"Alerta a fost {status_text}"}


@router.delete("/{alert_id}")
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Șterge o alertă."""

    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nu a fost gasita"
        )

    db.delete(alert)
    db.commit()

    return {"message": "Alerta a fost stearsa"}
