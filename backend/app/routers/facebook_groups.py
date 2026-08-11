"""Router /api/facebook-groups — monitorizare grupuri Facebook imobiliare.

Toate endpoint-urile cer autentificare si filtreaza pe user_id-ul curent
(un utilizator nu poate vedea/edita configurarile sau postarile altuia).
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.facebook_group_config import FacebookGroupConfig
from app.models.facebook_group_post import FacebookGroupPost
from app.utils.auth import get_current_user
from app.utils.cookie_crypto import encrypt_cookies, normalize_cookies
from app.services.facebook_group_service import run_single_config_check

router = APIRouter(prefix="/api/facebook-groups", tags=["Facebook Groups"])

_VALID_INTERVALS = (1, 2, 4)


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────


class FacebookGroupCreate(BaseModel):
    group_name: str
    group_url: str
    keywords: list[str] = []
    negative_keywords: list[str] = []
    check_interval_hours: int = 2

    @field_validator("check_interval_hours")
    @classmethod
    def _valid_interval(cls, v: int) -> int:
        if v not in _VALID_INTERVALS:
            raise ValueError("Intervalul trebuie sa fie 1, 2 sau 4 ore.")
        return v


class FacebookGroupUpdate(BaseModel):
    group_name: Optional[str] = None
    keywords: Optional[list[str]] = None
    negative_keywords: Optional[list[str]] = None
    check_interval_hours: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("check_interval_hours")
    @classmethod
    def _valid_interval(cls, v):
        if v is not None and v not in _VALID_INTERVALS:
            raise ValueError("Intervalul trebuie sa fie 1, 2 sau 4 ore.")
        return v


class CookiesPayload(BaseModel):
    cookies_json: str


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _config_to_dict(db: Session, c: FacebookGroupConfig) -> dict:
    # FBG-2 (m1): postarile brute se consuma DOAR prin feed-ul Imobiliare;
    # numaratorile posts_count/unread_count nu erau citite de frontend.
    return {
        "id": c.id,
        "group_name": c.group_name,
        "group_url": c.group_url,
        "keywords": c.keywords or [],
        "negative_keywords": c.negative_keywords or [],
        "check_interval_hours": c.check_interval_hours,
        "is_active": bool(c.is_active),
        "has_cookies": c.cookies_encrypted is not None,
        "cookies_saved_at": c.cookies_saved_at.isoformat() if c.cookies_saved_at else None,
        "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None,
        "last_run_status": c.last_run_status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _get_owned_config(db: Session, config_id: int, user: User) -> FacebookGroupConfig:
    config = db.query(FacebookGroupConfig).filter(
        FacebookGroupConfig.id == config_id,
        FacebookGroupConfig.user_id == user.id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configurarea nu a fost gasita.")
    return config


# ──────────────────────────────────────────────────────────────────────────────
# Configs CRUD
# ──────────────────────────────────────────────────────────────────────────────


@router.get("")
def list_configs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(FacebookGroupConfig)
        .filter(FacebookGroupConfig.user_id == current_user.id)
        .order_by(FacebookGroupConfig.created_at.desc())
        .all()
    )
    return [_config_to_dict(db, c) for c in rows]


@router.post("")
def create_config(
    data: FacebookGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not data.group_name.strip() or not data.group_url.strip():
        raise HTTPException(status_code=400, detail="Numele si URL-ul grupului sunt obligatorii.")
    config = FacebookGroupConfig(
        user_id=current_user.id,
        group_name=data.group_name.strip(),
        group_url=data.group_url.strip(),
        keywords=data.keywords or [],
        negative_keywords=data.negative_keywords or [],
        check_interval_hours=data.check_interval_hours,
        is_active=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_to_dict(db, config)


@router.put("/{config_id}")
def update_config(
    config_id: int,
    data: FacebookGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)
    if data.group_name is not None:
        config.group_name = data.group_name.strip()
    if data.keywords is not None:
        config.keywords = data.keywords
    if data.negative_keywords is not None:
        config.negative_keywords = data.negative_keywords
    if data.check_interval_hours is not None:
        config.check_interval_hours = data.check_interval_hours
    if data.is_active is not None:
        config.is_active = bool(data.is_active)
    db.commit()
    db.refresh(config)
    return _config_to_dict(db, config)


@router.delete("/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)
    db.query(FacebookGroupPost).filter(
        FacebookGroupPost.config_id == config_id,
        FacebookGroupPost.user_id == current_user.id,
    ).delete()
    db.delete(config)
    db.commit()
    return {"message": "Grupul si postarile asociate au fost sterse."}


# ──────────────────────────────────────────────────────────────────────────────
# Cookies
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/{config_id}/cookies")
def save_cookies(
    config_id: int,
    payload: CookiesPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)
    try:
        cookies = json.loads(payload.cookies_json)
    except Exception:
        raise HTTPException(status_code=400, detail="JSON-ul cu cookies este invalid.")
    if not isinstance(cookies, list) or not cookies:
        raise HTTPException(status_code=400, detail="Cookies-urile trebuie sa fie un array JSON ne-gol.")

    # FBG-2 (C1) — exporturile din extensii (Cookie-Editor etc.) au sameSite cu
    # litere mici + campuri extra pe care Playwright le respinge cu exceptie
    # INAINTE de a incarca pagina. Normalizam LA SALVARE, ca tot ce sta criptat
    # in DB sa fie deja in formatul acceptat.
    cookies = normalize_cookies(cookies)
    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="Niciun cookie valid in export (lipsesc name/value). "
                   "Exporta cookie-urile facebook.com cu Cookie-Editor (format JSON).")

    config.cookies_encrypted = encrypt_cookies(cookies)
    config.cookies_saved_at = datetime.utcnow()
    config.last_run_status = None
    db.commit()
    return {"status": "ok", "saved_at": config.cookies_saved_at.isoformat()}


@router.delete("/{config_id}/cookies")
def delete_cookies(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)
    config.cookies_encrypted = None
    config.cookies_saved_at = None
    config.last_run_status = "cookies_sterse"
    db.commit()
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────────────
# FBG-2 (m1) — endpoint-urile de postari brute (/posts/all, /{id}/posts) si
# mecanismul is_read/unread_count au fost STERSE: cod mort din perspectiva UI
# (api.js nu le definea, niciun apelant in frontend; precedentul MKT-CLEAN).
# Postarile brute se consuma exclusiv prin ingestul feed-ului Imobiliare.
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Test-run manual
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/{config_id}/test-run")
async def test_run(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)
    if not config.cookies_encrypted:
        raise HTTPException(status_code=400, detail="Adauga mai intai cookies pentru acest grup.")
    new_posts = await run_single_config_check(config_id, current_user.id)
    return {"new_posts": new_posts}
