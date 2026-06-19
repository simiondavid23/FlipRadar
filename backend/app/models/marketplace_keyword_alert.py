# FlipRadar — Modulul 1 Marketplace: alerte keyword (config wizard 3 pasi).
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class MarketplaceKeywordAlert(Base):
    __tablename__ = "marketplace_keyword_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(50))
    keyword = Column(String(300))
    category = Column(String(200), nullable=True)
    subcategory = Column(String(200), nullable=True)
    filters = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
