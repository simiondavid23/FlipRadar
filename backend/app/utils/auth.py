from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if a plain password matches the hashed version."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    """Hash a password for secure storage."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Extract and validate the current user from the JWT token.

    Also refuses tokens belonging to deactivated accounts so that an admin
    can flip `is_active=False` and immediately cut off API access for any
    outstanding JWT the user still holds.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid sau expirat",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is not None:
            user_id = int(user_id)
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acest cont a fost dezactivat. Contacteaza administratorul.",
        )
    return user


def require_feature(flag: str):
    """Return a FastAPI dependency that 403s when the user's flag is False.

    Used on feature-gated routers (AI, scraping, alerts, import/export)
    so an admin can selectively disable a capability per user without touching
    their account's is_active status.
    """
    _human_labels = {
        "can_use_ai": "functiile AI",
        "can_use_scraping": "cautarea automata pe site-uri",
        "can_use_alerts": "alertele de pret",
        "can_use_import_export": "importul si exportul de date",
    }

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not getattr(current_user, flag, False):
            label = _human_labels.get(flag, "aceasta functie")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesul la {label} a fost dezactivat de administrator.",
            )
        return current_user

    return _checker