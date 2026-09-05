from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
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
    # SEEN-2 — memoria de pret a anuntului VAZUT, si cand n-are rand in feed (aruncat
    # pe vechime sau pe marja negativa). `pret_initial` e referinta fata de care se
    # judeca scaderea: asa scaderile treptate (6900 -> 6700 -> 6400 -> 5900) se
    # cumuleaza, in loc sa fie fiecare "prea mica". NULL = rand de dinainte de SEEN-2;
    # prima reaparitie doar stabileste referinta (backfill).
    pret_initial = Column(Float, nullable=True)
    pret_ultim = Column(Float, nullable=True)
    moneda = Column(String, nullable=True)
