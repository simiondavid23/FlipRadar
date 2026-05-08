from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.schemas.product import ProductResponse


_ALLOWED_CURRENCIES = {"EUR", "RON", "USD"}
_ALLOWED_ALERT_TYPES = {"price_drop", "price_rise"}


class AlertCreate(BaseModel):
    product_id: int
    target_price: float = Field(..., gt=0, description="Trebuie sa fie mai mare decat 0")
    currency: str = "EUR"
    alert_type: str = "price_drop"  # price_drop | price_rise

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in _ALLOWED_CURRENCIES:
            raise ValueError(f"Moneda trebuie sa fie una din: {', '.join(sorted(_ALLOWED_CURRENCIES))}")
        return v

    @field_validator("alert_type")
    @classmethod
    def _validate_alert_type(cls, v: str) -> str:
        v = (v or "").lower()
        if v not in _ALLOWED_ALERT_TYPES:
            raise ValueError(f"Tipul alertei trebuie sa fie una din: {', '.join(sorted(_ALLOWED_ALERT_TYPES))}")
        return v


class AlertResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    target_price: float
    currency: str = "EUR"
    alert_type: str
    is_active: bool
    is_triggered: bool
    triggered_at: Optional[datetime] = None
    created_at: datetime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True
