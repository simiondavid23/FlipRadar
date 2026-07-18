"""FlipRadar — endpointuri de licentiere (KEY-1). Prefix /api/license.

status  : public, in orice mod — frontend-ul decide fluxul (login clasic vs activare).
activate: DOAR mod local — valideaza cheia, o salveaza pe disc, creeaza userul local
          si emite sesiunea (aceleasi cookie-uri httpOnly ca login-ul clasic).
session : DOAR mod local — auto-login silentios din licenta de pe disc (la boot sau
          dupa expirarea refresh-ului), fara sa mai afiseze vreun ecran de login.
"""
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.auth import create_access_token, get_password_hash
# Refolosim exact mecanismul de sesiune al login-ului clasic (cookie httpOnly + durate).
from app.routers.auth import (
    _set_access_cookie,
    _set_refresh_cookie,
    _ACCESS_TOKEN_MINUTES,
    _REFRESH_TOKEN_DAYS,
)
from app.services import license_service
from app.services.license_service import LicenseError, is_local_mode

router = APIRouter(prefix="/api/license", tags=["License"])

_LOCAL_EMAIL = "local@flipradar.app"


class ActivateBody(BaseModel):
    key: str


def _ensure_local_user(db: Session) -> User:
    """Userul unic al instantei desktop. Idempotent: creat o singura data, apoi
    reutilizat. Parola e un token aleator nefolosibil (nu exista ecran de login
    in modul local), iar contul e admin (single-user = proprietarul instantei)."""
    user = db.query(User).filter(User.email == _LOCAL_EMAIL).first()
    if user:
        return user
    user = User(
        email=_LOCAL_EMAIL,
        username="local",
        full_name="Utilizator local",
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _emit_session(response: Response, user: User) -> None:
    access = create_access_token(
        {"sub": str(user.id)}, expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES))
    refresh = create_access_token(
        {"sub": str(user.id), "type": "refresh"}, expires_delta=timedelta(days=_REFRESH_TOKEN_DAYS))
    _set_access_cookie(response, access)
    _set_refresh_cookie(response, refresh)


@router.get("/status")
def get_license_status():
    """Public, orice mod. {"local_mode","activated"[,"lid","name","iss","exp"]}."""
    return license_service.get_status()


@router.post("/activate")
def activate(body: ActivateBody, response: Response, db: Session = Depends(get_db)):
    """Doar mod local. Valideaza cheia, o persista, creeaza userul local si emite
    sesiunea. Idempotent la re-apel (aceeasi cheie sau alta valida)."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Indisponibil.")
    try:
        license_service.parse_license(body.key)
    except LicenseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    license_service.save_license(body.key)
    user = _ensure_local_user(db)
    _emit_session(response, user)
    return license_service.get_status()


@router.post("/session")
def open_session(response: Response, db: Session = Depends(get_db)):
    """Doar mod local. Daca exista o licenta VALIDA pe disc, emite sesiunea fara
    interactiune (auto-login la boot / dupa expirarea refresh-ului); altfel 401."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Indisponibil.")
    key = license_service.load_license()
    if not key:
        raise HTTPException(status_code=401, detail="Nicio licenta activa.")
    try:
        license_service.parse_license(key)
    except LicenseError as e:
        raise HTTPException(status_code=401, detail=str(e))
    user = _ensure_local_user(db)
    _emit_session(response, user)
    return license_service.get_status()
