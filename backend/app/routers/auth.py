from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from jose import JWTError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    SecurityQuestionResponse,
    ResetPasswordRequest,
)
from app.utils.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Aceasta adresa de email este deja inregistrata")

    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="Acest nume de utilizator este deja folosit")

    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        security_question=user_data.security_question.strip(),
        security_answer_hash=get_password_hash(user_data.security_answer.strip().lower()),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# MODIFICARE 3 — durata de viață a token-urilor (acces scurt + refresh lung).
_ACCESS_TOKEN_MINUTES = 15
_REFRESH_TOKEN_DAYS = 7
_ACCESS_MAX_AGE = _ACCESS_TOKEN_MINUTES * 60        # 900s
_REFRESH_MAX_AGE = _REFRESH_TOKEN_DAYS * 24 * 3600  # 604800s


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token", value=token,
        httponly=True, samesite="lax", secure=False,  # secure=True în producție (HTTPS)
        max_age=_ACCESS_MAX_AGE,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token", value=token,
        httponly=True, samesite="lax", secure=False,
        max_age=_REFRESH_MAX_AGE,
    )


@router.post("/login")
def login(response: Response, login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email sau parola incorecta")
    if not user.is_active:
        # Admin a dezactivat contul — refuzam login-ul inainte sa emitem JWT.
        raise HTTPException(
            status_code=403,
            detail="Acest cont a fost dezactivat. Contacteaza administratorul.",
        )

    # MODIFICARE 3 — token-urile pleacă în cookie-uri httpOnly, nu în body.
    access_token = create_access_token(
        {"sub": str(user.id)}, expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES))
    refresh_token = create_access_token(
        {"sub": str(user.id), "type": "refresh"}, expires_delta=timedelta(days=_REFRESH_TOKEN_DAYS))
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)
    return {
        "message": "Autentificat cu succes",
        "user": {"id": user.id, "email": user.email, "is_admin": user.is_admin},
    }


@router.post("/refresh")
def refresh_token(request: Request, response: Response):
    """Reînnoiește access_token-ul folosind refresh_token-ul din cookie."""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token lipsă")
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token invalid")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token invalid")
        new_access = create_access_token(
            {"sub": user_id}, expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES))
        _set_access_cookie(response, new_access)
        return {"message": "Token reînnoit"}
    except HTTPException:
        raise
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token invalid sau expirat")


@router.post("/logout")
def logout(response: Response):
    """Șterge ambele cookie-uri de sesiune."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Deconectat"}


@router.get("/security-question", response_model=SecurityQuestionResponse)
def get_security_question(email: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.security_question:
        raise HTTPException(
            status_code=404,
            detail="Nu am gasit o intrebare de securitate pentru acest email.",
        )
    return SecurityQuestionResponse(security_question=user.security_question)


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not user.security_answer_hash:
        raise HTTPException(
            status_code=400,
            detail="Date invalide. Verifica emailul si raspunsul la intrebarea de securitate.",
        )

    if not verify_password(data.security_answer.strip().lower(), user.security_answer_hash):
        raise HTTPException(
            status_code=400,
            detail="Date invalide. Verifica emailul si raspunsul la intrebarea de securitate.",
        )

    user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Parola a fost resetata cu succes"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
