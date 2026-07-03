"""Router /api/ml — statistici colectare date + predictie pret/timp + reantrenare."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/stats")
def ml_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.ml.price_predictor import get_model_stats
    from app.models.market_listing import MarketListing
    from sqlalchemy import func

    stats = get_model_stats()
    if not isinstance(stats, dict):
        stats = {}

    # MODIFICARE 19 — calitatea datelor de antrenare per categorie (complete/total).
    for category in ["auto_bmw", "electronics_apple"]:
        total = db.query(func.count(MarketListing.id)).filter(
            MarketListing.category == category).scalar() or 0
        complete = db.query(func.count(MarketListing.id)).filter(
            MarketListing.category == category,
            MarketListing.features_complete == True).scalar() or 0
        cat = stats.get(category)
        if not isinstance(cat, dict):
            cat = {}
            stats[category] = cat
        cat["total"] = total
        cat["complete"] = complete
        cat["completeness_pct"] = round(complete / total * 100) if total else 0

    return stats


class PredictRequest(BaseModel):
    category: str           # "auto_bmw" or "electronics_apple"
    features: dict


@router.post("/predict")
def ml_predict(
    payload: PredictRequest,
    current_user: User = Depends(get_current_user),
):
    if payload.category not in ("auto_bmw", "electronics_apple"):
        raise HTTPException(400, "Categorie necunoscuta.")
    from app.services.ml.price_predictor import predict_price
    result = predict_price(payload.category, payload.features)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/retrain")
def ml_retrain(
    current_user: User = Depends(get_current_user),
):
    """Trigger manual model retrain."""
    from app.services.ml.price_predictor import train_ml_models_if_ready
    try:
        train_ml_models_if_ready()
        return {"status": "ok", "message": "Reantrenare finalizata."}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.post("/sold-detection")
def run_sold_detection_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger manual sold detection run."""
    from app.services.ml.sold_detector import run_sold_detection
    try:
        stats = run_sold_detection(db, batch_size=200)
        return {
            "ok": True,
            "checked": stats["checked"],
            "sold":    stats["sold"],
            "errors":  stats["errors"],
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))
