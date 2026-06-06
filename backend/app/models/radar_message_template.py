from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base


class RadarMessageTemplate(Base):
    __tablename__ = "radar_message_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False, default="all")
    template_text = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
