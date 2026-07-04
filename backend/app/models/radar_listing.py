from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text, Boolean
from datetime import datetime, timezone
from app.database import Base


class RadarListing(Base):
    __tablename__ = "radar_listings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    keyword_id = Column(Integer, ForeignKey("radar_keywords.id"), nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, default="RON", nullable=False)
    condition = Column(String, nullable=True)
    location = Column(String, nullable=True)
    url = Column(String, nullable=False)
    images = Column(Text, nullable=True, default="[]")
    description = Column(Text, nullable=True)
    seller_name = Column(String, nullable=True)
    seller_id = Column(String, nullable=True)
    score = Column(String, nullable=True)
    margin_pct = Column(Float, nullable=True)
    status = Column(String, default="active", nullable=False, index=True)
    ai_review = Column(Text, nullable=True)
    listed_at = Column(DateTime, nullable=True)
    found_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    last_checked_at = Column(DateTime, nullable=True)
    # Vinted: detaliul complet (poze/descriere/data) a fost adus on-demand o singura data.
    vinted_detail_fetched = Column(Boolean, default=False, nullable=False)
    # Facebook: detaliul complet (descriere/galerie) a fost adus on-demand o singura data.
    facebook_detail_fetched = Column(Boolean, default=False, nullable=False)
