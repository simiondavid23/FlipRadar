from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email sau parola incorecta")
    if not user.is_active:
        # Admin a dezactivat contul — refuzam login-ul inainte sa emitem JWT.
        raise HTTPException(
            status_code=403,
            detail="Acest cont a fost dezactivat. Contacteaza administratorul.",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


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
