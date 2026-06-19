"""Router /api/ml — predictie pret + timp de vanzare pe baza modelelor ML."""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/ml", tags=["ML"])


class PredictInput(BaseModel):
    category: str
    features: Dict[str, Any] = {}


@router.post("/predict")
def predict(data: PredictInput, current_user: User = Depends(get_current_user)):
    # Import lazy: nu blocheaza pornirea aplicatiei daca dependintele ML lipsesc.
    try:
        from app.services.ml.price_predictor import predict_price_and_days
    except Exception as exc:
        return {"error": f"Modulul ML nu este disponibil: {exc}", "has_ml": False}
    return predict_price_and_days(data.category, data.features)
