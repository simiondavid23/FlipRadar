from pydantic import BaseModel
from typing import Optional
from app.schemas._types import UTCDateTime
from app.schemas.product import ProductResponse


class FavoriteCreate(BaseModel):
    product_id: int
    is_blacklisted: bool = False
    notes: Optional[str] = None


class FavoriteResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    is_blacklisted: bool
    notes: Optional[str] = None
    added_at: UTCDateTime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True
