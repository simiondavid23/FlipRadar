from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from app.schemas._types import UTCDateTime


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=100)
    full_name: Optional[str] = Field(default=None, max_length=100)
    security_question: str = Field(min_length=3, max_length=200)
    security_answer: str = Field(min_length=2, max_length=200)

    @field_validator("username")
    @classmethod
    def username_alnum(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Numele de utilizator poate contine doar litere, cifre, _, -, .")
        return stripped


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool = False
    # Feature flags — frontend uses them to hide links for revoked capabilities
    can_use_ai: bool = True
    can_use_scraping: bool = True
    can_use_alerts: bool = True
    can_use_import_export: bool = True
    # FlipRadar — ITEM 16: pragul Flash Deal, ca pagina de setari sa stie valoarea curenta
    flash_deal_threshold: Optional[float] = 0.15
    # FlipRadar — config per-functionalitate AI (cheile False = dezactivate)
    ai_features_config: Optional[dict] = None
    created_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None


class SecurityQuestionResponse(BaseModel):
    security_question: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    security_answer: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=6, max_length=100)
