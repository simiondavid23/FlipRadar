from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    sale_price = Column(Float, nullable=False)
    currency = Column(String, default="EUR", nullable=False)
    cost_price = Column(Float, nullable=True)
    platform = Column(String, nullable=True)
    buyer = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    sold_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
