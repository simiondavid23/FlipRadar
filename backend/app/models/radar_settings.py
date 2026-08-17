from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Text, JSON
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
    # ALERT-1 — webhook dedicat pentru alerte de pret + flash deals
    discord_webhook_alerts = Column(Text, nullable=True)
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
    facebook_session_path = Column(String, nullable=True)
    # SHOP-2a — scannerul de deal-uri Shopify. Deal-urile sunt globale pe instanta,
    # dar setarile care le guverneaza raman per-user, ca tot restul.
    discord_webhook_deals = Column(Text, nullable=True)
    # None -> DEFAULT_DISCOUNT_THRESHOLD (20.0) din deal_scanner.
    deal_discount_threshold = Column(Float, nullable=True)
    # DEAL-2b — prag SEPARAT pentru R1 pe calea de listare: acolo pretul taiat e un
    # PRP permanent, nu referinta unui comerciant activ, deci relevanta incepe mult
    # mai sus. None -> DEFAULT_LISTING_R1_THRESHOLD (40.0) din listing_scanner.
    listing_r1_threshold = Column(Float, nullable=True)
    deal_scan_enabled = Column(Boolean, default=True, nullable=False)
    deal_shops_disabled = Column(JSON, default=list)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
