from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime, timezone
from app.database import Base


class RadarSeenId(Base):
    __tablename__ = "radar_seen_ids"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "external_id", name="uq_radar_seen_user_platform_ext"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
