from fastapi import APIRouter
from sqlalchemy import text
from datetime import datetime, timezone
from app.database import SessionLocal

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check():
    """Endpoint de monitorizare — accesibil fără autentificare."""
    result = {
        "status": "ok",
        "db": "ok",
        "scheduler": "ok",
        "jobs": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Verifică DB
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as exc:
        result["db"] = f"error: {str(exc)[:120]}"
        result["status"] = "degraded"

    # Verifică scheduler și job-uri
    try:
        from app.main import scheduler
        if not scheduler.running:
            result["scheduler"] = "stopped"
            result["status"] = "degraded"
        for job in scheduler.get_jobs():
            result["jobs"].append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
    except Exception as exc:
        result["scheduler"] = f"error: {str(exc)[:80]}"

    return result
