# FlipRadar — ITEM 16: setari per-utilizator (pragul pentru alertele Flash Deal).
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.radar_settings import RadarSettings
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/users", tags=["User Settings"])


class UserSettings(BaseModel):
    flash_deal_threshold: Optional[float] = None
    ai_features_config: Optional[dict] = None


@router.get("/settings")
def get_user_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {
        "flash_deal_threshold": float(current_user.flash_deal_threshold or 0.15),
        "ai_features_config": current_user.ai_features_config or {},
    }


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

    if payload.ai_features_config is not None:
        current_user.ai_features_config = payload.ai_features_config

    db.commit()
    db.refresh(current_user)
    return {
        "flash_deal_threshold": float(current_user.flash_deal_threshold or 0.15),
        "ai_features_config": current_user.ai_features_config or {},
    }


# MODIFICARE 13 — statusul sesiunilor pentru platformele care necesita autentificare.
@router.get("/settings/session-status")
def get_session_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returnează statusul sesiunilor pentru platformele care necesită autentificare."""
    from pathlib import Path

    settings = db.query(RadarSettings).filter(RadarSettings.user_id == current_user.id).first()

    # Facebook: folosim calea REALĂ a sesiunii (RadarSettings.facebook_session_path),
    # aceeași sursă ca search_facebook / re_authenticate — nu o constantă hardcodată
    # (fostul STORAGE_STATE_PATH pointa spre un fișier care nu era cel real folosit).
    fb_path_str = settings.facebook_session_path if settings else None
    fb_path = Path(fb_path_str) if fb_path_str else None
    fb_exists = bool(fb_path and fb_path.exists())

    return {
        # Vinted nu mai necesită cookie — libraria vinted-scraper gestionează DataDome automat.
        "vinted":   {"status": "ok", "detail": "fără autentificare (librărie vinted-scraper)"},
        "okazii":   {"status": "ok" if (settings and settings.okazii_cookie) else "missing"},
        "lajumate": {"status": "ok" if (settings and settings.lajumate_cookie) else "missing"},
        "facebook": {
            "status": "ok" if fb_exists else "missing",
            "storage_state_exists": fb_exists,
            "age_hours": round((time.time() - fb_path.stat().st_mtime) / 3600, 1)
                         if fb_exists else None,
        },
    }
