# FlipRadar — model pentru loturi din licitatii auto (Copart/IAAI/SCA/OpenLane).
# Schema de baza; modulul care o populeaza vine separat.
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, JSON, Boolean, ForeignKey
from datetime import datetime
from app.database import Base


class AutoLot(Base):
    __tablename__ = "auto_lot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # NULL pentru loturi gasite prin cautarea manuala; setat pentru cele din feed-ul monitorizat.
    keyword_id = Column(Integer, ForeignKey("auto_lot_keywords.id", ondelete="SET NULL"), nullable=True)
    platform = Column(String(50))  # "copart" | "iaai" | "sca" | "openlane"
    lot_number = Column(String(100))
    title = Column(Text, nullable=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    odometer = Column(Integer, nullable=True)
    damage_primary = Column(String(100), nullable=True)
    damage_secondary = Column(String(100), nullable=True)
    location_city = Column(String(100), nullable=True)
    location_state = Column(String(100), nullable=True)
    auction_date = Column(DateTime, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    source_url = Column(Text)
    current_bid = Column(Numeric(10, 2), nullable=True)  # NULL daca necesita cont
    buy_now_price = Column(Numeric(10, 2), nullable=True)
    title_type = Column(String(50), nullable=True)  # NULL daca necesita cont
    starts = Column(Boolean, nullable=True)
    drives = Column(Boolean, nullable=True)
    keys_present = Column(Boolean, nullable=True)
    vin = Column(String(20), nullable=True)
    ai_description_extract = Column(JSON, nullable=True)  # datele extrase de AI din descriere
    saved = Column(Boolean, default=False)  # flag „Salveaza” din cautarea manuala (pastrat pt. pagina Loturi Salvate)
    # Feed monitorizat: active/saved/ignored (independent de coloana `saved` de mai sus).
    status = Column(String(20), default="active")
    last_seen_at = Column(DateTime, nullable=True)  # ultima data cand scanerul a mai vazut lotul
    created_at = Column(DateTime, default=datetime.utcnow)
