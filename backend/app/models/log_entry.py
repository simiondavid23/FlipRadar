"""MODIFICARE 12 — persistare opțională a log-urilor SSE în DB (TTL 24h).

Activată doar dacă LOG_DB_PERSISTENCE=true; logarea în memorie (deque) rămâne
sursa principală pentru stream-ul SSE și nu depinde de DB.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base
from app.utils.listing_dates import acum_local


class LogEntry(Base):
    __tablename__ = "log_entries"

    id         = Column(Integer, primary_key=True)
    module     = Column(String(50), nullable=False)
    level      = Column(String(10), nullable=False)
    message    = Column(Text, nullable=False)
    # TZ-1 — ora sistemului. `server_default=func.now()` dadea CURRENT_TIMESTAMP, adica
    # UTC: pagina de jurnal arata ultimul ciclu Radar la 21:40 in timp ce logul NSSM
    # (ora locala) il avea la 00:40. Default-ul Python il precede si ramane sursa.
    created_at = Column(DateTime(timezone=True), default=lambda: acum_local(),
                        server_default=func.now())

    __table_args__ = (
        Index("ix_log_entries_module_created", "module", "created_at"),
    )
