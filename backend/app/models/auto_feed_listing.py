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
    # Marja absoluta (RON) fata de pretul de revanzare al keyword-ului — paritate cu Radar.
    # NULL cand keyword-ul nu are resale_price setat (listing fara scor/grad).
    margin_value      = Column(Numeric(10, 2), nullable=True)
    import_score_json = Column(JSON)
    # Review AI on-demand (paritate cu RadarListing.ai_review) — generat din generate_ai_review.
    ai_review         = Column(Text, nullable=True)
    status            = Column(String(20), default="active")
    found_at          = Column(TIMESTAMP, server_default=func.now())
    last_checked_at   = Column(TIMESTAMP)
    # Imbogatire on-demand a detaliului (poze/descriere/vanzator/data) — pattern Radar.
    seller_name       = Column(String(200), nullable=True)
    listed_at         = Column(TIMESTAMP, nullable=True)
    detail_fetched    = Column(Boolean, default=False)
    # Detectare duplicate (mirror exact pe RealEstateMonitorListing) — cazul OLX Auto
    # vs Autovit cross-postat automat de OLX Group intre cele 2 platforme.
    phash              = Column(String(64))
    color_hist         = Column(JSON)
    duplicate_group_id = Column(String(100))
    duplicate_level    = Column(Integer)
    duplicate_match_id = Column(Integer)
