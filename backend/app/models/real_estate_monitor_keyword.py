"""Keyword de monitorizare imobiliare (tabel real_estate_keywords).

Distinct de modelul RealEstateAlert/RealEstateListing existent — acesta e pentru
noul modul "Imobiliare Monitor" (feed scorat + zone normalizate).
"""
from sqlalchemy import (Boolean, Column, Integer, Numeric,
                        String, Text, TIMESTAMP, ForeignKey)
from sqlalchemy.sql import func
from app.database import Base


class RealEstateMonitorKeyword(Base):
    __tablename__ = "real_estate_keywords"
    id                       = Column(Integer, primary_key=True)
    user_id                  = Column(Integer, ForeignKey("users.id"), nullable=False)
    name                     = Column(String(200), nullable=False)
    platform                 = Column(String(50), nullable=False)
    property_type            = Column(String(50))
    tip_anunt                = Column(String(50), default="vanzare")
    rooms                    = Column(Integer)
    area_min                 = Column(Integer)
    area_max                 = Column(Integer)
    price_min                = Column(Numeric(10, 2))
    price_max                = Column(Numeric(10, 2))
    price_currency           = Column(String(10), default="EUR")
    zone                     = Column(String(200))
    city                     = Column(String(100), default="București")
    floor_min                = Column(Integer)
    floor_max                = Column(Integer)
    furnished                = Column(Boolean)
    query                    = Column(Text)
    is_active                = Column(Boolean, default=True)
    notify_email             = Column(Boolean, default=False)
    notify_discord           = Column(Boolean, default=False)
    active_hours_start       = Column(Integer)
    active_hours_end         = Column(Integer)
    polling_interval_minutes = Column(Integer, default=30)
    created_at               = Column(TIMESTAMP, server_default=func.now())
