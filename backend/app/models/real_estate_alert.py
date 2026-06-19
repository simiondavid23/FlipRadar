# FlipRadar — Modul Imobiliare: alerte keyword (config + monitorizare).
from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class RealEstateAlert(Base):
    __tablename__ = "real_estate_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(50))
    tip_anunt = Column(String(20))
    tip_proprietate = Column(String(50))
    filters = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
