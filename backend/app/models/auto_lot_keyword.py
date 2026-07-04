# FlipRadar — keyword pentru monitorizarea loturilor din licitatii auto
# (Copart / IAAI / SCA / OpenLane). Calchiat pe AutoKeyword (models/auto_keyword.py),
# adaptat pentru loturi: damage_primary + bid_max + location_state in loc de
# km_max / price / fuel_type etc. Numele coloanelor urmeaza conventia AutoKeyword
# (polling_interval_minutes, active_hours_* nullable; use_active_hours e derivat in UI).
from sqlalchemy import (Boolean, Column, Integer, Numeric,
                        String, TIMESTAMP, ForeignKey)
from sqlalchemy.sql import func
from app.database import Base


class AutoLotKeyword(Base):
    __tablename__ = "auto_lot_keywords"
    id                       = Column(Integer, primary_key=True)
    user_id                  = Column(Integer, ForeignKey("users.id"), nullable=False)
    name                     = Column(String(200), nullable=False)
    platform                 = Column(String(50), nullable=False)  # copart|iaai|sca|openlane
    make                     = Column(String(100))
    model                    = Column(String(100))
    year_from                = Column(Integer)
    year_to                  = Column(Integer)
    damage_primary           = Column(String(100))
    bid_max                  = Column(Numeric(10, 2))
    location_state           = Column(String(100))
    is_active                = Column(Boolean, default=True)
    notify_email             = Column(Boolean, default=False)
    notify_discord           = Column(Boolean, default=False)
    active_hours_start       = Column(Integer)
    active_hours_end         = Column(Integer)
    polling_interval_minutes = Column(Integer, default=15)
    last_scan_at             = Column(TIMESTAMP)
    created_at               = Column(TIMESTAMP, server_default=func.now())
