from sqlalchemy import Column, Integer, String, Float, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    ean = Column(String, nullable=True, index=True)
    sku = Column(String, nullable=True, index=True)
    # FlipRadar — brand dedicat pentru filtrare precisa (separat de nume)
    brand = Column(String(200), nullable=True)
    category = Column(String, nullable=True)
    # FlipRadar — subcategorie inferata per magazin (taxonomie SOURCE_CATEGORIES)
    subcategory = Column(String(200), nullable=True)
    image_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    current_price = Column(Float, nullable=True)
    # FlipRadar — pret de lista original (pentru detectarea reducerilor / on_sale)
    original_price = Column(Numeric(10, 2), nullable=True)
    resale_price = Column(Float, nullable=True)
    currency = Column(String, default="EUR")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    watchlist_items = relationship("WatchlistItem", back_populates="product", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="product", cascade="all, delete-orphan")
    sources = relationship("ProductSource", back_populates="product", cascade="all, delete-orphan")
    # FlipRadar — sugestii de surse (potrivire pe nume) care asteapta confirmarea userului.
    suggestions = relationship("ProductSourceSuggestion", back_populates="product", cascade="all, delete-orphan")
