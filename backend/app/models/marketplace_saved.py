# FlipRadar — Modulul 1 Marketplace: anunturi salvate de utilizator.
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class MarketplaceSaved(Base):
    __tablename__ = "marketplace_saved"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(50))
    external_id = Column(String(200), nullable=True)
    title = Column(Text)
    price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), default="RON")
    source_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)
