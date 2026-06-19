# FlipRadar — model pentru anunturi auto din piata (OLX/Autovit/Mobile.de etc.).
# Schema de baza; modulul care o populeaza vine separat.
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, JSON, Boolean, ForeignKey
from datetime import datetime
from app.database import Base


class AutoListing(Base):
    __tablename__ = "auto_listing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # "olx_auto" | "autovit" | "mobile_de" | "autoscout24" | "facebook_auto" | "kleinanzeigen_auto"
    platform = Column(String(50))
    external_id = Column(String(200), nullable=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    km = Column(Integer, nullable=True)
    engine_type = Column(String(50), nullable=True)  # "benzina"|"diesel"|"hibrid"|"electric"|"gpl"
    gearbox = Column(String(20), nullable=True)  # "manuala"|"automata"
    body_type = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    pret = Column(Numeric(10, 2), nullable=True)
    moneda = Column(String(10), default="EUR")
    locatie = Column(String(200), nullable=True)
    titlu = Column(Text, nullable=True)
    descriere = Column(Text, nullable=True)
    source_url = Column(Text)
    thumbnail_url = Column(Text, nullable=True)
    ai_extract = Column(JSON, nullable=True)
    saved = Column(Boolean, default=False)
    listed_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
