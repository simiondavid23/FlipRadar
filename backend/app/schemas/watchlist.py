from pydantic import BaseModel
from typing import Optional
from datetime import datetime
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
    added_at: datetime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True
