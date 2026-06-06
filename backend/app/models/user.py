from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    security_question = Column(String, nullable=True)
    security_answer_hash = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    # --- Flag-uri per funcționalitate (controlabile de admin) ---
    # Implicit True ca utilizatorii existenți să nu fie blocați din funcțiile pe care
    # le foloseau deja. Adminii pot seta orice flag pe False pentru a restricționa
    # abuzuri/costuri (ex: dezactivarea AI pentru utilizatorii free). Garda HTTP returnează 403 când e False.
    can_use_ai = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_scraping = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_alerts = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_import_export = Column(Boolean, default=True, nullable=False, server_default="true")
    # FlipRadar — pragul minim de scadere (fractie 0-1) pentru alertele Flash Deal
    flash_deal_threshold = Column(Numeric(5, 2), default=0.15)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    watchlist_items = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
