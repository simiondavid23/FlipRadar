from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.schemas._types import UTCDateTime


_ALLOWED_CURRENCIES = {"EUR", "RON", "USD"}


class SaleCreate(BaseModel):
    product_name: Optional[str] = Field(None, description="Numele produsului — completat automat din inventar daca lipseste")
    quantity: int = Field(1, gt=0, description="Cantitatea trebuie sa fie pozitiva")
    sale_price: float = Field(..., ge=0, description="Pretul de vanzare nu poate fi negativ")
    currency: Optional[str] = None
    cost_price: Optional[float] = Field(None, ge=0)
    extra_costs: Optional[float] = Field(None, ge=0)
    platform: Optional[str] = None
    category: Optional[str] = None
    buyer: Optional[str] = None
    notes: Optional[str] = None
    sold_at: Optional[datetime] = None
    inventory_item_id: Optional[int] = Field(None, description="Daca e setat, vanzarea preia produsul din inventar si scade stocul")

    @field_validator("product_name")
    @classmethod
    def _validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if v not in _ALLOWED_CURRENCIES:
            raise ValueError(f"Moneda trebuie sa fie una din: {', '.join(sorted(_ALLOWED_CURRENCIES))}")
        return v


class SaleUpdate(BaseModel):
    product_name: Optional[str] = None
    quantity: Optional[int] = Field(None, gt=0)
    sale_price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    cost_price: Optional[float] = Field(None, ge=0)
    extra_costs: Optional[float] = Field(None, ge=0)
    platform: Optional[str] = None
    category: Optional[str] = None
    buyer: Optional[str] = None
    notes: Optional[str] = None
    sold_at: Optional[datetime] = None

    @field_validator("product_name")
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


class SaleResponse(BaseModel):
    id: int
    user_id: int
    product_name: str
    quantity: int
    sale_price: float
    currency: str
    cost_price: Optional[float] = None
    extra_costs: Optional[float] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    inventory_item_id: Optional[int] = None
    buyer: Optional[str] = None
    notes: Optional[str] = None
    sold_at: Optional[datetime] = None
    created_at: UTCDateTime

    class Config:
        from_attributes = True
