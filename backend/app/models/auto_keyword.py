from sqlalchemy import (Boolean, Column, Integer, JSON, Numeric,
                        String, Text, TIMESTAMP, ForeignKey)
from sqlalchemy.sql import func
from app.database import Base


class AutoKeyword(Base):
    __tablename__ = "auto_keywords"
    id                       = Column(Integer, primary_key=True)
    user_id                  = Column(Integer, ForeignKey("users.id"), nullable=False)
    name                     = Column(String(200), nullable=False)
    platform                 = Column(String(50), nullable=False)
    make                     = Column(String(100))
    model                    = Column(String(100))
    query                    = Column(Text)
    year_from                = Column(Integer)
    year_to                  = Column(Integer)
    km_max                   = Column(Integer)
    price_max                = Column(Numeric(10, 2))
    price_currency           = Column(String(10), default="RON")
    fuel_type                = Column(String(50))
    transmission             = Column(String(50))
    body_type                = Column(String(50))
    location                 = Column(String(200))
    is_active                = Column(Boolean, default=True)
    notify_email             = Column(Boolean, default=False)
    notify_discord           = Column(Boolean, default=False)
    active_hours_start       = Column(Integer)
    active_hours_end         = Column(Integer)
    polling_interval_minutes = Column(Integer, default=10)
    # Categorie per-platforma + filtre tehnice confirmate (populate de formularul dinamic).
    category                 = Column(String(100))
    tech_filters             = Column(JSON)
    created_at               = Column(TIMESTAMP, server_default=func.now())
