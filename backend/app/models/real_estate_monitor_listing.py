"""Anunt imobiliar monitorizat (tabel real_estate_listings).

NOTA: nume de clasa DISTINCT (RealEstateMonitorListing) fata de modelul existent
RealEstateListing (tabel real_estate_listing) ca sa nu existe coliziune in registry
SQLAlchemy / pe numele de tabel. Codul nou il importa aliasat ca RealEstateListing.
"""
from sqlalchemy import (Boolean, Column, Integer, JSON, Numeric,
                        String, Text, TIMESTAMP, ForeignKey)
from sqlalchemy.sql import func
from app.database import Base


class RealEstateMonitorListing(Base):
    __tablename__ = "real_estate_listings"
    id                        = Column(Integer, primary_key=True)
    user_id                   = Column(Integer, ForeignKey("users.id"), nullable=False)
    keyword_id                = Column(Integer, ForeignKey("real_estate_keywords.id",
                                       ondelete="SET NULL"), nullable=True)
    platform                  = Column(String(50), nullable=False)
    external_id               = Column(String(200))
    source                    = Column(String(20), default="platform")
    title                     = Column(Text)
    price                     = Column(Numeric(10, 2))
    currency                  = Column(String(10), default="EUR")
    price_per_sqm             = Column(Numeric(8, 2))
    property_type             = Column(String(50))
    rooms                     = Column(Integer)
    area_sqm                  = Column(Integer)
    floor                     = Column(String(30))
    zone_raw                  = Column(String(200))
    zone_normalized           = Column(String(200))
    city                      = Column(String(100))
    furnished                 = Column(Boolean)
    image_url                 = Column(Text)
    images_json               = Column(JSON, default=list)
    url                       = Column(Text)
    # Identificator vanzator — folosit pentru afisare in feed/export.
    # Populat din datele scraperului cand sunt disponibile.
    seller_id                 = Column(String(200))
    description               = Column(Text)
    score                     = Column(Integer, default=50)
    grade                     = Column(String(5), default="C")
    price_history             = Column(JSON, default=list)
    status                    = Column(String(20), default="active")
    found_at                  = Column(TIMESTAMP, server_default=func.now())
    # Data postarii pe platforma; NULL cand sursa nu o expune (IM-7).
    listed_at                 = Column(TIMESTAMP)
    last_checked_at           = Column(TIMESTAMP)
    last_price_change_at      = Column(TIMESTAMP)
