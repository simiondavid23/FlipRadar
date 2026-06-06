from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base


class RadarPreset(Base):
    __tablename__ = "radar_presets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    keywords_config = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
