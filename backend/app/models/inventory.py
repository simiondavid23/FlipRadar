from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.utils.listing_dates import acum_local
from app.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    sku = Column(String, nullable=True)
    quantity = Column(Integer, default=1, nullable=False)
    purchase_price = Column(Float, nullable=False)
    currency = Column(String, default="RON", nullable=False)
    source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    purchased_at = Column(DateTime, default=lambda: acum_local())
    created_at = Column(DateTime, default=lambda: acum_local())
    updated_at = Column(DateTime, default=lambda: acum_local(), onupdate=lambda: acum_local())

    user = relationship("User")
