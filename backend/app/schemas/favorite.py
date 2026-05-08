from pydantic import BaseModel
from typing import Optional
from datetime import datetime
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
    added_at: datetime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True
