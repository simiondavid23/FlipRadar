from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class ProductSource(Base):
    __tablename__ = "product_sources"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=False)
    current_price = Column(Float, nullable=True)
    currency = Column(String, default="EUR", nullable=False)
    # RETAIL-2: stoc pe sursa, tri-state — True/False din pagina, NULL = necunoscut
    # (magazinul nu declara disponibilitatea sau sursa n-a fost inca extrasa prin link).
    in_stock = Column(Boolean, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("product_id", "source", name="uq_product_source"),)

    product = relationship("Product", back_populates="sources")
