from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
from datetime import datetime, timezone
from app.database import Base


class RadarSettings(Base):
    __tablename__ = "radar_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    discord_webhook_all = Column(String, nullable=True)
    discord_webhook_buy_now = Column(String, nullable=True)
    discord_webhook_maybe = Column(String, nullable=True)
    discord_webhook_auto = Column(Text, nullable=True)
    # Global Discord notification service (Module 1) — webhook-uri + toggle @here
    discord_webhook_auto_all = Column(Text, nullable=True)
    discord_webhook_auto_b = Column(Text, nullable=True)
    discord_webhook_imob_all = Column(Text, nullable=True)
    discord_webhook_imob_a = Column(Text, nullable=True)
    discord_webhook_imob_b = Column(Text, nullable=True)
    discord_here_radar = Column(Boolean, default=False)
    discord_here_auto = Column(Boolean, default=False)
    discord_here_imob = Column(Boolean, default=False)
    custom_zone_aliases = Column(JSON, default=dict)
    platform_olx_enabled = Column(Boolean, default=True, nullable=False)
    platform_vinted_enabled = Column(Boolean, default=True, nullable=False)
    platform_okazii_enabled = Column(Boolean, default=True, nullable=False)
    platform_facebook_enabled = Column(Boolean, default=False, nullable=False)
    platform_lajumate_enabled = Column(Boolean, default=True, nullable=False)
    platform_publi24_enabled = Column(Boolean, default=True, nullable=False)
    platform_autovit_enabled = Column(Boolean, default=True, nullable=False)
    platform_mobilede_enabled = Column(Boolean, default=True, nullable=False)
    vinted_cookie = Column(Text, nullable=True)
    lajumate_cookie = Column(Text, nullable=True)
    okazii_cookie = Column(Text, nullable=True)
    facebook_session_path = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
