from pydantic import BaseModel
from typing import Optional
from app.schemas._types import UTCDateTime
from app.schemas.product import ProductResponse


class WatchlistItemCreate(BaseModel):
    product_id: int
    notes: Optional[str] = None


class WatchlistItemUpdate(BaseModel):
    notes: Optional[str] = None


class WatchlistItemResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    notes: Optional[str] = None
    added_at: UTCDateTime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True
