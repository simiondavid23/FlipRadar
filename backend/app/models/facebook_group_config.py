from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class FacebookGroupConfig(Base):
    __tablename__ = "facebook_group_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)          # FK implicit la users.id
    group_name = Column(String(200), nullable=False)   # nume afișat în UI
    group_url = Column(Text, nullable=False)           # URL complet grup FB
    keywords = Column(JSON, default=list)              # ["garsoniera", "2 camere"]
    negative_keywords = Column(JSON, default=list)     # ["caut", "schimb"]
    check_interval_hours = Column(Integer, default=2)  # 1, 2 sau 4 ore
    is_active = Column(Boolean, default=True)
    cookies_encrypted = Column(Text, nullable=True)    # cookies criptate
    cookies_saved_at = Column(DateTime, nullable=True)  # data salvarii cookies
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(50), nullable=True)  # "ok" | "eroare" | "cookies_expirate"
    created_at = Column(DateTime, default=datetime.utcnow)
