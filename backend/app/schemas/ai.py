from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []


class ChatResponse(BaseModel):
    response: str
    needs_staff: bool = False


class ProductAnalysisRequest(BaseModel):
    product_name: str
    category: Optional[str] = ""
    price: Optional[float] = 0
    source: Optional[str] = ""
    currency: Optional[str] = "EUR"


class ListingGenerationRequest(BaseModel):
    product_name: str
    category: Optional[str] = ""
    features: Optional[str] = ""
    price: Optional[float] = 0
    currency: Optional[str] = "EUR"


class AIResponse(BaseModel):
    result: str
    success: bool = True
