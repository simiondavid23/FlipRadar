from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, timezone
from app.database import Base


class RadarBlockedSeller(Base):
    __tablename__ = "radar_blocked_sellers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    seller_id = Column(String, nullable=False, index=True)
    seller_name = Column(String, nullable=True)
    blocked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
