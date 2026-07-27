"""FASHION-3a — scheme pentru profilurile de taxe si referintele de revanzare."""
from typing import Optional

from pydantic import BaseModel

from app.schemas._types import UTCDateTime


class FeeProfileCreate(BaseModel):
    platform: str
    label: str
    commission_pct: float = 0.0
    processing_pct: float = 0.0
    extra_pct: float = 0.0
    fixed_fee: float = 0.0
    shipping_cost: float = 0.0
    currency: str = "EUR"
    note: Optional[str] = None


class FeeProfileUpdate(BaseModel):
    """Doar campurile trimise se modifica (platform ramane cheia, nu se schimba)."""
    label: Optional[str] = None
    commission_pct: Optional[float] = None
    processing_pct: Optional[float] = None
    extra_pct: Optional[float] = None
    fixed_fee: Optional[float] = None
    shipping_cost: Optional[float] = None
    currency: Optional[str] = None
    note: Optional[str] = None


class FeeProfileResponse(BaseModel):
    id: int
    platform: str
    label: str
    commission_pct: float
    processing_pct: float
    extra_pct: float
    fixed_fee: float
    shipping_cost: float
    currency: str
    # Data verificarii manuale a procentelor pe pagina oficiala (text).
    verified_at: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True


class NetPreviewRequest(BaseModel):
    """FASHION-3b — cat ar ramane net pentru un pret inca nesalvat."""
    platform: str
    ref_price: float
    ref_currency: str = "EUR"


class NetPreviewResponse(BaseModel):
    net: float
    net_currency: str


class ResaleReferenceCreate(BaseModel):
    platform: str
    variant: str = ""          # "" = referinta la nivel de produs (conventia 1a)
    ref_price: float
    ref_currency: str = "EUR"
    source_url: Optional[str] = None


class ResaleReferenceUpdate(BaseModel):
    ref_price: Optional[float] = None
    ref_currency: Optional[str] = None
    source_url: Optional[str] = None


class ResaleReferenceResponse(BaseModel):
    id: int
    product_id: int
    platform: str
    variant: str
    ref_price: float
    ref_currency: str
    source_url: Optional[str] = None
    mode: str
    fetched_at: Optional[UTCDateTime] = None
    is_primary: bool
    # Calculate LIVE la fiecare raspuns, niciodata stocate: netul depinde de
    # profilul de taxe curent, care se poate edita oricand.
    net: Optional[float] = None
    net_currency: Optional[str] = None

    class Config:
        from_attributes = True
