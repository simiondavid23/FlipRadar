from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ProductCreate(BaseModel):
    name: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    currency: str = "EUR"


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    ean: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None


class ProductSourceResponse(BaseModel):
    id: int
    source: str
    source_url: str
    current_price: Optional[float] = None
    currency: str
    last_checked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    id: int
    name: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    currency: str
    created_at: datetime
    sources: List[ProductSourceResponse] = []

    class Config:
        from_attributes = True


class RefreshSourceResult(BaseModel):
    source: str
    source_url: str
    old_price: Optional[float] = None
    new_price: Optional[float] = None
    currency: str
    changed: bool = False
    success: bool = True
    error: Optional[str] = None


class RefreshAllSourcesResponse(BaseModel):
    product: ProductResponse
    results: List[RefreshSourceResult]


class ProductSaveResponse(ProductResponse):
    """Response returned after POST /api/products/.

    `is_new` indicates whether a new product row was created.
    `previous_price` is the price the product had *before* this save (only set
    when the product already existed and the price was updated).
    """
    is_new: bool = True
    previous_price: Optional[float] = None
    price_changed: bool = False


class PriceHistoryResponse(BaseModel):
    id: int
    product_id: int
    price: float
    currency: str
    source: Optional[str] = None
    recorded_at: datetime

    class Config:
        from_attributes = True


class ProductDetailResponse(BaseModel):
    product: ProductResponse
    price_history: List[PriceHistoryResponse] = []
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    average_price: Optional[float] = None
