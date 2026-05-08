from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String, default="info")  # info, alert, success, warning
    is_read = Column(Boolean, default=False)
    link = Column(String, nullable=True)  # Optional link to navigate to
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
