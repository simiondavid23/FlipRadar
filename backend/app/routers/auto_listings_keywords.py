import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.auto_keyword import AutoKeyword
from app.models.auto_feed_listing import AutoFeedListing
from app.services.auto_listings.excel_exporter import build_auto_xlsx
from app.services.bnr_exchange import get_eur_ron
from app.services.radar.ai_reviewer import generate_ai_review
from app.services.ai_service import AIConfigError
from app.models.radar_message_template import RadarMessageTemplate
from app.utils.auth import get_current_user
from app.utils.id_csv import parse_id_csv

router = APIRouter(prefix="/api/auto-listings", tags=["auto-listings"])


# ── Pydantic schemas ────────────────────────────────────────────

class KeywordCreate(BaseModel):
    name: str
    platform: str
    make: Optional[str] = None
    model: Optional[str] = None
    query: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    km_max: Optional[int] = None
    price_max: Optional[float] = None
    price_currency: Optional[str] = "EUR"
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    body_type: Optional[str] = None
    location: Optional[str] = None
    is_active: bool = True
    notify_email: bool = False
    notify_discord: bool = False
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    polling_interval_minutes: int = 10
    # Categorie per-platforma + filtre tehnice confirmate (JSON), populate de formularul
    # dinamic de keyword. Vezi AUTO_PLATFORM_CATEGORIES / AUTO_TECHNICAL_FIELDS.
    category: Optional[str] = None
    tech_filters: Optional[dict] = None
    # Gradare (marja fata de pretul de revanzare introdus manual) — identic cu Radar.
    # resale_price None => listingurile raman fara scor/grad.
    resale_price: Optional[float] = None
    resale_price_currency: Optional[str] = "EUR"
    min_margin_pct: Optional[float] = 10.0
    grade_a_min: Optional[float] = None
    grade_b_min: Optional[float] = None
    grade_c_min: Optional[float] = None

class KeywordUpdate(KeywordCreate):
    pass


def _kw_dict(kw: AutoKeyword) -> dict:
    return {c.name: getattr(kw, c.name)
            for c in kw.__table__.columns}


@router.get("/categories")
def get_auto_categories(current_user: User = Depends(get_current_user)):
    """Categorii + campuri tehnice confirmate per platforma (pentru formularul dinamic
    de keyword si tab-ul de cautare manuala). GET /api/auto-listings/categories.

    Necesita autentificare (AN-1): taxonomia e statica, dar toate celelalte
    endpointuri ale modulului cer autentificare — pastram politica uniforma.
    """
    from app.scrapers.auto.listings.auto_categories import (
        AUTO_PLATFORM_CATEGORIES, AUTO_TECHNICAL_FIELDS)
    return {"categories": AUTO_PLATFORM_CATEGORIES, "technical_fields": AUTO_TECHNICAL_FIELDS}


@router.get("/makes/mobile-de")
def get_mobile_de_makes(current_user: User = Depends(get_current_user)):
    """Marcile mapate pe ID-uri mobile.de (sursa unica de adevar: MOBILE_DE_MAKE_IDS din
    scraper) — pentru datalist-ul de sugestii din formularul de keyword. Read-only."""
    from app.scrapers.auto.listings.mobile_de_scraper import MOBILE_DE_MAKE_IDS
    return {"makes": sorted(MOBILE_DE_MAKE_IDS.keys())}


# ── Keywords CRUD ───────────────────────────────────────────────

@router.get("/keywords")
def list_keywords(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kws = db.query(AutoKeyword).filter(
        AutoKeyword.user_id == current_user.id
    ).order_by(AutoKeyword.created_at.desc()).all()
    return [_kw_dict(k) for k in kws]


@router.post("/keywords", status_code=201)
def create_keyword(
    payload: KeywordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = AutoKeyword(user_id=current_user.id, **payload.model_dump())
    db.add(kw); db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.put("/keywords/{kw_id}")
def update_keyword(
    kw_id: int,
    payload: KeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(AutoKeyword).filter(
        AutoKeyword.id == kw_id,
        AutoKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    # exclude_unset: update-urile partiale (ex. butonul de toggle activ/inactiv, care nu
    # trimite resale_price / praguri de grad) NU trebuie sa reseteze campurile netrimise.
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(kw, k, v)
    db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.delete("/keywords/{kw_id}")
def delete_keyword(
    kw_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(AutoKeyword).filter(
        AutoKeyword.id == kw_id,
        AutoKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    db.delete(kw); db.commit()
    return {"ok": True}


# ── Feed endpoints ───────────────────────────────────────────────

@router.get("/feed")
def get_feed(
    platform: Optional[str] = None,
    grade: Optional[str] = None,
    status: str = "active",
    keyword_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AutoFeedListing).filter(
        AutoFeedListing.user_id == current_user.id,
        AutoFeedListing.status == status,
    )
    if platform: q = q.filter(AutoFeedListing.platform == platform)
    if grade:    q = q.filter(AutoFeedListing.grade == grade)
    if keyword_id: q = q.filter(AutoFeedListing.keyword_id == keyword_id)
    total = q.count()
    items = q.order_by(AutoFeedListing.found_at.desc())\
             .offset(offset).limit(limit).all()
    eur_ron = get_eur_ron()
    def _d(l):
        d = {c.name: getattr(l, c.name) for c in l.__table__.columns}
        d["price"] = float(d["price"]) if d["price"] else None
        # Marja/revanzare — derivate din margin_value stocat (paritate cu Radar). resale_price
        # (RON) = pret_ron + marja; pct = marja/resale*100. Consistente intre ele; None cand
        # keyword-ul nu are resale (margin_value NULL) -> UI nu afiseaza nimic despre marja.
        mv = d.get("margin_value")
        d["margin_value"] = float(mv) if mv is not None else None
        if d["margin_value"] is not None and d["price"]:
            price_ron = d["price"] * (eur_ron if (d.get("currency") or "RON") == "EUR" else 1.0)
            resale_ron = price_ron + d["margin_value"]
            d["resale_price"] = round(resale_ron, 2)
            d["margin_pct"] = round(d["margin_value"] / resale_ron * 100, 1) if resale_ron else None
        else:
            d["resale_price"] = None
            d["margin_pct"] = None
        return d
    return {"total": total, "items": [_d(i) for i in items]}


# Definit ÎNAINTE de /feed/{listing_id}/... ca "export" să nu fie prins de rutele cu param.
@router.get("/feed/export")
def export_feed(
    platform: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword_id: Optional[int] = Query(None),
    ids: Optional[str] = Query(None),  # CSV de id-uri — folosit de "Exporta selectia"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export .xlsx al feed-ului Auto — aceleași filtre ca lista (platform/grad/status/keyword)."""
    q = db.query(AutoFeedListing).filter(AutoFeedListing.user_id == current_user.id)
    if platform:
        q = q.filter(AutoFeedListing.platform == platform)
    if grade:
        q = q.filter(AutoFeedListing.grade == grade)
    if status and status != "all":
        q = q.filter(AutoFeedListing.status == status)
    if keyword_id:
        q = q.filter(AutoFeedListing.keyword_id == keyword_id)
    # "Exporta selectia" — filtreaza pe id-urile date (CSV tolerant), PESTE filtrul pe user.
    id_list = parse_id_csv(ids)
    if id_list:
        q = q.filter(AutoFeedListing.id.in_(id_list))
    items = q.order_by(AutoFeedListing.found_at.desc()).limit(5000).all()

    kw_ids = {i.keyword_id for i in items if i.keyword_id}
    kw_map = (
        {k.id: k.name for k in db.query(AutoKeyword).filter(AutoKeyword.id.in_(kw_ids)).all()}
        if kw_ids else {}
    )
    rows = [{
        "title": i.title, "platform": i.platform, "grade": i.grade,
        "price": float(i.price) if i.price is not None else None, "currency": i.currency,
        "year": i.year, "km": i.km, "fuel_type": i.fuel_type, "location": i.location,
        "seller_name": i.seller_name, "keyword_name": kw_map.get(i.keyword_id),
        "listed_at": i.listed_at, "found_at": i.found_at, "status": i.status, "url": i.url,
    } for i in items]

    xlsx_bytes = build_auto_xlsx(rows)
    filename = f"auto_anunturi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class BulkAction(BaseModel):
    listing_ids: list[int]
    action: str  # "saved" | "ignored" | "active" | "deleted"


# Definit ÎNAINTE de rutele parametrizate /feed/{listing_id}/... (același pattern ca /feed/export
# de mai sus și ca radar.py) ca "bulk-action" să nu fie prins drept listing_id.
@router.post("/feed/bulk-action")
def bulk_feed_action(
    data: BulkAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acțiuni în masă pe feed-ul Auto — mirror pe radar.py::bulk_listing_action, adaptat la
    AutoFeedListing. Toate query-urile sunt scopate pe user_id == current_user.id, deci un user
    nu poate atinge listingurile altuia nici cu ID-uri ghicite. "active" e în plus față de Radar:
    scoate în masă din Salvate/Ignorate înapoi în feed (statusuri deja folosite de update_listing_status).
    listing_ids gol → {"updated": 0, ...} fără eroare."""
    if data.action not in ("saved", "ignored", "active", "deleted"):
        raise HTTPException(status_code=400, detail="Acțiune invalidă.")
    if not data.listing_ids:
        return {"updated": 0, "action": data.action, "message": "Niciun listing selectat."}

    if data.action == "deleted":
        updated = (
            db.query(AutoFeedListing)
            .filter(
                AutoFeedListing.user_id == current_user.id,
                AutoFeedListing.id.in_(data.listing_ids),
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
        db.query(AutoFeedListing)
        .filter(
            AutoFeedListing.user_id == current_user.id,
            AutoFeedListing.id.in_(data.listing_ids),
        )
        .update({AutoFeedListing.status: data.action}, synchronize_session=False)
    )
    db.commit()
    return {
        "updated": int(updated),
        "action": data.action,
        "message": f"{updated} listinguri actualizate ({data.action}).",
    }


@router.patch("/feed/{listing_id}/status")
def update_listing_status(
    listing_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(AutoFeedListing).filter(
        AutoFeedListing.id == listing_id,
        AutoFeedListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    listing.status = payload.get("status", listing.status)
    db.commit()
    return {"ok": True}


def _latest_facebook_session():
    """Cea mai recenta sesiune Facebook salvata (acelasi pattern ca /stats)."""
    try:
        import glob, os
        files = glob.glob("data/facebook_session_*.json")
        return max(files, key=os.path.getmtime) if files else None
    except Exception:
        return None


@router.get("/feed/{listing_id}/detail")
def get_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Îmbogățește on-demand un anunț auto cu poze/descriere/vânzător/dată, o singură
    dată per anunț (rezultat cache-uit în DB). Mirror pe /listings/{id}/vinted-detail."""
    listing = db.query(AutoFeedListing).filter(
        AutoFeedListing.id == listing_id,
        AutoFeedListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Anunțul nu a fost găsit.")

    if not listing.detail_fetched:
        from app.scrapers.auto.listings.detail import DETAIL_FETCHERS
        fn = DETAIL_FETCHERS.get(listing.platform)
        detail = None
        if fn and listing.url:
            try:
                detail = (fn(listing.url, _latest_facebook_session())
                          if listing.platform == "facebook_auto" else fn(listing.url))
            except Exception as exc:
                print(f"[auto detail] {listing.platform} eroare: {exc}")
        # Succes = macar un camp util. Populam DOAR campurile nenule (nu suprascriem cu
        # None ce exista deja). detail_fetched=True DOAR la succes -> retry la esec (ca Vinted).
        if detail and any(detail.get(k) for k in ("images", "description", "seller_name", "listed_at")):
            if detail.get("images"):
                listing.images_json = detail["images"]
            if detail.get("description"):
                listing.description = detail["description"]
            if detail.get("seller_name"):
                listing.seller_name = detail["seller_name"]
            if detail.get("listed_at"):
                listing.listed_at = detail["listed_at"]
            listing.detail_fetched = True
            db.commit()
            db.refresh(listing)

    d = {c.name: getattr(listing, c.name) for c in listing.__table__.columns}
    d["price"] = float(d["price"]) if d["price"] else None
    return d


@router.post("/feed/{listing_id}/generate-review")
def generate_auto_ai_review(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Review AI on-demand pentru un anunt Auto — mirror pe radar.py::generate_listing_ai_review.
    Foloseste aceeasi functie generica generate_ai_review (kw.resale_price + listing.grade)."""
    listing = db.query(AutoFeedListing).filter(
        AutoFeedListing.id == listing_id,
        AutoFeedListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    if (current_user.ai_features_config or {}).get("ai_radar_review") is False:
        raise HTTPException(status_code=403, detail="Review-ul AI este dezactivat din Setări (Review AI în feed).")
    keyword = db.query(AutoKeyword).filter(AutoKeyword.id == listing.keyword_id).first()
    # Convertim AMBELE valori in RON (monede posibil diferite: listing.currency vs
    # keyword.resale_price_currency) INAINTE de review. generate_ai_review afiseaza "RON"
    # hardcodat, deci valorile trimise trebuie sa fie cu adevarat in RON. Functia ramane neatinsa.
    eur_ron = get_eur_ron()
    price = float(listing.price) if listing.price is not None else 0.0
    price_ron = price * eur_ron if (listing.currency or "RON").upper() == "EUR" else price
    resale_ron = 0.0
    if keyword and keyword.resale_price is not None:
        rp = float(keyword.resale_price)
        rp_cur = (getattr(keyword, "resale_price_currency", None) or "EUR").upper()
        resale_ron = rp * eur_ron if rp_cur == "EUR" else rp
    try:
        review = generate_ai_review(
            title=listing.title,
            description=listing.description,
            price=price_ron,
            resale_price=resale_ron,
            platform=listing.platform,
            score=listing.grade,
            location=listing.location,
            user=current_user,
        )
    except AIConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not review:
        raise HTTPException(status_code=502, detail="Nu am putut genera review-ul AI. Încearcă din nou.")
    listing.ai_review = review
    db.commit()
    return {"ai_review": review}


_AUTO_PLATFORM_NICE = {
    "autovit": "Autovit", "olx_auto": "OLX", "mobile_de": "Mobile.de",
    "autoscout24": "AutoScout24", "facebook_auto": "Facebook Marketplace",
    "kleinanzeigen_auto": "Kleinanzeigen",
}


class AutoTemplateRender(BaseModel):
    template_id: int
    pret_oferit: Optional[float] = None


@router.post("/feed/{listing_id}/render-template")
def render_auto_template(
    listing_id: int,
    payload: AutoTemplateRender,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Randare sablon mesaj pentru un anunt Auto — mirror pe radar.py::render_template,
    dar interogheaza AutoFeedListing in loc de RadarListing (sabloanele sunt partajate)."""
    t = db.query(RadarMessageTemplate).filter(
        RadarMessageTemplate.id == payload.template_id,
        RadarMessageTemplate.user_id == current_user.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Șablonul nu a fost găsit.")
    listing = db.query(AutoFeedListing).filter(
        AutoFeedListing.id == listing_id,
        AutoFeedListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Anunțul nu a fost găsit.")
    keyword = db.query(AutoKeyword).filter(AutoKeyword.id == listing.keyword_id).first()

    price = float(listing.price) if listing.price is not None else 0.0
    if payload.pret_oferit is not None and payload.pret_oferit > 0:
        pret_oferit = float(payload.pret_oferit)
    elif keyword and keyword.price_max:
        pret_oferit = float(keyword.price_max)
    else:
        pret_oferit = round(price * 0.9, 2)

    rendered = t.template_text
    rendered = rendered.replace("{titlu}", listing.title or "")
    rendered = rendered.replace("{pret_cerut}", f"{int(round(price))}")
    rendered = rendered.replace("{pret_oferit}", f"{int(round(pret_oferit))}")
    rendered = rendered.replace("{platforma}", _AUTO_PLATFORM_NICE.get(listing.platform, listing.platform or ""))
    return {
        "template_id": t.id,
        "listing_id": listing.id,
        "rendered_text": rendered,
        "pret_oferit": pret_oferit,
    }


@router.delete("/feed/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(AutoFeedListing).filter(
        AutoFeedListing.id == listing_id,
        AutoFeedListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    db.delete(listing); db.commit()
    return {"ok": True}


# MODIFICARE 18 — impactul stergerii unui keyword auto (listinguri asociate).
@router.get("/keywords/{keyword_id}/impact")
def get_keyword_impact(
    keyword_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_count = db.query(func.count(AutoFeedListing.id)).filter(
        AutoFeedListing.keyword_id == keyword_id,
        AutoFeedListing.user_id == current_user.id,
    ).scalar() or 0
    return {"listing_count": listing_count, "seen_count": 0}


@router.post("/scan-now")
@limiter.limit("5/minute")
def scan_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger immediate background scan for current user's active keywords."""
    import threading
    from app.database import SessionLocal
    from app.services.auto_listings_scanner import run_auto_scan
    from app.services.log_manager import set_log_user

    user_id = current_user.id

    def _background_scan():
        set_log_user(user_id)  # MON-4 — jurnalele scanului manual apartin acestui user
        _db = SessionLocal()
        try:
            run_auto_scan(_db, user_id=user_id)
        except Exception as exc:
            print(f"[AutoScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    thread = threading.Thread(target=_background_scan, daemon=True)
    thread.start()
    return {"ok": True, "message": "Scanare pornită în background."}


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func

    total = db.query(AutoFeedListing).filter(
        AutoFeedListing.user_id == current_user.id).count()
    by_grade = db.query(
        AutoFeedListing.grade, func.count(AutoFeedListing.id)
    ).filter(
        AutoFeedListing.user_id == current_user.id,
        AutoFeedListing.status == "active",
    ).group_by(AutoFeedListing.grade).all()
    kw_count = db.query(AutoKeyword).filter(
        AutoKeyword.user_id == current_user.id,
        AutoKeyword.is_active == True,
    ).count()

    # Status sesiune Facebook — doar daca exista keyword-uri facebook_auto active.
    has_fb_keyword = db.query(AutoKeyword).filter(
        AutoKeyword.user_id == current_user.id,
        AutoKeyword.is_active == True,
        AutoKeyword.platform == "facebook_auto",
    ).first() is not None

    fb_session_valid = None
    if has_fb_keyword:
        try:
            import glob, os
            files = glob.glob("data/facebook_session_*.json")
            session_path = max(files, key=os.path.getmtime) if files else None
            if session_path:
                from app.scrapers.auto.listings.facebook_auto_scraper import _is_session_valid
                fb_session_valid = _is_session_valid(session_path)
            else:
                fb_session_valid = False
        except Exception:
            fb_session_valid = False

    return {
        "total_listings": total,
        "active_keywords": kw_count,
        "by_grade": {g: c for g, c in by_grade},
        "facebook_session_valid": fb_session_valid,
        "has_facebook_keywords": has_fb_keyword,
    }
