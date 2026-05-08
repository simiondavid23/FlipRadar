from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.models.support_ticket import SupportTicket, TicketMessage
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/support", tags=["Support"])


_ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}


class CreateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    priority: Optional[str] = "normal"

    @field_validator("subject")
    @classmethod
    def _validate_subject(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Subiectul nu poate fi gol")
        return v.strip()

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Mesajul nu poate fi gol")
        return v.strip()

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, v: Optional[str]) -> str:
        v = (v or "normal").lower()
        if v not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Prioritatea trebuie sa fie una din: {', '.join(sorted(_ALLOWED_PRIORITIES))}")
        return v


class TicketReplyRequest(BaseModel):
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Mesajul nu poate fi gol")
        return v.strip()


@router.get("/tickets")
def get_my_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tickets for the current user."""
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "subject": t.subject,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "message_count": len(t.messages),
            "has_admin_reply": any(m.is_admin for m in t.messages),
        }
        for t in tickets
    ]


@router.post("/tickets")
def create_ticket(
    request: CreateTicketRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new support ticket."""
    ticket = SupportTicket(
        user_id=current_user.id,
        subject=request.subject,
        priority=request.priority,
    )
    db.add(ticket)
    db.flush()

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        content=request.message,
        is_admin=False,
    )
    db.add(msg)
    db.commit()

    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "message": "Ticketul a fost creat cu succes",
    }


@router.get("/tickets/{ticket_id}")
def get_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ticket details with messages."""
    ticket = (
        db.query(SupportTicket)
        .filter(SupportTicket.id == ticket_id, SupportTicket.user_id == current_user.id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticketul nu a fost gasit")

    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "messages": [
            {
                "id": m.id,
                "content": m.content,
                "is_admin": m.is_admin,
                "sender_name": m.sender.full_name or m.sender.username,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in ticket.messages
        ],
    }


@router.post("/tickets/{ticket_id}/reply")
def reply_to_ticket(
    ticket_id: int,
    request: TicketReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reply to a support ticket."""
    ticket = (
        db.query(SupportTicket)
        .filter(SupportTicket.id == ticket_id, SupportTicket.user_id == current_user.id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticketul nu a fost gasit")

    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Nu poti raspunde la un ticket inchis")

    msg = TicketMessage(
        ticket_id=ticket_id,
        sender_id=current_user.id,
        content=request.content,
        is_admin=False,
    )
    db.add(msg)
    db.commit()

    return {"message": "Mesajul a fost trimis"}
