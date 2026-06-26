from sqlalchemy import (Boolean, Column, Integer, JSON, Numeric,
                        String, Text, TIMESTAMP, ForeignKey)
from sqlalchemy.sql import func
from app.database import Base


class AutoFeedListing(Base):
    __tablename__ = "auto_feed_listings"
    id                = Column(Integer, primary_key=True)
    user_id           = Column(Integer, ForeignKey("users.id"), nullable=False)
    keyword_id        = Column(Integer, ForeignKey("auto_keywords.id",
                               ondelete="SET NULL"), nullable=True)
    platform          = Column(String(50), nullable=False)
    external_id       = Column(String(200))
    title             = Column(Text)
    price             = Column(Numeric(10, 2))
    currency          = Column(String(10), default="RON")
    year              = Column(Integer)
    km                = Column(Integer)
    fuel_type         = Column(String(50))
    transmission      = Column(String(50))
    body_type         = Column(String(50))
    location          = Column(String(200))
    image_url         = Column(Text)
    images_json       = Column(JSON, default=list)
    url               = Column(Text)
    description       = Column(Text)
    score             = Column(Integer, default=50)
    grade             = Column(String(5), default="C")
    import_score_json = Column(JSON)
    status            = Column(String(20), default="active")
    found_at          = Column(TIMESTAMP, server_default=func.now())
    last_checked_at   = Column(TIMESTAMP)
