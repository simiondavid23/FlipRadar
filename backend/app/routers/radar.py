"""Router HTTP pentru modulul Radar Marketplace.

Endpoint-urile sunt grupate logic: keywords, listings,
settings, facebook auth, stats. Toate cer un user autentificat
si filtreaza pe user_id-ul curent (un user nu poate vedea/edita datele altuia).

Mesajele de eroare sunt in romana, in ton cu restul aplicatiei.
"""
import io
import json
import os
import re
import threading
import contextvars
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import cast, func, Date
from sqlalchemy.orm import Session

from app.config import VAPID_PUBLIC_KEY
from app.rate_limit import limiter
from app.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.radar_keyword import RadarKeyword
from app.models.radar_listing import RadarListing
from app.models.radar_message_template import RadarMessageTemplate
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services.radar.ai_reviewer import generate_ai_review
from app.services.radar.categories import PLATFORM_CATEGORIES, get_category_label
from app.services.radar.discord_service import send_test_message
from app.services.radar.excel_exporter import build_listings_xlsx
from app.services.radar.facebook_auth import start_facebook_login_session
from app.services.radar.facebook_scraper import is_facebook_session_valid
from app.services.radar.scorer import calculate_fee_ceiling, calculate_score
from app.services.log_manager import set_log_user
from app.utils.auth import get_current_user
from app.utils.id_csv import parse_id_csv
from app.utils.radar_scanner import (
    cancel_keyword_scan,
    mark_keyword_deleted,
    restore_keyword_scan,
)


router = APIRouter(prefix="/api/radar", tags=["Radar Marketplace"])


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────


class KeywordCreate(BaseModel):
    name: str
    max_price: float
    min_price: Optional[float] = None
    resale_price: float
    category: Optional[str] = None
    platform: Optional[str] = None
    exclude_words: list[str] = []
    exclude_description_words: Optional[list] = None
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    platforms: list[str] = ["olx", "vinted", "okazii"]
    poll_interval_minutes: int = 5
    judet: Optional[str] = None
    oras: Optional[str] = None
    condition: str = "all"
    is_active: bool = True
    preset_group: Optional[str] = None
    min_margin_pct: float = 10.0
    # Praguri de grad ajustabile per-keyword (None = implicit 40/25/10).
    grade_a_min: Optional[float] = None
    grade_b_min: Optional[float] = None
    grade_c_min: Optional[float] = None
    notify_email: bool = True
    notify_discord: bool = True
    car_filters: Optional[dict] = None
    marketplace_config: Optional[dict] = None
    # RP-2 — engine de excluderi v2 (opt-in).
    exclude_matching_mode: Optional[str] = None
    exclude_exceptions: Optional[list[str]] = None


class KeywordUpdate(BaseModel):
    name: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    resale_price: Optional[float] = None
    category: Optional[str] = None
    platform: Optional[str] = None
    exclude_words: Optional[list[str]] = None
    exclude_description_words: Optional[list] = None
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    platforms: Optional[list[str]] = None
    poll_interval_minutes: Optional[int] = None
    judet: Optional[str] = None
    oras: Optional[str] = None
    condition: Optional[str] = None
    is_active: Optional[bool] = None
    preset_group: Optional[str] = None
    min_margin_pct: Optional[float] = None
    grade_a_min: Optional[float] = None
    grade_b_min: Optional[float] = None
    grade_c_min: Optional[float] = None
    notify_email: Optional[bool] = None
    notify_discord: Optional[bool] = None
    car_filters: Optional[dict] = None
    marketplace_config: Optional[dict] = None
    # RP-2 — engine de excluderi v2 (opt-in).
    exclude_matching_mode: Optional[str] = None
    exclude_exceptions: Optional[list[str]] = None


_DISCORD_WEBHOOK_PREFIX = "https://discord.com/api/webhooks/"


def _validate_discord_webhook(v):
    """Anti-SSRF: acceptam doar webhook-uri Discord reale. Gol/None = stergere, permis.

    Serverul face POST catre aceasta valoare (coada Discord + test-discord), deci un URL
    arbitrar ar fi un vector SSRF. Validarea sta la granita API (schema); constructia ORM
    directa din teste nu trece prin validator si ramane neatinsa.
    """
    if v is None or v == "":
        return v
    if not v.startswith(_DISCORD_WEBHOOK_PREFIX):
        raise ValueError("URL-ul trebuie sa fie un webhook Discord valid (https://discord.com/api/webhooks/...).")
    return v


class ListingStatusUpdate(BaseModel):
    status: str


class SettingsUpdate(BaseModel):
    discord_webhook_all: Optional[str] = None
    discord_webhook_buy_now: Optional[str] = None
    discord_webhook_maybe: Optional[str] = None
    discord_webhook_auto: Optional[str] = None
    discord_webhook_auto_all: Optional[str] = None
    discord_webhook_auto_b: Optional[str] = None
    discord_webhook_imob_all: Optional[str] = None
    discord_webhook_imob_a: Optional[str] = None
    discord_webhook_imob_b: Optional[str] = None
    discord_webhook_alerts: Optional[str] = None

    @field_validator(
        "discord_webhook_all", "discord_webhook_buy_now", "discord_webhook_maybe",
        "discord_webhook_auto", "discord_webhook_auto_all", "discord_webhook_auto_b",
        "discord_webhook_imob_all", "discord_webhook_imob_a", "discord_webhook_imob_b",
        "discord_webhook_alerts",
    )
    @classmethod
    def _check_webhooks(cls, v):
        return _validate_discord_webhook(v)

    discord_here_radar: Optional[bool] = None
    discord_here_auto: Optional[bool] = None
    discord_here_imob: Optional[bool] = None
    custom_zone_aliases: Optional[dict] = None
    platform_olx_enabled: Optional[bool] = None
    platform_vinted_enabled: Optional[bool] = None
    platform_okazii_enabled: Optional[bool] = None
    platform_facebook_enabled: Optional[bool] = None
    platform_lajumate_enabled: Optional[bool] = None
    platform_publi24_enabled: Optional[bool] = None
    platform_autovit_enabled: Optional[bool] = None
    platform_mobilede_enabled: Optional[bool] = None


class ManualSearchRequest(BaseModel):
    keyword: str
    max_price: float
    min_price: Optional[float] = None
    platform: Optional[str] = None
    platforms: list[str] = []
    category: Optional[str] = None
    exclude_words: list[str] = []


class DiscordTestRequest(BaseModel):
    webhook_url: str

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook(cls, v):
        return _validate_discord_webhook(v)


class ProxyConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: str = ""
    username: str = ""
    password: str = ""


class TemplateCreate(BaseModel):
    name: str
    platform: str = "all"
    template_text: str
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    template_text: Optional[str] = None
    is_default: Optional[bool] = None


class TemplateRender(BaseModel):
    listing_id: int
    pret_oferit: Optional[float] = None


class BulkAction(BaseModel):
    listing_ids: list[int]
    action: str  # "saved" | "ignored" | "sold"


class PushSubscribe(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _build_keyword_label(kw: RadarKeyword) -> Optional[str]:
    """Label human-readable al categoriei pentru AFISARE (camp calculat, nepersistat).

    Traduce valoarea tehnica din keyword.category (slug OLX / catalog_id Vinted) la
    label-ul din dropdown si adauga subcategoria din marketplace_config daca exista.
    La orice esec cade pe valoarea bruta -> nicio regresie.
    """
    platforms = _parse_json_list(kw.platforms)
    platform = getattr(kw, "platform", None) or (platforms[0] if platforms else None)

    mc = {}
    if getattr(kw, "marketplace_config", None):
        try:
            mc = json.loads(kw.marketplace_config) or {}
        except Exception:
            mc = {}
    sub = mc.get("subcategory") or mc.get("_keyword_subcategory")

    if kw.category:
        label = get_category_label(platform, kw.category)
    else:
        label = mc.get("category") or None

    if sub and isinstance(sub, str) and sub.strip():
        sub = sub.strip()
        if label and sub.lower() not in label.lower():
            label = f"{label} > {sub}"
        elif not label:
            label = sub
    return label or None


def _kw_to_dict(kw: RadarKeyword) -> dict:
    return {
        "id": kw.id,
        "name": kw.name,
        "max_price": kw.max_price,
        "min_price": kw.min_price,
        "resale_price": kw.resale_price,
        "category": kw.category,
        "category_label": _build_keyword_label(kw),
        "platform": getattr(kw, "platform", None),
        "exclude_words": _parse_json_list(kw.exclude_words),
        "exclude_description_words": (getattr(kw, "exclude_description_words", None) or []),
        "active_hours_start": getattr(kw, "active_hours_start", None),
        "active_hours_end": getattr(kw, "active_hours_end", None),
        "platforms": _parse_json_list(kw.platforms),
        "poll_interval_minutes": kw.poll_interval_minutes,
        "judet": kw.judet,
        "oras": kw.oras,
        "condition": kw.condition,
        "is_active": kw.is_active,
        "preset_group": kw.preset_group,
        "min_margin_pct": kw.min_margin_pct,
        "grade_a_min": getattr(kw, "grade_a_min", None),
        "grade_b_min": getattr(kw, "grade_b_min", None),
        "grade_c_min": getattr(kw, "grade_c_min", None),
        "notify_email": bool(getattr(kw, "notify_email", True)),
        "notify_discord": bool(getattr(kw, "notify_discord", True)),
        "car_filters": (json.loads(kw.car_filters) if getattr(kw, "car_filters", None) else None),
        "marketplace_config": _parse_json_obj(getattr(kw, "marketplace_config", None)),
        "exclude_matching_mode": getattr(kw, "exclude_matching_mode", "simple") or "simple",
        "exclude_exceptions": _parse_json_list(getattr(kw, "exclude_exceptions", None)),
        "last_scan_at": kw.last_scan_at.isoformat() if kw.last_scan_at else None,
        "created_at": kw.created_at.isoformat() if kw.created_at else None,
    }


def _listing_to_dict(listing: RadarListing, keyword: Optional[RadarKeyword] = None) -> dict:
    resale_price = keyword.resale_price if keyword else None
    fee_ceiling = None
    if resale_price:
        fee_ceiling = calculate_fee_ceiling(resale_price, listing.platform)
    # RP-1 — attributes_json contine atribute item + badge-uri + risk_reason + extras.
    try:
        _attrs = json.loads(listing.attributes_json) if listing.attributes_json else {}
    except Exception:
        _attrs = {}
    if not isinstance(_attrs, dict):
        _attrs = {}
    return {
        "id": listing.id,
        "keyword_id": listing.keyword_id,
        "keyword_name": keyword.name if keyword else None,
        "external_id": listing.external_id,
        "platform": listing.platform,
        "title": listing.title,
        "price": listing.price,
        "currency": listing.currency,
        "condition": listing.condition,
        "location": listing.location,
        "url": listing.url,
        "images": _parse_json_list(listing.images),
        "description": listing.description,
        "vinted_detail_fetched": listing.vinted_detail_fetched,
        "facebook_detail_fetched": listing.facebook_detail_fetched,
        "seller_name": listing.seller_name,
        "seller_id": listing.seller_id,
        "seller_reviews": listing.seller_reviews,
        "seller_rating": listing.seller_rating,
        "seller_risk": listing.seller_risk,
        "risk_reason": _attrs.get("risk_reason"),
        "attributes": _attrs.get("attributes"),
        "seller_badges": _attrs.get("seller_badges"),
        "seller_type": _attrs.get("okazii_seller_type"),
        "member_since": _attrs.get("olx_member_since"),
        "view_count": _attrs.get("view_count"),
        "favourite_count": _attrs.get("favourite_count"),
        "score": listing.score,
        "margin_pct": listing.margin_pct,
        "margin_value": (resale_price - listing.price) if resale_price else None,
        "resale_price": resale_price,
        "fee_ceiling": fee_ceiling,
        "status": listing.status,
        "ai_review": listing.ai_review,
        "listed_at": listing.listed_at.isoformat() if listing.listed_at else None,
        "found_at": listing.found_at.isoformat() if listing.found_at else None,
        "last_checked_at": listing.last_checked_at.isoformat() if listing.last_checked_at else None,
    }


def _parse_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    return []


def _parse_json_obj(raw) -> Optional[dict]:
    """RP-2-fix — marketplace_config ca OBIECT (defensiv): None → None, dict → dict,
    string JSON → dict parsat, orice malformat → None (nu aruncă 500 în serializer)."""
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _get_or_create_settings(db: Session, user_id: int) -> RadarSettings:
    s = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
    if s:
        return s
    s = RadarSettings(user_id=user_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _settings_to_dict(s: RadarSettings) -> dict:
    return {
        "id": s.id,
        "discord_webhook_all": s.discord_webhook_all,
        "discord_webhook_buy_now": s.discord_webhook_buy_now,
        "discord_webhook_maybe": s.discord_webhook_maybe,
        "discord_webhook_auto": getattr(s, "discord_webhook_auto", None),
        "discord_webhook_auto_all": getattr(s, "discord_webhook_auto_all", None),
        "discord_webhook_auto_b": getattr(s, "discord_webhook_auto_b", None),
        "discord_webhook_imob_all": getattr(s, "discord_webhook_imob_all", None),
        "discord_webhook_imob_a": getattr(s, "discord_webhook_imob_a", None),
        "discord_webhook_imob_b": getattr(s, "discord_webhook_imob_b", None),
        "discord_webhook_alerts": getattr(s, "discord_webhook_alerts", None),
        "discord_here_radar": bool(getattr(s, "discord_here_radar", False)),
        "discord_here_auto": bool(getattr(s, "discord_here_auto", False)),
        "discord_here_imob": bool(getattr(s, "discord_here_imob", False)),
        "custom_zone_aliases": getattr(s, "custom_zone_aliases", None) or {},
        "platform_olx_enabled": s.platform_olx_enabled,
        "platform_vinted_enabled": s.platform_vinted_enabled,
        "platform_okazii_enabled": s.platform_okazii_enabled,
        "platform_facebook_enabled": s.platform_facebook_enabled,
        "platform_lajumate_enabled": bool(getattr(s, "platform_lajumate_enabled", True)),
        "platform_publi24_enabled": bool(getattr(s, "platform_publi24_enabled", True)),
        "platform_autovit_enabled": bool(getattr(s, "platform_autovit_enabled", True)),
        "platform_mobilede_enabled": bool(getattr(s, "platform_mobilede_enabled", True)),
        "facebook_session_path": s.facebook_session_path,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _default_facebook_session_path(user_id: int) -> str:
    base_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"facebook_session_{user_id}.json")


# ──────────────────────────────────────────────────────────────────────────────
# CATEGORII (lista statica, expusa pentru frontend)
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/categories")
def list_categories(current_user: User = Depends(get_current_user)):
    return PLATFORM_CATEGORIES


# ──────────────────────────────────────────────────────────────────────────────
# KEYWORD ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/keywords")
def list_keywords(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.user_id == current_user.id)
        .order_by(RadarKeyword.created_at.desc())
        .all()
    )
    return [_kw_to_dict(k) for k in items]


@router.post("/keywords")
def create_keyword(
    data: KeywordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="Numele keyword-ului este obligatoriu.")
    if data.max_price is None or data.max_price <= 0:
        raise HTTPException(status_code=400, detail="Prețul maxim trebuie să fie pozitiv.")
    if data.resale_price is None or data.resale_price <= 0:
        raise HTTPException(status_code=400, detail="Prețul de revânzare trebuie să fie pozitiv.")
    if data.min_price is not None and data.min_price < 0:
        raise HTTPException(status_code=400, detail="Prețul minim nu poate fi negativ.")
    if data.min_price is not None and data.min_price > data.max_price:
        raise HTTPException(status_code=400, detail="Prețul minim nu poate fi mai mare decât prețul maxim.")
    kw = RadarKeyword(
        user_id=current_user.id,
        name=data.name.strip(),
        max_price=data.max_price,
        min_price=data.min_price,
        resale_price=data.resale_price,
        category=data.category,
        platform=data.platform,
        exclude_words=json.dumps(data.exclude_words or [], ensure_ascii=False),
        exclude_description_words=(data.exclude_description_words or None),
        active_hours_start=data.active_hours_start,
        active_hours_end=data.active_hours_end,
        platforms=json.dumps(data.platforms or ["olx"], ensure_ascii=False),
        poll_interval_minutes=max(1, int(data.poll_interval_minutes or 5)),
        judet=data.judet,
        oras=data.oras,
        condition=data.condition or "all",
        is_active=bool(data.is_active),
        preset_group=data.preset_group,
        min_margin_pct=float(data.min_margin_pct or 10.0),
        grade_a_min=data.grade_a_min,
        grade_b_min=data.grade_b_min,
        grade_c_min=data.grade_c_min,
        notify_email=bool(data.notify_email),
        notify_discord=bool(data.notify_discord),
        car_filters=(json.dumps(data.car_filters, ensure_ascii=False) if data.car_filters else None),
        marketplace_config=(json.dumps(data.marketplace_config, ensure_ascii=False) if data.marketplace_config else None),
        exclude_matching_mode=(data.exclude_matching_mode if data.exclude_matching_mode in ("simple", "advanced") else "simple"),
        exclude_exceptions=(json.dumps(data.exclude_exceptions, ensure_ascii=False) if data.exclude_exceptions else None),
    )
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return _kw_to_dict(kw)


@router.put("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int,
    data: KeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.id == keyword_id, RadarKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword-ul nu a fost găsit.")
    if data.name is not None:
        kw.name = data.name.strip()
    if data.max_price is not None:
        kw.max_price = data.max_price
    if data.min_price is not None:
        kw.min_price = data.min_price if data.min_price > 0 else None
    if data.resale_price is not None:
        kw.resale_price = data.resale_price
    if data.category is not None:
        kw.category = data.category or None
    if data.platform is not None:
        kw.platform = data.platform or None
    if data.exclude_words is not None:
        kw.exclude_words = json.dumps(data.exclude_words, ensure_ascii=False)
    if data.exclude_description_words is not None:
        kw.exclude_description_words = data.exclude_description_words or None
    # active_hours: setam doar daca au fost trimise explicit (inclusiv null pentru clear)
    if "active_hours_start" in data.model_fields_set:
        kw.active_hours_start = data.active_hours_start
    if "active_hours_end" in data.model_fields_set:
        kw.active_hours_end = data.active_hours_end
    if data.platforms is not None:
        kw.platforms = json.dumps(data.platforms, ensure_ascii=False)
    if data.poll_interval_minutes is not None:
        kw.poll_interval_minutes = max(1, int(data.poll_interval_minutes))
    if data.judet is not None:
        kw.judet = data.judet
    if data.oras is not None:
        kw.oras = data.oras
    if data.condition is not None:
        kw.condition = data.condition
    if data.is_active is not None:
        kw.is_active = bool(data.is_active)
    if data.preset_group is not None:
        kw.preset_group = data.preset_group
    if data.min_margin_pct is not None:
        kw.min_margin_pct = float(data.min_margin_pct)
    # Praguri de grad: setam doar daca au fost trimise explicit (inclusiv null = reset la implicit).
    for _g in ("grade_a_min", "grade_b_min", "grade_c_min"):
        if _g in data.model_fields_set:
            setattr(kw, _g, getattr(data, _g))
    if data.notify_email is not None:
        kw.notify_email = bool(data.notify_email)
    if data.notify_discord is not None:
        kw.notify_discord = bool(data.notify_discord)
    if data.car_filters is not None:
        kw.car_filters = json.dumps(data.car_filters, ensure_ascii=False) if data.car_filters else None
    if data.marketplace_config is not None:
        kw.marketplace_config = json.dumps(data.marketplace_config, ensure_ascii=False) if data.marketplace_config else None
    if data.exclude_matching_mode is not None:
        kw.exclude_matching_mode = data.exclude_matching_mode if data.exclude_matching_mode in ("simple", "advanced") else "simple"
    if data.exclude_exceptions is not None:
        kw.exclude_exceptions = json.dumps(data.exclude_exceptions, ensure_ascii=False) if data.exclude_exceptions else None
    # Validare combinata pret min/max dupa update
    if kw.min_price is not None and kw.min_price > kw.max_price:
        raise HTTPException(status_code=400, detail="Prețul minim nu poate fi mai mare decât prețul maxim.")
    db.commit()
    db.refresh(kw)
    return _kw_to_dict(kw)


@router.delete("/keywords/{keyword_id}")
def delete_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.id == keyword_id, RadarKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword-ul nu a fost găsit.")
    # Marcam keyword-ul ca sters inainte de delete fizic ca scanul curent sa-l
    # observe la urmatoarea iteratie. Un delay scurt da timp buclei sa iasa.
    import time as _time
    mark_keyword_deleted(keyword_id)
    _time.sleep(0.1)
    db.query(RadarListing).filter(
        RadarListing.keyword_id == keyword_id,
        RadarListing.user_id == current_user.id,
    ).delete()
    db.delete(kw)
    db.commit()
    return {"message": "Keyword-ul a fost șters."}


@router.patch("/keywords/{keyword_id}/toggle")
def toggle_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.id == keyword_id, RadarKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword-ul nu a fost găsit.")
    kw.is_active = not kw.is_active
    # Daca tocmai l-am dezactivat, intrerupe scanul curent imediat;
    # daca a fost activat, scoatem semaforul.
    if kw.is_active:
        restore_keyword_scan(kw.id)
    else:
        cancel_keyword_scan(kw.id)
    db.commit()
    return {"id": kw.id, "is_active": kw.is_active}


# ──────────────────────────────────────────────────────────────────────────────
# LISTINGS ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/listings")
def list_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    platform: Optional[str] = Query(None),
    score: Optional[str] = Query(None),
    keyword_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    hide_filtered: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    """Feed-ul de listinguri. Implicit returneaza active+saved, sortat dupa found_at DESC."""
    q = db.query(RadarListing).filter(RadarListing.user_id == current_user.id)

    if status_filter == "active":
        q = q.filter(RadarListing.status == "active")
    elif status_filter == "saved":
        q = q.filter(RadarListing.status == "saved")
    elif status_filter == "ignored":
        q = q.filter(RadarListing.status == "ignored")
    elif status_filter == "all":
        pass
    else:
        # default: doar active
        q = q.filter(RadarListing.status == "active")

    if platform:
        q = q.filter(RadarListing.platform == platform)
    if score:
        q = q.filter(RadarListing.score == score)
    if keyword_id:
        q = q.filter(RadarListing.keyword_id == keyword_id)
    if hide_filtered:
        # Ascunde scorurile D (sub pragul AI Filter); marja negativa nu e salvata
        # in baza de date, deci pe asta nu mai trebuie sa filtram aici.
        q = q.filter(RadarListing.score.in_(["A", "B", "C"]))

    total = q.count()
    items = (
        q.order_by(RadarListing.found_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    keyword_ids = {it.keyword_id for it in items}
    keywords = {
        k.id: k for k in db.query(RadarKeyword).filter(RadarKeyword.id.in_(keyword_ids)).all()
    } if keyword_ids else {}

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_listing_to_dict(it, keywords.get(it.keyword_id)) for it in items],
    }


# ──────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT (definit inaintea /listings/{listing_id} ca "export" sa nu fie
# interpretat ca listing_id:int — altfel FastAPI returneaza 422)
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/listings/export")
def export_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    platform: Optional[str] = Query(None),
    score: Optional[str] = Query(None),
    keyword_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),  # CSV de id-uri — folosit de "Exporta selectia"
):
    q = db.query(RadarListing).filter(RadarListing.user_id == current_user.id)
    if platform:
        q = q.filter(RadarListing.platform == platform)
    if score:
        q = q.filter(RadarListing.score == score)
    if keyword_id:
        q = q.filter(RadarListing.keyword_id == keyword_id)
    if status_filter and status_filter != "all":
        q = q.filter(RadarListing.status == status_filter)
    if date_from:
        try:
            q = q.filter(RadarListing.found_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(RadarListing.found_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    # "Exporta selectia" — filtreaza pe id-urile date (CSV tolerant), PESTE filtrul pe user
    # (id-urile altui user pica din intersectie). Absent/gol -> feedul filtrat curent.
    id_list = parse_id_csv(ids)
    if id_list:
        q = q.filter(RadarListing.id.in_(id_list))
    items = q.order_by(RadarListing.found_at.desc()).limit(5000).all()
    kw_ids = {it.keyword_id for it in items}
    keywords = (
        {k.id: k for k in db.query(RadarKeyword).filter(RadarKeyword.id.in_(kw_ids)).all()}
        if kw_ids else {}
    )
    rows = [_listing_to_dict(it, keywords.get(it.keyword_id)) for it in items]
    xlsx_bytes = build_listings_xlsx(rows)
    filename = f"radar_dealuri_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/listings/{listing_id}")
def get_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()
    return _listing_to_dict(listing, keyword)


# RP-1 — single-flight pentru enrichment-ul on-demand Vinted: al doilea request
# pentru acelasi listing in timp ce primul ruleaza primeste imediat un raspuns
# "in curs" (fara fetch dublu / hammering pe pagina HTML).
_vinted_detail_inflight: set = set()
_vinted_detail_lock = threading.Lock()


@router.get("/listings/{listing_id}/vinted-detail")
def get_vinted_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Îmbogățește on-demand un anunț Vinted cu poze/descriere/dată/atribute/vânzător
    complete (pagina HTML), o singură dată per anunț (rezultat cache-uit în DB)."""
    from app.services.radar.vinted_scraper import get_vinted_item_detail, apply_vinted_detail
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()
    if listing.platform != "vinted":
        return _listing_to_dict(listing, keyword)

    if not listing.vinted_detail_fetched:
        # Single-flight: daca deja se imbogateste acest listing, raspunde "in curs".
        with _vinted_detail_lock:
            already = listing_id in _vinted_detail_inflight
            if not already:
                _vinted_detail_inflight.add(listing_id)
        if already:
            resp = _listing_to_dict(listing, keyword)
            resp["enrichment_in_progress"] = True
            return resp
        try:
            item_id = (listing.external_id or "").replace("vinted_", "", 1)
            detail = get_vinted_item_detail(item_id) if item_id else None
            if detail:
                # Persista poze/descriere/data/atribute/vanzator + recalculeaza risc.
                # La esec (403/None) NU marcam fetched -> reincercare data viitoare.
                apply_vinted_detail(listing, detail, keyword.resale_price if keyword else None)
                db.commit()
                db.refresh(listing)
        finally:
            with _vinted_detail_lock:
                _vinted_detail_inflight.discard(listing_id)

    return _listing_to_dict(listing, keyword)


# ── RP-2: arbore dinamic de categorii Vinted ────────────────────────────────────
@router.get("/vinted-catalogs")
def list_vinted_catalogs(
    parent_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copiii unui nod de catalog Vinted (parent_id gol = rădăcini)."""
    from app.services.radar.vinted_catalog_service import get_children
    return get_children(db, parent_id)


@router.get("/vinted-catalogs/search")
def search_vinted_catalogs(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Max 20 potriviri pe `path`, diacritics-insensitive."""
    from app.services.radar.vinted_catalog_service import search_catalogs
    return search_catalogs(db, q)


class ExclusionTestBody(BaseModel):
    title: str
    description: Optional[str] = None


@router.post("/keywords/{keyword_id}/test-exclusion")
def test_keyword_exclusion(
    keyword_id: int,
    body: ExclusionTestBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """RP-2 — tester de excluderi pe configurația keyword-ului (ambele moduri)."""
    kw = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.id == keyword_id, RadarKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword-ul nu a fost găsit.")

    mode = getattr(kw, "exclude_matching_mode", "simple") or "simple"
    exclude_words = _parse_json_list(kw.exclude_words)
    desc_raw = kw.exclude_description_words
    desc_words = desc_raw if isinstance(desc_raw, list) else _parse_json_list(desc_raw)

    if mode == "advanced":
        from app.services.radar.exclusion_engine import check_exclusion
        exceptions = _parse_json_list(getattr(kw, "exclude_exceptions", None))
        excluded, rule = check_exclusion(body.title, body.description, exclude_words, desc_words, exceptions)
    else:
        # Modul simplu = logica veche (is_excluded, substring case-insensitive pe titlu).
        from app.services.radar.base_scraper import is_excluded
        excluded, rule = False, None
        if is_excluded(body.title, exclude_words):
            excluded = True
            w = next((x for x in exclude_words if x and x.lower() in (body.title or "").lower()), None)
            rule = f'„{w}" (în titlu)'
        elif body.description and is_excluded(body.description, desc_words):
            excluded = True
            w = next((x for x in desc_words if x and x.lower() in (body.description or "").lower()), None)
            rule = f'„{w}" (în descriere)'

    return {"excluded": excluded, "matched_rule": rule, "mode": mode}


@router.get("/listings/{listing_id}/facebook-detail")
def get_facebook_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Îmbogățește on-demand un anunț Facebook cu descriere + galerie completă,
    o singură dată per anunț (rezultat cache-uit în DB)."""
    from app.services.radar.facebook_scraper import fetch_facebook_listing_detail
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    if listing.platform != "facebook":
        keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()
        return _listing_to_dict(listing, keyword)

    if not listing.facebook_detail_fetched:
        settings = _get_or_create_settings(db, current_user.id)
        detail = fetch_facebook_listing_detail(listing.url, settings.facebook_session_path)
        if detail and (detail.get("description") or detail.get("images")):
            if detail.get("images"):
                listing.images = json.dumps(detail["images"], ensure_ascii=False)
            if detail.get("description"):
                listing.description = detail["description"]
            # Marcam fetched=True DOAR la succes (am primit descriere si/sau galerie).
            # La esec (fetch esuat/gol, detail fara continut) lasam flag-ul False
            # intentionat, ca sa reincercam data viitoare cand redeschizi anuntul.
            listing.facebook_detail_fetched = True
            db.commit()
            db.refresh(listing)

    keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()
    return _listing_to_dict(listing, keyword)


@router.get("/listings/{listing_id}/ai-review")
def generate_listing_ai_review(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genereaza on-demand un AI review pentru un listing (daca lipseste sau userul vrea refresh)."""
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    # PARTEA B — nu genera review nou daca userul a dezactivat "Review AI în feed".
    if (current_user.ai_features_config or {}).get("ai_radar_review") is False:
        raise HTTPException(
            status_code=403,
            detail="Review-ul AI este dezactivat din Setări (Review AI în feed).",
        )
    keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()
    resale = keyword.resale_price if keyword else 0
    review = generate_ai_review(
        title=listing.title,
        description=listing.description,
        price=listing.price,
        resale_price=resale,
        platform=listing.platform,
        score=listing.score,
    )
    if not review:
        raise HTTPException(status_code=502, detail="Nu am putut genera review-ul AI. Încearcă din nou.")
    listing.ai_review = review
    db.commit()
    return {"ai_review": review}


@router.patch("/listings/{listing_id}/status")
def update_listing_status(
    listing_id: int,
    data: ListingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.status not in ("active", "saved", "ignored", "sold", "removed"):
        raise HTTPException(status_code=400, detail="Status invalid.")
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    listing.status = data.status
    db.commit()
    return {"id": listing.id, "status": listing.status}


@router.delete("/listings/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(RadarListing).filter(
        RadarListing.id == listing_id,
        RadarListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    db.delete(listing)
    db.commit()
    return {"message": "Anunț șters.", "id": listing_id}


# ──────────────────────────────────────────────────────────────────────────────
# MANUAL SEARCH (cautare live, fara salvare in DB)
# ──────────────────────────────────────────────────────────────────────────────


# MODIFICARE 18 — impactul stergerii unui keyword (cate listinguri sunt asociate).
# RadarSeenId nu e legat de keyword (e global pe user+platforma), deci seen_count=0.
@router.get("/keywords/{keyword_id}/impact")
def get_keyword_impact(
    keyword_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_count = db.query(func.count(RadarListing.id)).filter(
        RadarListing.keyword_id == keyword_id,
        RadarListing.user_id == current_user.id,
    ).scalar() or 0
    return {"listing_count": listing_count, "seen_count": 0}


@router.post("/search-manual")
@limiter.limit("5/minute")
def search_manual(
    request: Request,
    data: ManualSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cautare live pe platformele alese, fara a salva nimic in baza de date.

    Apeleaza scraperele direct, in paralel, si calculeaza margin_pct cu aceeasi
    logica de scor (calculate_score) folosita de radar_scanner. Pretul maxim tine
    loc de pret de revanzare pentru estimarea marjei.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from app.services.radar.autovit_scraper import search_autovit
    from app.services.radar.facebook_scraper import search_facebook
    from app.services.radar.lajumate_scraper import search_lajumate
    from app.services.radar.mobilede_scraper import search_mobilede
    from app.services.radar.okazii_scraper import search_okazii
    from app.services.radar.olx_scraper import search_olx
    from app.services.radar.publi24_scraper import search_publi24
    from app.services.radar.vinted_scraper import search_vinted

    keyword = (data.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword-ul este obligatoriu.")
    if data.max_price is None or data.max_price <= 0:
        raise HTTPException(status_code=400, detail="Prețul maxim trebuie să fie pozitiv.")
    if data.platform:
        platforms = [data.platform.lower()]
    else:
        platforms = [(p or "").lower() for p in (data.platforms or []) if p]
    if not platforms:
        raise HTTPException(status_code=400, detail="Selectează cel puțin o platformă.")

    settings = _get_or_create_settings(db, current_user.id)
    exclude_words = data.exclude_words or []
    max_price = float(data.max_price)
    min_price = data.min_price

    def _run(platform: str) -> list[dict]:
        try:
            if platform == "olx":
                return search_olx(keyword=keyword, max_price=max_price, condition="all",
                                  exclude_words=exclude_words, min_price=min_price, category=data.category)
            if platform == "vinted":
                return search_vinted(keyword=keyword, max_price=max_price, condition="all",
                                     exclude_words=exclude_words,
                                     min_price=min_price, category=data.category)
            if platform == "okazii":
                return search_okazii(keyword=keyword, max_price=max_price, condition="all",
                                     exclude_words=exclude_words, min_price=min_price, category=data.category)
            if platform == "facebook":
                return search_facebook(keyword=keyword, max_price=max_price, judet=None, oras=None,
                                       exclude_words=exclude_words, session_path=settings.facebook_session_path,
                                       min_price=min_price, category=data.category)
            if platform == "lajumate":
                return search_lajumate(keyword=keyword, max_price=max_price, min_price=min_price,
                                       condition="all", exclude_words=exclude_words, judet=None, oras=None)
            if platform == "publi24":
                return search_publi24(keyword=keyword, max_price=max_price, min_price=min_price,
                                      condition="all", exclude_words=exclude_words, judet=None, oras=None)
            if platform == "autovit":
                return search_autovit(keyword=keyword, max_price=max_price, min_price=min_price,
                                      exclude_words=exclude_words, car_filters=None)
            if platform == "mobilede":
                return search_mobilede(keyword=keyword, max_price=max_price, min_price=min_price,
                                       exclude_words=exclude_words, car_filters=None)
        except Exception as exc:
            print(f"[RadarManualSearch] Scraperul {platform} a crapat: {exc}")
        return []

    # MON-4 — jurnalele scraperelor (emise din workerii executorului) apartin user-ului
    # care a cerut cautarea; workerii NU mostenesc contextul, deci il copiem explicit.
    set_log_user(current_user.id)
    _ctx = contextvars.copy_context()
    combined: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(platforms), 6)) as executor:
        future_map = {executor.submit(_ctx.run, _run, p): p for p in platforms}
        for future in as_completed(future_map):
            platform = future_map[future]
            try:
                rows = future.result() or []
            except Exception as exc:
                print(f"[RadarManualSearch] {platform} a esuat: {exc}")
                rows = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                price = float(r.get("price") or 0)
                score_data = calculate_score(
                    listing_price=price,
                    resale_price=max_price,
                    min_margin_pct=0,
                )
                combined.append({
                    "title": r.get("title"),
                    "price": price,
                    "currency": r.get("currency") or "RON",
                    "platform": r.get("platform") or platform,
                    "url": r.get("url"),
                    "images": r.get("images") or [],
                    "location": r.get("location"),
                    "condition": r.get("condition"),
                    "margin_pct": round(score_data.get("margin_pct") or 0, 1),
                })

    set_log_user(None)  # MON-4 — curatam contextul pe thread-ul de request (pooled)
    return combined


# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_or_create_settings(db, current_user.id)
    return _settings_to_dict(s)


@router.put("/settings")
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_or_create_settings(db, current_user.id)
    if data.discord_webhook_all is not None:
        s.discord_webhook_all = data.discord_webhook_all or None
    if data.discord_webhook_buy_now is not None:
        s.discord_webhook_buy_now = data.discord_webhook_buy_now or None
    if data.discord_webhook_maybe is not None:
        s.discord_webhook_maybe = data.discord_webhook_maybe or None
    if data.discord_webhook_auto is not None:
        s.discord_webhook_auto = data.discord_webhook_auto or None
    if data.discord_webhook_auto_all is not None:
        s.discord_webhook_auto_all = data.discord_webhook_auto_all or None
    if data.discord_webhook_auto_b is not None:
        s.discord_webhook_auto_b = data.discord_webhook_auto_b or None
    if data.discord_webhook_imob_all is not None:
        s.discord_webhook_imob_all = data.discord_webhook_imob_all or None
    if data.discord_webhook_imob_a is not None:
        s.discord_webhook_imob_a = data.discord_webhook_imob_a or None
    if data.discord_webhook_imob_b is not None:
        s.discord_webhook_imob_b = data.discord_webhook_imob_b or None
    if data.discord_webhook_alerts is not None:
        s.discord_webhook_alerts = data.discord_webhook_alerts or None
    if data.discord_here_radar is not None:
        s.discord_here_radar = bool(data.discord_here_radar)
    if data.discord_here_auto is not None:
        s.discord_here_auto = bool(data.discord_here_auto)
    if data.discord_here_imob is not None:
        s.discord_here_imob = bool(data.discord_here_imob)
    if data.custom_zone_aliases is not None:
        s.custom_zone_aliases = data.custom_zone_aliases
    if data.platform_olx_enabled is not None:
        s.platform_olx_enabled = bool(data.platform_olx_enabled)
    if data.platform_vinted_enabled is not None:
        s.platform_vinted_enabled = bool(data.platform_vinted_enabled)
    if data.platform_okazii_enabled is not None:
        s.platform_okazii_enabled = bool(data.platform_okazii_enabled)
    if data.platform_facebook_enabled is not None:
        s.platform_facebook_enabled = bool(data.platform_facebook_enabled)
    if data.platform_lajumate_enabled is not None:
        s.platform_lajumate_enabled = bool(data.platform_lajumate_enabled)
    if data.platform_publi24_enabled is not None:
        s.platform_publi24_enabled = bool(data.platform_publi24_enabled)
    if data.platform_autovit_enabled is not None:
        s.platform_autovit_enabled = bool(data.platform_autovit_enabled)
    if data.platform_mobilede_enabled is not None:
        s.platform_mobilede_enabled = bool(data.platform_mobilede_enabled)
    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return _settings_to_dict(s)


@router.post("/settings/test-discord")
def test_discord_webhook(
    data: DiscordTestRequest,
    current_user: User = Depends(get_current_user),
):
    if not data.webhook_url:
        raise HTTPException(status_code=400, detail="URL-ul webhook-ului este obligatoriu.")
    ok = send_test_message(data.webhook_url)
    if not ok:
        raise HTTPException(status_code=502, detail="Nu am putut trimite mesajul de test. Verifică URL-ul.")
    return {"message": "Mesaj de test trimis cu succes."}


# ──────────────────────────────────────────────────────────────────────────────
# FACEBOOK AUTH
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/facebook/status")
def facebook_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import time
    s = _get_or_create_settings(db, current_user.id)
    path = s.facebook_session_path or _default_facebook_session_path(current_user.id)
    valid = is_facebook_session_valid(path)
    exists = bool(path) and os.path.isfile(path)
    if valid:
        status = "active"
    elif exists:
        status = "expired"   # fisier prezent dar invalid: prea vechi (>30 zile) sau fara c_user
    else:
        status = "missing"
    age_hours = round((time.time() - os.path.getmtime(path)) / 3600, 1) if exists else None
    return {"valid": valid, "status": status, "age_hours": age_hours}


@router.post("/facebook/connect")
def facebook_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_or_create_settings(db, current_user.id)
    path = s.facebook_session_path or _default_facebook_session_path(current_user.id)
    s.facebook_session_path = path
    db.commit()

    def _bg():
        set_log_user(current_user.id)  # MON-4 — jurnalele conectarii FB apartin acestui user
        try:
            start_facebook_login_session(path)
        except Exception as exc:
            print(f"[RadarFacebook] connect bg eroare: {exc}")

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return {
        "status": "connecting",
        "message": "Deschide browserul și loghează-te în Facebook în fereastra care apare. Sesiunea se salvează automat.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# STATS
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/stats")
def radar_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = (
        db.query(func.count(RadarListing.id))
        .filter(RadarListing.user_id == current_user.id)
        .scalar() or 0
    )
    by_score_rows = (
        db.query(RadarListing.score, func.count(RadarListing.id))
        .filter(RadarListing.user_id == current_user.id)
        .group_by(RadarListing.score)
        .all()
    )
    by_score = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s, c in by_score_rows:
        if s in by_score:
            by_score[s] = int(c)

    saved = (
        db.query(func.count(RadarListing.id))
        .filter(RadarListing.user_id == current_user.id, RadarListing.status == "saved")
        .scalar() or 0
    )

    top_kw_rows = (
        db.query(RadarKeyword.id, RadarKeyword.name, func.count(RadarListing.id).label("cnt"))
        .join(RadarListing, RadarListing.keyword_id == RadarKeyword.id)
        .filter(RadarKeyword.user_id == current_user.id)
        .group_by(RadarKeyword.id, RadarKeyword.name)
        .order_by(func.count(RadarListing.id).desc())
        .limit(5)
        .all()
    )
    top_keywords = [
        {"id": r[0], "name": r[1], "count": int(r[2])} for r in top_kw_rows
    ]

    active_keywords = (
        db.query(func.count(RadarKeyword.id))
        .filter(RadarKeyword.user_id == current_user.id, RadarKeyword.is_active == True)
        .scalar() or 0
    )

    return {
        "total_listings_found": int(total),
        "listings_by_score": by_score,
        "active_keywords": int(active_keywords),
        "listings_saved": int(saved),
        "listings_acted_on": int(saved),
        "top_keywords": top_keywords,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SCAN NOW (manual, scopat per-user)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/scan-now")
@limiter.limit("5/minute")
def radar_scan_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pornește o scanare imediată DOAR pentru keyword-urile active ale userului curent.

    Spre deosebire de run_radar_scan() (care iterează toți userii), aici apelăm
    _scan_user(db, user) — deja scopat per-user — evitând bug-ul din Auto Anunțuri.
    Reîncărcăm userul în sesiunea nouă a thread-ului ca să evităm DetachedInstanceError
    (sesiunea request-ului se închide, iar _scan_user citește user.email la alerte).
    """
    from app.database import SessionLocal
    from app.utils.radar_scanner import _scan_user

    user_id = current_user.id

    def _background_scan():
        set_log_user(user_id)  # MON-4 — jurnalele scanului manual apartin acestui user
        _db = SessionLocal()
        try:
            _user = _db.query(User).filter(User.id == user_id).first()
            if _user:
                _scan_user(_db, _user)
        except Exception as exc:
            print(f"[RadarScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    thread = threading.Thread(target=_background_scan, daemon=True)
    thread.start()
    return {"ok": True, "message": "Scanare pornită în background."}


# ──────────────────────────────────────────────────────────────────────────────
# PROXY (.env management)
# ──────────────────────────────────────────────────────────────────────────────


def _env_file_path() -> str:
    """Calea catre fisierul .env (root-ul backend-ului)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def _read_env_lines() -> list[str]:
    path = _env_file_path()
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def _write_env_lines(lines: list[str]) -> None:
    path = _env_file_path()
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


_PROXY_VARS = ["PROXY_ENABLED", "PROXY_HOST", "PROXY_PORT", "PROXY_USER", "PROXY_PASS"]


@router.get("/settings/proxy")
def get_proxy_settings(current_user: User = Depends(get_current_user)):
    """Returneaza configuratia proxy citita din .env / variabilele de mediu."""
    return {
        "enabled": os.environ.get("PROXY_ENABLED", "false").lower() in ("1", "true", "yes"),
        "host": os.environ.get("PROXY_HOST", ""),
        "port": os.environ.get("PROXY_PORT", ""),
        "username": os.environ.get("PROXY_USER", ""),
        # parola nu o expunem inapoi in UI ca sa nu fie scursa accidental
        "password": "",
        "password_set": bool(os.environ.get("PROXY_PASS", "")),
    }


@router.put("/settings/proxy")
def update_proxy_settings(
    cfg: ProxyConfig,
    current_user: User = Depends(get_current_user),
):
    """Rescrie liniile PROXY_* din .env (creandu-le daca lipsesc).

    Doar admin-ii ar trebui sa modifice asta in productie — pentru moment
    permite oricarui user logat ca radar e per-user; daca admin-ul vrea
    restrictionare poate adauga is_admin guard ulterior.
    """
    new_values = {
        "PROXY_ENABLED": "true" if cfg.enabled else "false",
        "PROXY_HOST": cfg.host or "",
        "PROXY_PORT": cfg.port or "",
        "PROXY_USER": cfg.username or "",
    }
    # Daca a fost transmisa parola noua (string non-gol) o actualizam;
    # daca a venit goala pastram pe cea existenta ca sa nu sterga useri din greseala.
    if cfg.password:
        new_values["PROXY_PASS"] = cfg.password

    lines = _read_env_lines()
    seen = set()
    out = []
    for ln in lines:
        match = re.match(r"^([A-Z_]+)=", ln)
        if match and match.group(1) in new_values:
            key = match.group(1)
            out.append(f"{key}={new_values[key]}\n")
            seen.add(key)
        else:
            out.append(ln)
    for key, value in new_values.items():
        if key not in seen:
            if out and not out[-1].endswith("\n"):
                out[-1] = out[-1] + "\n"
            out.append(f"{key}={value}\n")
    _write_env_lines(out)

    # Sincronizeaza si os.environ ca scraperele sa vada imediat noile valori
    # fara restart.
    for key, value in new_values.items():
        os.environ[key] = value

    return {"message": "Configurația proxy a fost salvată."}


# ──────────────────────────────────────────────────────────────────────────────
# MESSAGE TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────


_DEFAULT_TEMPLATES = [
    ("Interes general (OLX)", "olx",
     "Bună ziua! Sunt interesat de {titlu}. Este încă disponibil? "
     "Puteți face {pret_oferit} RON? Mulțumesc!"),
    ("Ofertă directă (OLX)", "olx",
     "Bună! Văd că vindeți {titlu} la {pret_cerut} RON. "
     "Vă ofer {pret_oferit} RON cash, ridicare imediată. Mergeți?"),
    ("Vinted casual", "vinted",
     "Salut! Mă interesează {titlu}. Faci {pret_oferit}?"),
    ("Universal", "all",
     "Bună ziua, sunt interesat de {titlu}. Este disponibil?"),
]


def _ensure_default_templates(db: Session, user_id: int) -> None:
    """La primul acces, populeaza userul cu sabloanele default."""
    existing = db.query(RadarMessageTemplate).filter(RadarMessageTemplate.user_id == user_id).first()
    if existing:
        return
    for name, platform, text in _DEFAULT_TEMPLATES:
        db.add(RadarMessageTemplate(
            user_id=user_id,
            name=name,
            platform=platform,
            template_text=text,
            is_default=True,
        ))
    db.commit()


def _template_to_dict(t: RadarMessageTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "platform": t.platform,
        "template_text": t.template_text,
        "is_default": t.is_default,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/templates")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_default_templates(db, current_user.id)
    rows = (
        db.query(RadarMessageTemplate)
        .filter(RadarMessageTemplate.user_id == current_user.id)
        .order_by(RadarMessageTemplate.created_at.asc())
        .all()
    )
    return [_template_to_dict(t) for t in rows]


@router.post("/templates")
def create_template(
    data: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not data.name.strip() or not data.template_text.strip():
        raise HTTPException(status_code=400, detail="Numele și textul șablonului sunt obligatorii.")
    t = RadarMessageTemplate(
        user_id=current_user.id,
        name=data.name.strip(),
        platform=(data.platform or "all").lower(),
        template_text=data.template_text,
        is_default=bool(data.is_default),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _template_to_dict(t)


@router.put("/templates/{template_id}")
def update_template(
    template_id: int,
    data: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(RadarMessageTemplate).filter(
        RadarMessageTemplate.id == template_id,
        RadarMessageTemplate.user_id == current_user.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Șablonul nu a fost găsit.")
    if data.name is not None:
        t.name = data.name.strip()
    if data.platform is not None:
        t.platform = data.platform.lower()
    if data.template_text is not None:
        t.template_text = data.template_text
    if data.is_default is not None:
        t.is_default = bool(data.is_default)
    db.commit()
    db.refresh(t)
    return _template_to_dict(t)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(RadarMessageTemplate).filter(
        RadarMessageTemplate.id == template_id,
        RadarMessageTemplate.user_id == current_user.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Șablonul nu a fost găsit.")
    db.delete(t)
    db.commit()
    return {"message": "Șablon șters."}


_PLATFORM_NICE = {"olx": "OLX", "vinted": "Vinted", "okazii": "Okazii", "facebook": "Facebook Marketplace"}


@router.post("/templates/{template_id}/render")
def render_template(
    template_id: int,
    payload: TemplateRender,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Inlocuieste placeholder-ele cu datele unui listing al userului."""
    t = db.query(RadarMessageTemplate).filter(
        RadarMessageTemplate.id == template_id,
        RadarMessageTemplate.user_id == current_user.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Șablonul nu a fost găsit.")
    listing = (
        db.query(RadarListing)
        .filter(RadarListing.id == payload.listing_id, RadarListing.user_id == current_user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    keyword = db.query(RadarKeyword).filter(RadarKeyword.id == listing.keyword_id).first()

    if payload.pret_oferit is not None and payload.pret_oferit > 0:
        pret_oferit = float(payload.pret_oferit)
    elif keyword and keyword.max_price:
        pret_oferit = float(keyword.max_price)
    else:
        pret_oferit = round(float(listing.price) * 0.9, 2)

    rendered = t.template_text
    rendered = rendered.replace("{titlu}", listing.title or "")
    rendered = rendered.replace("{pret_cerut}", f"{int(round(listing.price))}")
    rendered = rendered.replace("{pret_oferit}", f"{int(round(pret_oferit))}")
    rendered = rendered.replace("{platforma}", _PLATFORM_NICE.get(listing.platform, listing.platform or ""))
    return {
        "template_id": t.id,
        "listing_id": listing.id,
        "rendered_text": rendered,
        "pret_oferit": pret_oferit,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BULK ACTIONS
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/listings/bulk-action")
def bulk_listing_action(
    data: BulkAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.action not in ("saved", "ignored", "sold", "deleted"):
        raise HTTPException(status_code=400, detail="Acțiune invalidă.")
    if not data.listing_ids:
        return {"updated": 0, "action": data.action, "message": "Niciun listing selectat."}

    if data.action == "deleted":
        updated = (
            db.query(RadarListing)
            .filter(
                RadarListing.user_id == current_user.id,
                RadarListing.id.in_(data.listing_ids),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return {
            "updated": int(updated),
            "action": "deleted",
            "message": f"{updated} listinguri șterse definitiv.",
        }

    updated = (
        db.query(RadarListing)
        .filter(
            RadarListing.user_id == current_user.id,
            RadarListing.id.in_(data.listing_ids),
        )
        .update({RadarListing.status: data.action}, synchronize_session=False)
    )
    db.commit()
    return {
        "updated": int(updated),
        "action": data.action,
        "message": f"{updated} listinguri actualizate ({data.action}).",
    }


# ──────────────────────────────────────────────────────────────────────────────
# PRICE TREND PER KEYWORD
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/keywords/{keyword_id}/price-trend")
def keyword_price_trend(
    keyword_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = (
        db.query(RadarKeyword)
        .filter(RadarKeyword.id == keyword_id, RadarKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword-ul nu a fost găsit.")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            cast(RadarListing.found_at, Date).label("day"),
            func.avg(RadarListing.price).label("avg_p"),
            func.min(RadarListing.price).label("min_p"),
            func.max(RadarListing.price).label("max_p"),
            func.count(RadarListing.id).label("cnt"),
        )
        .filter(
            RadarListing.user_id == current_user.id,
            RadarListing.keyword_id == keyword_id,
            RadarListing.found_at >= since,
        )
        .group_by(cast(RadarListing.found_at, Date))
        .order_by(cast(RadarListing.found_at, Date).asc())
        .all()
    )
    series = []
    all_prices = []
    for r in rows:
        avg_p = float(r.avg_p or 0)
        min_p = float(r.min_p or 0)
        max_p = float(r.max_p or 0)
        all_prices.append(avg_p)
        series.append({
            "date": r.day.isoformat() if r.day else None,
            "avg_price": round(avg_p, 2),
            "min_price": round(min_p, 2),
            "max_price": round(max_p, 2),
            "count": int(r.cnt or 0),
        })

    overall_avg = round(sum(all_prices) / len(all_prices), 2) if all_prices else 0
    overall_min = round(min(all_prices), 2) if all_prices else 0
    overall_max = round(max(all_prices), 2) if all_prices else 0

    # Trend direction — compara primele 7 zile cu ultimele 7
    trend = "stabil"
    if len(series) >= 4:
        head = [s["avg_price"] for s in series[: max(1, len(series) // 2)]]
        tail = [s["avg_price"] for s in series[-max(1, len(series) // 2):]]
        if head and tail:
            head_avg = sum(head) / len(head)
            tail_avg = sum(tail) / len(tail)
            if head_avg > 0:
                pct = (tail_avg - head_avg) / head_avg * 100
                if pct > 5:
                    trend = "crescator"
                elif pct < -5:
                    trend = "descrescator"

    return {
        "keyword_id": kw.id,
        "keyword_name": kw.name,
        "max_price_target": kw.max_price,
        "resale_price_target": kw.resale_price,
        "days": days,
        "series": series,
        "overall_avg": overall_avg,
        "overall_min": overall_min,
        "overall_max": overall_max,
        "trend_direction": trend,
    }


# ──────────────────────────────────────────────────────────────────────────────
# WEB PUSH
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/push/vapid-public-key")
def get_vapid_public_key(current_user: User = Depends(get_current_user)):
    return {"public_key": VAPID_PUBLIC_KEY, "configured": bool(VAPID_PUBLIC_KEY)}


@router.post("/push/subscribe")
def push_subscribe(
    data: PushSubscribe,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(PushSubscription).filter(
        PushSubscription.user_id == current_user.id,
        PushSubscription.endpoint == data.endpoint,
    ).first()
    if existing:
        existing.p256dh = data.p256dh
        existing.auth = data.auth
        existing.user_agent = data.user_agent
        db.commit()
        return {"message": "Subscription actualizat.", "id": existing.id}
    sub = PushSubscription(
        user_id=current_user.id,
        endpoint=data.endpoint,
        p256dh=data.p256dh,
        auth=data.auth,
        user_agent=data.user_agent,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"message": "Notificările push sunt active.", "id": sub.id}


@router.delete("/push/unsubscribe")
def push_unsubscribe(
    endpoint: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(PushSubscription).filter(PushSubscription.user_id == current_user.id)
    if endpoint:
        q = q.filter(PushSubscription.endpoint == endpoint)
    count = q.delete(synchronize_session=False)
    db.commit()
    return {"message": f"{count} subscription(s) șterse."}


@router.get("/push/status")
def push_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(func.count(PushSubscription.id)).filter(PushSubscription.user_id == current_user.id).scalar() or 0
    return {
        "subscribed": int(total) > 0,
        "subscriptions_count": int(total),
        "configured": bool(VAPID_PUBLIC_KEY),
    }
