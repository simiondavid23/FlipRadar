"""Router /api/facebook-groups — monitorizare grupuri Facebook imobiliare.

Toate endpoint-urile cer autentificare si filtreaza pe user_id-ul curent
(un utilizator nu poate vedea/edita configurarile sau postarile altuia).
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.facebook_group_config import FacebookGroupConfig
from app.models.facebook_group_post import FacebookGroupPost
from app.utils.auth import get_current_user
from app.utils.cookie_crypto import encrypt_cookies
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
    posts_count = db.query(FacebookGroupPost).filter(
        FacebookGroupPost.config_id == c.id,
        FacebookGroupPost.user_id == c.user_id,
    ).count()
    unread_count = db.query(FacebookGroupPost).filter(
        FacebookGroupPost.config_id == c.id,
        FacebookGroupPost.user_id == c.user_id,
        FacebookGroupPost.is_read == False,  # noqa: E712
    ).count()
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
        "posts_count": posts_count,
        "unread_count": unread_count,
    }


def _post_to_dict(p: FacebookGroupPost, group_name: Optional[str] = None) -> dict:
    return {
        "id": p.id,
        "config_id": p.config_id,
        "group_name": group_name,
        "post_id": p.post_id,
        "group_url": p.group_url,
        "text": p.text,
        "pret": float(p.pret) if p.pret is not None else None,
        "moneda": p.moneda,
        "tip_anunt": p.tip_anunt,
        "tip_proprietate": p.tip_proprietate,
        "suprafata_mp": p.suprafata_mp,
        "etaj": p.etaj,
        "zona": p.zona,
        "termen": p.termen,
        "facilitati": p.facilitati,
        "posted_at": p.posted_at.isoformat() if p.posted_at else None,
        "is_read": bool(p.is_read),
        "created_at": p.created_at.isoformat() if p.created_at else None,
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
# Posts
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/posts/all")
def list_all_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(FacebookGroupPost).filter(FacebookGroupPost.user_id == current_user.id)
    total = q.count()
    rows = (
        q.order_by(FacebookGroupPost.posted_at.desc().nullslast(), FacebookGroupPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    names = dict(
        db.query(FacebookGroupConfig.id, FacebookGroupConfig.group_name)
        .filter(FacebookGroupConfig.user_id == current_user.id)
        .all()
    )
    return {
        "posts": [_post_to_dict(p, names.get(p.config_id)) for p in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
    }


@router.get("/{config_id}/posts")
def list_config_posts(
    config_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    tip_anunt: Optional[str] = Query(None),
    pret_max: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_owned_config(db, config_id, current_user)

    q = db.query(FacebookGroupPost).filter(
        FacebookGroupPost.config_id == config_id,
        FacebookGroupPost.user_id == current_user.id,
    )
    if tip_anunt:
        q = q.filter(FacebookGroupPost.tip_anunt == tip_anunt)
    if pret_max is not None:
        q = q.filter(FacebookGroupPost.pret.isnot(None), FacebookGroupPost.pret <= pret_max)

    total = q.count()
    rows = (
        q.order_by(FacebookGroupPost.posted_at.desc().nullslast(), FacebookGroupPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Marcheaza postarile returnate ca citite.
    unread_ids = [p.id for p in rows if not p.is_read]
    if unread_ids:
        db.query(FacebookGroupPost).filter(FacebookGroupPost.id.in_(unread_ids)).update(
            {FacebookGroupPost.is_read: True}, synchronize_session=False
        )
        db.commit()

    return {
        "posts": [_post_to_dict(p, config.group_name) for p in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
    }


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
