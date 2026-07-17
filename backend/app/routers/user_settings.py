# FlipRadar — ITEM 16: setari per-utilizator (prag Flash Deal + furnizor AI, PKG-2).
from types import SimpleNamespace
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.ai_service import PROVIDERS, resolve_ai_config, AIConfigError

router = APIRouter(prefix="/api/users", tags=["User Settings"])


class UserSettings(BaseModel):
    flash_deal_threshold: Optional[float] = None
    ai_features_config: Optional[dict] = None
    # PKG-2 — furnizor AI comutabil. ai_api_key e write-only (absent = neschimbat).
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_api_key: Optional[str] = None


def _settings_payload(user: User) -> dict:
    """Raspunsul de setari. NICIODATA cheia AI in clar — doar ai_api_key_set."""
    return {
        "flash_deal_threshold": float(user.flash_deal_threshold or 0.15),
        "ai_features_config": user.ai_features_config or {},
        "ai_provider": (user.ai_provider or "groq"),
        "ai_model": user.ai_model,
        "ai_api_key_set": bool((user.ai_api_key or "").strip()),
    }


@router.get("/settings")
def get_user_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _settings_payload(current_user)


@router.patch("/settings")
def update_user_settings(
    payload: UserSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizeaza setarile utilizatorului curent. Pragul Flash Deal este o fractie
    intre 0.05 (5%) si 0.50 (50%). Campurile AI se actualizeaza doar daca sunt trimise;
    ai_api_key e write-only (absent = neschimbat, "" = sterge)."""
    if payload.flash_deal_threshold is not None:
        threshold = float(payload.flash_deal_threshold)
        if not (0.05 <= threshold <= 0.50):
            raise HTTPException(status_code=400, detail="Pragul trebuie sa fie intre 0.05 si 0.50.")
        current_user.flash_deal_threshold = threshold

    if payload.ai_features_config is not None:
        current_user.ai_features_config = payload.ai_features_config

    if payload.ai_provider is not None:
        provider = payload.ai_provider.strip().lower()
        if provider not in PROVIDERS:
            raise HTTPException(status_code=422, detail=f"Furnizor AI necunoscut: {provider}")
        current_user.ai_provider = provider

    if payload.ai_model is not None:
        model = payload.ai_model.strip()
        if len(model) > 100:
            raise HTTPException(status_code=422, detail="Numele modelului e prea lung (max 100 caractere).")
        current_user.ai_model = model or None

    # Write-only: actioneaza DOAR cand campul e prezent in payload. "" -> sterge (NULL).
    if "ai_api_key" in payload.model_fields_set:
        key = (payload.ai_api_key or "").strip()
        current_user.ai_api_key = key or None

    db.commit()
    db.refresh(current_user)
    return _settings_payload(current_user)


class AITestPayload(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@router.post("/ai/test")
def test_ai_connection(
    payload: AITestPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Testeaza conexiunea AI cu valorile EFECTIVE: payload > config salvata a
    userului > fallback env (groq). HTTP 200 in ambele cazuri — starea e in body."""
    eff = SimpleNamespace(
        ai_provider=(payload.provider or getattr(current_user, "ai_provider", None)),
        ai_api_key=((payload.api_key or "").strip() or getattr(current_user, "ai_api_key", None)),
        ai_model=((payload.model or "").strip() or getattr(current_user, "ai_model", None)),
    )
    try:
        provider, key, model = resolve_ai_config(eff)
    except AIConfigError as e:
        return {"ok": False, "error": str(e)}
    client = OpenAI(api_key=key, base_url=PROVIDERS[provider]["base_url"])
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            timeout=10,
        )
        return {"ok": True, "provider": provider, "model": model}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
