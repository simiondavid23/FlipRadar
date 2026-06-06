# FlipRadar — ITEM 16: setari per-utilizator (pragul pentru alertele Flash Deal).
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/users", tags=["User Settings"])


class UserSettings(BaseModel):
    flash_deal_threshold: Optional[float] = None


@router.patch("/settings")
def update_user_settings(
    payload: UserSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizeaza setarile utilizatorului curent. Pragul Flash Deal este o
    fractie intre 0.05 (5%) si 0.50 (50%)."""
    if payload.flash_deal_threshold is not None:
        threshold = float(payload.flash_deal_threshold)
        if not (0.05 <= threshold <= 0.50):
            raise HTTPException(status_code=400, detail="Pragul trebuie sa fie intre 0.05 si 0.50.")
        current_user.flash_deal_threshold = threshold

    db.commit()
    db.refresh(current_user)
    return {
        "flash_deal_threshold": float(current_user.flash_deal_threshold or 0.15),
    }
