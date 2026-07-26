from pydantic import BaseModel
from typing import Optional, List
from app.schemas._types import UTCDateTime


class ProductCreate(BaseModel):
    name: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    original_price: Optional[float] = None
    resale_price: Optional[float] = None
    currency: str = "EUR"
    # FASHION-1c — marimea sursei salvate; "" = fara varianta (rand product-level).
    # E camp de SURSA, nu de produs: vezi excluderea din model_dump in create_product.
    variant: str = ""


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    ean: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    original_price: Optional[float] = None
    resale_price: Optional[float] = None
    currency: Optional[str] = None


class ProductSourceResponse(BaseModel):
    id: int
    source: str
    source_url: str
    current_price: Optional[float] = None
    currency: str
    # RETAIL-2 — tri-state: True/False din pagina magazinului, None = necunoscut.
    in_stock: Optional[bool] = None
    # FASHION-1a — marimea urmarita la aceasta sursa; "" = fara varianta.
    variant: str = ""
    last_checked_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True


class ProductSourceSuggestionResponse(BaseModel):
    id: int
    source: str
    source_url: str
    name: Optional[str] = None
    price: Optional[float] = None
    currency: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    id: int
    name: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    current_price: Optional[float] = None
    original_price: Optional[float] = None
    resale_price: Optional[float] = None
    currency: str
    created_at: UTCDateTime
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
    # FASHION-1a — marimea careia ii apartine pretul; "" = fara varianta.
    variant: str = ""
    recorded_at: UTCDateTime

    class Config:
        from_attributes = True


class ProductDetailResponse(BaseModel):
    product: ProductResponse
    price_history: List[PriceHistoryResponse] = []
    # FlipRadar — sugestii de surse cross-shop (potrivire pe nume) ce asteapta confirmare.
    suggestions: List[ProductSourceSuggestionResponse] = []
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    average_price: Optional[float] = None


# ── RETAIL-2 — adaugare produs prin link ─────────────────────────────────────────

class ProductFromUrlRequest(BaseModel):
    """Link-ul lipit de user in UI. Doar URL-ul: restul datelor vin din extractor."""
    url: str
    # FASHION-1c — marimea ceruta explicit; None/absent = produsul intreg (ca pana acum).
    variant: Optional[str] = None


class ExtractionMeta(BaseModel):
    """Cum au fost obtinute datele — arata in UI cat de sigura e extragerea si
    ajuta la diagnoza cand un magazin isi schimba structura."""
    method: str                            # "jsonld" | "og"
    override_applied: bool = False         # a intervenit un DOMAIN_OVERRIDES
    in_stock: Optional[bool] = None        # tri-state, ca pe sursa
    is_aggregate: bool = False             # pretul vine dintr-un interval (lowPrice)


class VariantOption(BaseModel):
    """O marime publicata de pagina, cu pretul si stocul ei (extractorul FASHION-1b)."""
    variant: str
    price: float
    in_stock: Optional[bool] = None


class ProductFromUrlResponse(ProductDetailResponse):
    """Detaliul complet al produsului (ca la GET /{id}) plus rezultatul salvarii,
    ca UI-ul sa poata afisa produsul imediat, fara un al doilea request."""
    is_new: bool = True
    previous_price: Optional[float] = None
    price_changed: bool = False
    domain_validated: bool = False         # domeniul e in VALIDATED_DOMAINS
    extraction: ExtractionMeta
    # FASHION-1c — marimile pe care le publica pagina, ca UI-ul (1d) sa poata oferi
    # alegerea fara un al doilea fetch. None = pagina nu publica oferte per marime.
    variants: Optional[List[VariantOption]] = None
