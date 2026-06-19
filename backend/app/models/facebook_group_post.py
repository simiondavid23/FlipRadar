from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric
from datetime import datetime
from app.database import Base


class FacebookGroupPost(Base):
    __tablename__ = "facebook_group_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    config_id = Column(Integer, nullable=False)        # FK la facebook_group_configs.id
    post_id = Column(String(200), nullable=True)       # ID extern Facebook
    group_url = Column(Text, nullable=True)
    text = Column(Text, nullable=True)                 # primele 1000 caractere
    pret = Column(Numeric(10, 2), nullable=True)
    moneda = Column(String(10), nullable=True)
    tip_anunt = Column(String(20), nullable=True)      # "vanzare" | "inchiriere"
    tip_proprietate = Column(String(50), nullable=True)
    suprafata_mp = Column(Integer, nullable=True)
    etaj = Column(String(30), nullable=True)
    zona = Column(String(100), nullable=True)
    termen = Column(String(20), nullable=True)         # "lung" | "scurt"
    facilitati = Column(String(200), nullable=True)    # "parcare, balcon"
    posted_at = Column(DateTime, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
