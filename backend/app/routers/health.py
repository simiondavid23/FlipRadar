import os
import re
import time
import requests
from fastapi import APIRouter
from sqlalchemy import text
from datetime import datetime, timezone
from app.database import SessionLocal
from app.version import APP_VERSION

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


# ── PKG-UPD — versiune + verificare GitHub Releases ─────────────────────────
_update_cache = {"checked_at": 0.0, "latest": None, "url": None}
UPDATE_CHECK_TTL_S = 6 * 3600
_RELEASES_URL = ("https://api.github.com/repos/"
                 "simiondavid23/FlipRadar/releases/latest")


def _parse_version(s):
    """Tuple de int-uri din primele 3 grupuri numerice; None daca nu exista
    niciunul — comparatie toleranta, nu stricta semver."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) if nums else None


def _fetch_latest_release():
    """(tag, url) sau (None, None). 404 = niciun release inca — normal."""
    r = requests.get(_RELEASES_URL, timeout=5,
                     headers={"Accept": "application/vnd.github+json"})
    if r.status_code != 200:
        return None, None
    d = r.json()
    return d.get("tag_name"), d.get("html_url")


@router.get("/version")
def version_info():
    """Versiunea curenta + daca exista una mai noua pe GitHub Releases.
    Accesibil fara autentificare (ca /health). Cache in-memory 6h, esecuri
    silentioase — mecanismul se activeaza la primul release. Opt-out prin
    FLIPRADAR_DISABLE_UPDATE_CHECK=1."""
    if os.getenv("FLIPRADAR_DISABLE_UPDATE_CHECK") == "1":
        return {"version": APP_VERSION, "latest": None,
                "update_available": False, "url": None}

    if time.time() - _update_cache["checked_at"] > UPDATE_CHECK_TTL_S:
        try:
            latest, url = _fetch_latest_release()
        except Exception:
            latest, url = None, None
        # checked_at se actualizeaza MEREU (inclusiv la esec): un GitHub cazut
        # nu se re-loveste la fiecare request.
        _update_cache["checked_at"] = time.time()
        _update_cache["latest"] = latest
        _update_cache["url"] = url

    latest = _update_cache["latest"]
    latest_v = _parse_version(latest)
    current_v = _parse_version(APP_VERSION)
    update_available = bool(latest_v and current_v and latest_v > current_v)
    return {
        "version": APP_VERSION,
        "latest": latest,
        "update_available": update_available,
        "url": _update_cache["url"],
    }
