"""MODIFICARE 7 — coadă Discord persistentă în PostgreSQL.

Înlocuiește coada in-memory din discord_service: notificările supraviețuiesc
restartului backend-ului (status pending → sent/failed).
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class DiscordQueueItem(Base):
    __tablename__ = "discord_queue"

    id           = Column(Integer, primary_key=True, index=True)
    webhook_url  = Column(String, nullable=False)
    embed        = Column(Text, nullable=False)        # JSON serializat
    listing_id   = Column(String, nullable=False)
    module       = Column(String(30), nullable=False)  # radar/auto/imobiliare
    grade        = Column(String(2))
    mention_here = Column(Boolean, default=False)
    image_url    = Column(String)
    status       = Column(String(20), default="pending", index=True)
                                                       # pending/sent/failed
    retry_count  = Column(Integer, default=0)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at      = Column(DateTime(timezone=True))
    error_msg    = Column(Text)
