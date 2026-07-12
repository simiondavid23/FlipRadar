from pydantic import BaseModel
from typing import Optional
from app.schemas._types import UTCDateTime


class NotificationCreate(BaseModel):
    title: str
    message: str
    notification_type: str = "info"
    link: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    link: Optional[str] = None
    created_at: UTCDateTime

    class Config:
        from_attributes = True
