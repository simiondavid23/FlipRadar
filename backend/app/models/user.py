from sqlalchemy import Column, Integer, String, DateTime, Boolean
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
    # --- Per-feature flags (admin-controllable) ---
    # Default True so existing users aren't locked out of features they already
    # use. Admins can flip any of these to False to restrict abuse/cost, e.g.
    # disabling AI for free-tier users. The HTTP guards return 403 when False.
    can_use_ai = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_scraping = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_alerts = Column(Boolean, default=True, nullable=False, server_default="true")
    can_use_import_export = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    watchlist_items = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
