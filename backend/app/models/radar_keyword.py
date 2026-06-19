from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base


class RadarKeyword(Base):
    __tablename__ = "radar_keywords"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    max_price = Column(Float, nullable=False)
    min_price = Column(Float, nullable=True)
    resale_price = Column(Float, nullable=False)
    category = Column(String, nullable=True)
    exclude_words = Column(Text, nullable=True, default="[]")
    platforms = Column(Text, nullable=False, default='["olx","vinted","okazii"]')
    poll_interval_minutes = Column(Integer, default=5, nullable=False)
    judet = Column(String, nullable=True)
    oras = Column(String, nullable=True)
    condition = Column(String, default="all", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    preset_group = Column(String, nullable=True)
    min_margin_pct = Column(Float, default=10.0, nullable=False)
    notify_email = Column(Boolean, default=True, nullable=False)
    notify_discord = Column(Boolean, default=True, nullable=False)
    car_filters = Column(Text, nullable=True)
    # FlipRadar — config wizard marketplace (platform, categorie, subcategorie, filtre) serializat JSON
    marketplace_config = Column(Text, nullable=True)
    last_scan_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
