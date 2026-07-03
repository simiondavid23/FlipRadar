from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class ProductSourceSuggestion(Base):
    """Sugestie de sursă găsită prin potrivire pe NUME (nu prin EAN) la scanarea
    cross-shop. Separată de ProductSource ca să NU intre niciodată în calculul
    `current_price` (minimul dintre surse) până când utilizatorul o confirmă.
    """
    __tablename__ = "product_source_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=False)
    name = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    currency = Column(String, default="EUR", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("product_id", "source", name="uq_product_suggestion_source"),)

    product = relationship("Product", back_populates="suggestions")
