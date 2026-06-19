# FlipRadar — model pentru anunturi imobiliare monitorizate (publice sau ale
# unui utilizator). Schema de baza; modulul care o populeaza vine separat.
from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, JSON, Boolean, ForeignKey
from datetime import datetime
from app.database import Base


class RealEstateListing(Base):
    __tablename__ = "real_estate_listing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # NULL = listing public monitorizat (nu apartine unui utilizator anume)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    platform = Column(String(50))  # "olx" | "storia" | "imobiliare" | "facebook"
    external_id = Column(String(200), nullable=True)
    tip_anunt = Column(String(20))  # "vanzare" | "inchiriere"
    tip_proprietate = Column(String(50))  # "apartament" | "casa" | "teren" | "comercial" | "garsoniera"
    camere = Column(Integer, nullable=True)
    suprafata_mp = Column(Numeric(8, 2), nullable=True)
    etaj = Column(String(50), nullable=True)
    pret = Column(Numeric(12, 2), nullable=True)
    moneda = Column(String(10), default="EUR")
    locatie_judet = Column(String(100), nullable=True)
    locatie_oras = Column(String(100), nullable=True)
    an_constructie = Column(Integer, nullable=True)
    facilitati = Column(JSON, nullable=True)  # {"parcare": true, "balcon": true, "lift": false}
    titlu = Column(Text, nullable=True)
    descriere = Column(Text, nullable=True)
    source_url = Column(Text)
    thumbnail_url = Column(Text, nullable=True)
    listed_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    sold_at = Column(DateTime, nullable=True)
    # FlipRadar — True daca utilizatorul a salvat explicit anuntul (vs. urmarit de scanner)
    saved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
