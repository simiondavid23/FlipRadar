from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    currency = Column(String, default="EUR")
    source = Column(String, nullable=True)
    # FASHION-1a: varianta (marimea) careia ii apartine pretul inregistrat;
    # '' = fara varianta (rand la nivel de produs). Aceleasi default-uri ca pe
    # ProductSource.variant, ca istoricul sa se poata filtra pe acelasi triplet.
    variant = Column(String, nullable=False, default="", server_default="")
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    product = relationship("Product", back_populates="price_history")
