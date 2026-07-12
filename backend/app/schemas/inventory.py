from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.schemas._types import UTCDateTime


_ALLOWED_CURRENCIES = {"EUR", "RON", "USD"}


class InventoryItemCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Numele produsului este obligatoriu")
    category: Optional[str] = None
    sku: Optional[str] = None
    quantity: int = Field(1, ge=0, description="Cantitatea nu poate fi negativa")
    purchase_price: float = Field(..., ge=0, description="Pretul nu poate fi negativ")
    currency: str = "RON"
    source: Optional[str] = None
    notes: Optional[str] = None
    purchased_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Numele produsului nu poate fi gol")
        return v.strip()

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in _ALLOWED_CURRENCIES:
            raise ValueError(f"Moneda trebuie sa fie una din: {', '.join(sorted(_ALLOWED_CURRENCIES))}")
        return v


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    quantity: Optional[int] = Field(None, ge=0)
    purchase_price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    purchased_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("Numele produsului nu poate fi gol")
        return v.strip()

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if v not in _ALLOWED_CURRENCIES:
            raise ValueError(f"Moneda trebuie sa fie una din: {', '.join(sorted(_ALLOWED_CURRENCIES))}")
        return v


class InventoryItemResponse(BaseModel):
    id: int
    user_id: int
    name: str
    category: Optional[str] = None
    sku: Optional[str] = None
    quantity: int
    purchase_price: float
    currency: str
    source: Optional[str] = None
    notes: Optional[str] = None
    purchased_at: Optional[datetime] = None
    created_at: UTCDateTime

    class Config:
        from_attributes = True
