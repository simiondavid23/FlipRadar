from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas._types import UTCDateTime


class RecentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: Optional[UTCDateTime] = None


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_products: int
    total_watchlist: int
    total_alerts: int
    active_alerts: int
    open_tickets: int
    in_progress_tickets: int
    total_tickets: int
    recent_users: List[RecentUser]


class TicketUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: Optional[str] = None


class TicketSummary(BaseModel):
    id: int
    subject: str
    status: str
    priority: str
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None
    user: TicketUser
    message_count: int


class TicketMessageResponse(BaseModel):
    id: int
    content: str
    is_admin: bool
    sender_name: str
    created_at: Optional[UTCDateTime] = None


class TicketDetail(BaseModel):
    id: int
    subject: str
    status: str
    priority: str
    created_at: Optional[UTCDateTime] = None
    user: TicketUser
    messages: List[TicketMessageResponse]


class SimpleMessage(BaseModel):
    message: str


class AlertCheckResult(BaseModel):
    triggered: int


# --- Per-user administration ----------------------------------------------

class UserFeatureFlags(BaseModel):
    """The admin-controllable feature gates for a single user account."""

    can_use_ai: bool = True
    can_use_scraping: bool = True
    can_use_alerts: bool = True
    can_use_import_export: bool = True


class UserFeatureUpdate(BaseModel):
    """Partial update for user flags — only the fields provided get written."""

    can_use_ai: Optional[bool] = None
    can_use_scraping: Optional[bool] = None
    can_use_alerts: Optional[bool] = None
    can_use_import_export: Optional[bool] = None


class UserActiveUpdate(BaseModel):
    is_active: bool


class AdminUserSummary(BaseModel):
    """One row in the admin Users table — identity + small stat preview."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    can_use_ai: bool
    can_use_scraping: bool
    can_use_alerts: bool
    can_use_import_export: bool
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None
    # preview counts — computed by router, not read from ORM
    products_count: int = 0
    watchlist_count: int = 0
    active_alerts_count: int = 0
    sales_count: int = 0


# --- Global / filtered activity listings -----------------------------------
# Shared mini-user envelope used by every "list X with their owner" response.

class AdminMiniUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: Optional[str] = None


class AdminProductItem(BaseModel):
    """One row in /api/admin/products."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None  # Direct link back to the seller page.
    category: Optional[str] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[UTCDateTime] = None
    # Product.user_id is nullable (legacy rows), so keep the owner optional.
    owner: Optional[AdminMiniUser] = None


class AdminWatchlistItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notes: Optional[str] = None
    added_at: Optional[UTCDateTime] = None
    product: Optional[AdminProductItem] = None
    owner: AdminMiniUser


class AdminAlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_price: float
    currency: Optional[str] = None
    alert_type: str
    is_active: bool
    is_triggered: bool
    triggered_at: Optional[UTCDateTime] = None
    created_at: Optional[UTCDateTime] = None
    product: Optional[AdminProductItem] = None
    owner: AdminMiniUser


class AdminInventoryItem(BaseModel):
    """One row in /api/admin/inventory."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str] = None
    sku: Optional[str] = None
    quantity: int
    purchase_price: float
    currency: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    purchased_at: Optional[datetime] = None
    created_at: Optional[UTCDateTime] = None
    owner: AdminMiniUser


class AdminSaleItem(BaseModel):
    """One row in /api/admin/sales."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_name: str
    quantity: int
    sale_price: float
    currency: Optional[str] = None
    cost_price: Optional[float] = None
    platform: Optional[str] = None
    buyer: Optional[str] = None
    notes: Optional[str] = None
    sold_at: Optional[datetime] = None
    created_at: Optional[UTCDateTime] = None
    owner: AdminMiniUser


class AdminFavoriteItem(BaseModel):
    """One row in /api/admin/favorites — covers both favorites and blacklist."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_blacklisted: bool
    notes: Optional[str] = None
    added_at: Optional[UTCDateTime] = None
    product: Optional[AdminProductItem] = None
    owner: AdminMiniUser


class AdminChatMessageItem(BaseModel):
    """One row in /api/admin/chat-messages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str  # "user" or "assistant"
    content: str
    needs_staff: bool
    created_at: Optional[UTCDateTime] = None
    owner: AdminMiniUser


class AdminUserDetail(BaseModel):
    """Everything the admin sees on the user detail panel."""

    model_config = ConfigDict(from_attributes=True)

    # identity
    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None
    # flags
    can_use_ai: bool
    can_use_scraping: bool
    can_use_alerts: bool
    can_use_import_export: bool
    # activity / usage stats (computed)
    products_count: int = 0
    watchlist_count: int = 0
    favorites_count: int = 0
    blacklist_count: int = 0
    total_alerts: int = 0
    active_alerts: int = 0
    triggered_alerts: int = 0
    inventory_count: int = 0
    inventory_value: float = 0.0
    sales_count: int = 0
    sales_revenue: float = 0.0
    sales_profit: float = 0.0
    tickets_count: int = 0
    open_tickets: int = 0
    chat_messages_count: int = 0
    last_sale_at: Optional[UTCDateTime] = None
    last_chat_at: Optional[UTCDateTime] = None
