from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base


class RadarSettings(Base):
    __tablename__ = "radar_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    discord_webhook_all = Column(String, nullable=True)
    discord_webhook_buy_now = Column(String, nullable=True)
    discord_webhook_maybe = Column(String, nullable=True)
    platform_olx_enabled = Column(Boolean, default=True, nullable=False)
    platform_vinted_enabled = Column(Boolean, default=True, nullable=False)
    platform_okazii_enabled = Column(Boolean, default=True, nullable=False)
    platform_facebook_enabled = Column(Boolean, default=False, nullable=False)
    platform_lajumate_enabled = Column(Boolean, default=True, nullable=False)
    platform_publi24_enabled = Column(Boolean, default=True, nullable=False)
    platform_autovit_enabled = Column(Boolean, default=True, nullable=False)
    platform_mobilede_enabled = Column(Boolean, default=True, nullable=False)
    vinted_cookie = Column(Text, nullable=True)
    facebook_session_path = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
