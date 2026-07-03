import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.user import User
from app.services.log_manager import log_manager
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _get_user_from_token(token: str, db: Session) -> Optional[User]:
    """Verify a JWT token passed as a query param (needed for EventSource).

    EventSource nu suporta headere custom, deci tokenul vine ca ?token=...
    Decodam JWT-ul cu aceeasi cheie/algoritm ca restul aplicatiei (app.utils.auth).
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
        if not user_id:
            return None
        return db.query(User).filter(User.id == int(user_id)).first()
    except (JWTError, ValueError, TypeError):
        return None


@router.get("/stream")
async def stream_logs(
    module: str = "radar",
    token: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """SSE endpoint — streams log events for the given module.
    Token is passed as a query param because EventSource doesn't support headers.

    MODIFICARE 3 — EventSource(withCredentials) trimite automat cookie-ul httpOnly
    `access_token`; dacă nu vine token în query, îl citim din cookie.
    """
    if not token and request is not None:
        token = request.cookies.get("access_token")
    user = _get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalid sau lipsă.")
    if module not in log_manager.MODULES:
        raise HTTPException(status_code=400, detail=f"Modul necunoscut: {module}")

    async def generate():
        existing = log_manager.get_all(module)
        for entry in existing:
            yield f"data: {json.dumps(entry)}\n\n"
        last_id = existing[-1]["id"] if existing else 0
        while True:
            if await request.is_disconnected():
                break
            new = log_manager.get_since(module, last_id)
            for entry in new:
                yield f"data: {json.dumps(entry)}\n\n"
                last_id = max(last_id, entry["id"])
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return log_manager.get_stats()


@router.post("/test-emit")
def test_emit(current_user: User = Depends(get_current_user)):
    """Debug — emite cate o pereche de evenimente in fiecare modul si
    raporteaza dimensiunile bufferelor (verifica singleton-ul + maparea)."""
    from app.services.log_manager import log_manager, LogManager
    for module in LogManager.MODULES:
        log_manager.emit(module, "INFO",
                         f"Test emit → modul {module} functioneaza corect")
        log_manager.emit(module, "OK",
                         f"Buffer activ · {len(log_manager.get_all(module))} intrari")
    return {
        "emitted_to": LogManager.MODULES,
        "buffer_sizes": {
            m: len(log_manager.get_all(m))
            for m in LogManager.MODULES
        },
    }
