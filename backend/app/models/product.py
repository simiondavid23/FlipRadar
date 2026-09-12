from sqlalchemy import Column, Integer, String, Float, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.utils.listing_dates import acum_local
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
    # MAG-1 — CUM a intrat produsul prima data: link | deal | scan | manual (multimea
    # inchisa `ORIGINS` din routers/products.py, validata la intrare). Nullable pentru
    # randurile de dinaintea migrarii; la dedup NU se rescrie — un produs adaugat prin
    # link si reintalnit intr-un deal ramane `link`, fiindca `origin` descrie
    # provenienta, nu ultima atingere.
    origin = Column(String(10), nullable=True)
    current_price = Column(Float, nullable=True)
    # FlipRadar — pret de lista original (pentru detectarea reducerilor / on_sale)
    original_price = Column(Numeric(10, 2), nullable=True)
    resale_price = Column(Float, nullable=True)
    currency = Column(String, default="EUR")
    created_at = Column(DateTime, default=lambda: acum_local())
    updated_at = Column(DateTime, default=lambda: acum_local(), onupdate=lambda: acum_local())

    user = relationship("User")
    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    tracked_items = relationship("TrackedProduct", back_populates="product", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="product", cascade="all, delete-orphan")
    sources = relationship("ProductSource", back_populates="product", cascade="all, delete-orphan")
    # FlipRadar — sugestii de surse (potrivire pe nume) care asteapta confirmarea userului.
    suggestions = relationship("ProductSourceSuggestion", back_populates="product", cascade="all, delete-orphan")
    # MAG-1 — deal-urile promovate in acest produs. DELIBERAT fara cascada de stergere:
    # un deal e o OBSERVATIE a scannerului despre un magazin, nu o proprietate a
    # produsului, deci stergerea produsului nu are voie sa-l stearga. Comportamentul
    # implicit al SQLAlchemy pe o relatie fara cascada e exact ce vrem — anuleaza
    # `promoted_product_id` pe copii inainte de DELETE-ul parintelui, deci FK-ul din
    # baza (NO ACTION, cu PRAGMA foreign_keys=ON) nu mai are ce sa refuze. FK-ul NU s-a
    # schimbat in baza: pe SQLite asta ar fi cerut un rebuild de tabela pe 28k randuri,
    # iar relatia ORM rezolva problema fara sa atinga schema.
    promoted_deals = relationship("Deal", back_populates="promoted_product")
