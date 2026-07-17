import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.rate_limit import limiter
from app.database import get_db
from app.models.user import User
from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword as RealEstateKeyword
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing
from app.services.real_estate.excel_exporter import build_re_xlsx
from app.utils.auth import get_current_user
from app.utils.id_csv import parse_id_csv

router = APIRouter(prefix="/api/real-estate-monitor", tags=["real-estate-monitor"])


# ── Pydantic schemas ────────────────────────────────────────────

class KeywordCreate(BaseModel):
    name: str
    platform: str
    property_type: Optional[str] = None
    tip_anunt: Optional[str] = "vanzare"
    rooms: Optional[int] = None
    rooms_max: Optional[int] = None      # IMO-1 — plafon; rooms ramane minim
    area_min: Optional[int] = None
    area_max: Optional[int] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_currency: Optional[str] = "EUR"
    zone: Optional[str] = None
    city: Optional[str] = "București"
    floor_min: Optional[int] = None
    floor_max: Optional[int] = None
    furnished: Optional[bool] = None
    query: Optional[str] = None
    is_active: bool = True
    notify_email: bool = False
    notify_discord: bool = False
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    polling_interval_minutes: int = 30
    exclude_words: Optional[list[str]] = None   # termeni exclusi pe titlu+descriere (IM-6)

    @field_validator("rooms_max")
    @classmethod
    def _rooms_max_zero_e_null(cls, v):
        """IMO-1 — 0 (sau negativ) din formular = dezactivare explicita a plafonului -> NULL.
        Stocat ca 0, plafonul ar respinge TACIT orice anunt (orice camere > 0)."""
        return v if v and v > 0 else None


class KeywordUpdate(KeywordCreate):
    pass


def _kw_dict(kw: RealEstateKeyword) -> dict:
    return {c.name: getattr(kw, c.name) for c in kw.__table__.columns}


@router.get("/categories")
def get_re_categories():
    """Campuri tehnice + tipuri de proprietate confirmate per platforma (pentru formularul
    dinamic de keyword + tab-ul de cautare manuala). GET /api/real-estate-monitor/categories.

    Doar intrarile cu confirmed:True sunt de conectat; frontend-ul le foloseste ca sa stie ce
    filtre / tipuri de proprietate suporta fiecare platforma (ex. "comercial" e confirmat pe OLX,
    dar inca neconfirmat pe Storia/Imobiliare.ro — vezi RE_PROPERTY_TYPES).
    """
    from app.scrapers.real_estate.re_categories import RE_TECHNICAL_FIELDS, RE_PROPERTY_TYPES
    return {"technical_fields": RE_TECHNICAL_FIELDS, "property_types": RE_PROPERTY_TYPES}


# ── Keywords CRUD ───────────────────────────────────────────────

@router.get("/keywords")
def list_keywords(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kws = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id
    ).order_by(RealEstateKeyword.created_at.desc()).all()
    return [_kw_dict(k) for k in kws]


@router.post("/keywords", status_code=201)
def create_keyword(
    payload: KeywordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    data["exclude_words"] = data.get("exclude_words") or []   # JSON lista, nu NULL
    kw = RealEstateKeyword(user_id=current_user.id, **data)
    db.add(kw); db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.put("/keywords/{kw_id}")
def update_keyword(
    kw_id: int,
    payload: KeywordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.id == kw_id,
        RealEstateKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    data = payload.model_dump()
    data["exclude_words"] = data.get("exclude_words") or []   # JSON lista, nu NULL
    for k, v in data.items():
        setattr(kw, k, v)
    db.commit(); db.refresh(kw)
    return _kw_dict(kw)


@router.delete("/keywords/{kw_id}")
def delete_keyword(
    kw_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.id == kw_id,
        RealEstateKeyword.user_id == current_user.id,
    ).first()
    if not kw:
        raise HTTPException(404, "Keyword negăsit.")
    db.delete(kw); db.commit()
    return {"ok": True}


# ── Feed endpoints ───────────────────────────────────────────────

def _listing_dict(listing) -> dict:
    d = {c.name: getattr(listing, c.name) for c in listing.__table__.columns}
    d["price"] = float(d["price"]) if d["price"] is not None else None
    d["price_per_sqm"] = float(d["price_per_sqm"]) if d["price_per_sqm"] is not None else None
    return d


@router.get("/feed")
def get_feed(
    platform: Optional[str] = None,
    grade: Optional[str] = None,
    status: str = "active",
    zone: Optional[str] = None,
    city: Optional[str] = None,
    rooms: Optional[int] = None,
    keyword_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == status,
    )
    if platform: q = q.filter(RealEstateListing.platform == platform)
    if grade:    q = q.filter(RealEstateListing.grade == grade)
    if zone:     q = q.filter(RealEstateListing.zone_normalized == zone)
    if city:     q = q.filter(RealEstateListing.city == city)
    # Camere: optiunea de UI "4+ cam" trimite rooms=4 -> match >= (si 5+ camere apar);
    # 1..3 raman match EXACT.
    if rooms:
        q = q.filter(RealEstateListing.rooms >= rooms) if rooms >= 4 else q.filter(RealEstateListing.rooms == rooms)
    if keyword_id: q = q.filter(RealEstateListing.keyword_id == keyword_id)
    total = q.count()
    items = q.order_by(RealEstateListing.found_at.desc())\
             .offset(offset).limit(limit).all()
    return {"total": total, "items": [_listing_dict(i) for i in items]}


# Definit ÎNAINTE de /feed/{listing_id}/... ca "export" să nu fie prins de rutele cu param.
@router.get("/feed/export")
def export_feed(
    platform: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    rooms: Optional[int] = Query(None),
    keyword_id: Optional[int] = Query(None),
    ids: Optional[str] = Query(None),  # CSV de id-uri — folosit de "Exporta selectia"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export .xlsx al feed-ului Imobiliare — aceleasi filtre ca lista (platform/grad/status/
    keyword/oras/zona/camere), ca exportul sa reflecte exact feed-ul vizibil."""
    q = db.query(RealEstateListing).filter(RealEstateListing.user_id == current_user.id)
    if platform:
        q = q.filter(RealEstateListing.platform == platform)
    if grade:
        q = q.filter(RealEstateListing.grade == grade)
    if zone:
        q = q.filter(RealEstateListing.zone_normalized == zone)
    if city:
        q = q.filter(RealEstateListing.city == city)
    # Camere: aceeasi semantica 4+ ca la get_feed (rooms=4 -> >=; 1..3 exact).
    if rooms:
        q = q.filter(RealEstateListing.rooms >= rooms) if rooms >= 4 else q.filter(RealEstateListing.rooms == rooms)
    if keyword_id:
        q = q.filter(RealEstateListing.keyword_id == keyword_id)
    # "Exporta selectia" — filtreaza pe id-urile date (CSV tolerant), PESTE filtrul pe user
    # (id-urile altui user pica din intersectie). Selectia poate traversa statusuri, deci cand
    # exista ids NU aplicam filtrul de status; absent/gol -> feedul filtrat curent (cu status).
    id_list = parse_id_csv(ids)
    if id_list:
        q = q.filter(RealEstateListing.id.in_(id_list))
    elif status and status != "all":
        q = q.filter(RealEstateListing.status == status)
    items = q.order_by(RealEstateListing.found_at.desc()).limit(5000).all()

    kw_ids = {i.keyword_id for i in items if i.keyword_id}
    kw_map = (
        {k.id: k.name for k in db.query(RealEstateKeyword).filter(RealEstateKeyword.id.in_(kw_ids)).all()}
        if kw_ids else {}
    )
    rows = [{
        "title": i.title, "platform": i.platform, "grade": i.grade,
        "price": float(i.price) if i.price is not None else None, "currency": i.currency,
        "price_per_sqm": float(i.price_per_sqm) if i.price_per_sqm is not None else None,
        "rooms": i.rooms, "area_sqm": i.area_sqm,
        "zone_normalized": i.zone_normalized, "zone_raw": i.zone_raw, "floor": i.floor,
        "seller_id": i.seller_id, "keyword_name": kw_map.get(i.keyword_id),
        "found_at": i.found_at, "listed_at": i.listed_at, "status": i.status, "url": i.url,
    } for i in items]

    xlsx_bytes = build_re_xlsx(rows)
    filename = f"imobiliare_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Definit ÎNAINTE de rutele parametrizate /feed/{listing_id}/... (același pattern ca /feed/export)
# ca "filter-options" să nu fie prins drept listing_id.
@router.get("/feed/filter-options")
def get_feed_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Opțiuni pentru dropdown-urile de filtrare a feed-ului (zonă + oraș), DISTINCT pe datele
    userului. FĂRĂ filtrare pe status — dropdown-ul arată tot ce există în feed, indiferent de
    status. Sortare în Python (locale-independent, .lower()), nu ORDER BY dependent de collation."""
    zone_rows = db.query(RealEstateListing.zone_normalized).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.zone_normalized.isnot(None),
    ).distinct().all()
    city_rows = db.query(RealEstateListing.city).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.city.isnot(None),
    ).distinct().all()
    zones = sorted({r[0] for r in zone_rows}, key=lambda s: s.lower())
    cities = sorted({r[0] for r in city_rows}, key=lambda s: s.lower())
    return {"zones": zones, "cities": cities}


class BulkAction(BaseModel):
    listing_ids: list[int]
    action: str  # "saved" | "ignored" | "active" | "deleted"


# Definit ÎNAINTE de rutele parametrizate /feed/{listing_id}/... (același pattern ca /feed/export
# de mai sus și ca radar.py/auto) ca "bulk-action" să nu fie prins drept listing_id.
@router.post("/feed/bulk-action")
def bulk_feed_action(
    data: BulkAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acțiuni în masă pe feed-ul Imobiliare — mirror pe radar.py::bulk_listing_action / auto.
    Toate query-urile sunt scopate pe user_id == current_user.id, deci ID-urile altui user sunt
    IGNORATE silențios (nu 403, nu leak). "active" scoate în masă din Salvate/Ignorate înapoi în
    feed. "deleted" șterge FIZIC rândul (RE nu are status "deleted" — la fel ca DELETE /feed/{id}).
    listing_ids gol → {"updated": 0}. Commit o singură dată la final."""
    if data.action not in ("saved", "ignored", "active", "deleted"):
        raise HTTPException(status_code=400, detail="Acțiune invalidă.")
    if not data.listing_ids:
        return {"updated": 0, "message": "Niciun listing selectat."}

    rows = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.id.in_(data.listing_ids),
    ).all()
    n = len(rows)

    if data.action == "deleted":
        for row in rows:
            db.delete(row)   # ștergere fizică (RE nu are status "deleted")
        db.commit()
        return {"updated": n, "message": f"{n} listinguri șterse."}

    for row in rows:
        row.status = data.action
    db.commit()
    return {"updated": n, "message": f"{n} listinguri actualizate."}


@router.patch("/feed/{listing_id}/status")
def update_listing_status(
    listing_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(RealEstateListing).filter(
        RealEstateListing.id == listing_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    listing.status = payload.get("status", listing.status)
    db.commit()
    return {"ok": True}


@router.delete("/feed/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(RealEstateListing).filter(
        RealEstateListing.id == listing_id,
        RealEstateListing.user_id == current_user.id,
    ).first()
    if not listing:
        raise HTTPException(404, "Listing negăsit.")
    db.delete(listing); db.commit()
    return {"ok": True}


class ManualListingSave(BaseModel):
    # Cheile emise de make_re_listing (scraperele RE) — toate Optional in afara de platform.
    platform: str
    external_id: Optional[str] = None
    tip_anunt: Optional[str] = None
    tip_proprietate: Optional[str] = None
    camere: Optional[int] = None
    suprafata_mp: Optional[float] = None
    etaj: Optional[str] = None
    pret: Optional[float] = None
    moneda: str = "EUR"
    locatie_judet: Optional[str] = None
    locatie_oras: Optional[str] = None
    titlu: Optional[str] = None
    descriere: Optional[str] = None
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


@router.post("/listings/save-manual")
def save_manual_listing(
    data: ManualListingSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Salvare din Căutarea Manuală în tabelul MONITOR (real_estate_listings) cu status="saved",
    ca anunțul să apară în "Salvate & Ignorate". Înainte salvările manuale mergeau în tabelul
    VECHI (real_estate_listing), fără UI care să le citească. IM-5."""
    # Scraperul vechi emite platform="imobiliare"; monitorul folosește "imobiliare_ro".
    platform = {"imobiliare": "imobiliare_ro"}.get(data.platform, data.platform)

    # external_id efectiv: id-ul dat sau, în lipsă, source_url trunchiat la 200 (coloana e
    # VARCHAR(200)). Fără niciunul nu putem deduplica -> 422.
    external_id = data.external_id or (data.source_url[:200] if data.source_url else None)
    if not external_id:
        raise HTTPException(422, "Anunțul nu are nici external_id, nici URL — nu poate fi salvat (deduplicare imposibilă).")

    # Idempotență: dacă există deja pentru (user, platformă normalizată, external_id) -> doar
    # marchează saved (fără duplicat); redevine "saved" chiar dacă era "ignored".
    existing = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.platform == platform,
        RealEstateListing.external_id == external_id,
    ).first()
    if existing:
        existing.status = "saved"
        db.commit()
        return {"ok": True, "id": existing.id, "existing": True}

    # Utilitare deja folosite de scanner (nu importăm scanner-ul, doar helperele lui).
    from app.services.real_estate.extractor import extract_all
    from app.services.real_estate.zones import normalize_zone
    from app.services.real_estate.scorer import compute_re_score

    titlu = data.titlu or ""
    descriere = data.descriere or ""
    text = f"{titlu} {descriere}"
    # Extragere regex din text — FĂRĂ groq_extract (request sincron, fără apel LLM).
    extracted = extract_all(text)
    # Precedență payload (scraper) > regex, ca în _save_listing (IM-1).
    if data.camere is not None:
        extracted["rooms"] = data.camere
    if data.suprafata_mp is not None:
        extracted["area_sqm"] = data.suprafata_mp
    if data.etaj is not None:
        extracted["floor"] = data.etaj
    if data.pret is not None:
        extracted["price"] = data.pret
        extracted["currency"] = data.moneda or "EUR"

    price = extracted.get("price")
    currency = extracted.get("currency") or "EUR"
    area = extracted.get("area_sqm")
    rooms = extracted.get("rooms")
    price_per_sqm = round(price / area, 2) if price and area and area > 0 else None

    zone_raw = data.locatie_oras or ""
    # city None -> normalize_zone detectează orașul din text (comportament suportat de funcție).
    zone_normalized = normalize_zone(zone_raw, None, {})
    city = data.locatie_oras   # la manual nu există kw.city; folosim ce avem

    tip_anunt = data.tip_anunt or "vanzare"
    score, grade = (50, "C")
    if tip_anunt == "inchiriere" and price and area:
        score, grade = compute_re_score(
            price, currency, area, rooms, zone_normalized, city, None, tip_anunt="inchiriere")

    listing = RealEstateListing(
        user_id         = current_user.id,
        keyword_id      = None,
        platform        = platform,
        external_id     = external_id,
        source          = "manual",
        status          = "saved",
        title           = titlu[:500],
        price           = price,
        currency        = currency,
        price_per_sqm   = price_per_sqm,
        property_type   = data.tip_proprietate,
        rooms           = rooms,
        area_sqm        = area,
        floor           = extracted.get("floor"),
        zone_raw        = zone_raw[:200] if zone_raw else None,
        zone_normalized = zone_normalized,
        city            = city,
        image_url       = data.thumbnail_url or "",
        url             = data.source_url or "",
        description     = descriere[:2000],
        score           = score,
        grade           = grade,
        found_at        = datetime.now(timezone.utc),
        last_checked_at = datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return {"ok": True, "id": listing.id, "existing": False}


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func
    # Cardul "Total listinguri" reflectă feed-ul ACTIV (aliniat cu by_grade/by_platform).
    total = db.query(RealEstateListing).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == "active").count()
    by_grade = db.query(
        RealEstateListing.grade, func.count(RealEstateListing.id)
    ).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == "active",
    ).group_by(RealEstateListing.grade).all()
    by_platform = db.query(
        RealEstateListing.platform, func.count(RealEstateListing.id)
    ).filter(
        RealEstateListing.user_id == current_user.id,
        RealEstateListing.status == "active",
    ).group_by(RealEstateListing.platform).all()
    kw_count = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id,
        RealEstateKeyword.is_active == True,
    ).count()
    # Status sesiune Facebook — daca exista keyword FB Marketplace sau FB Groups.
    has_fb_keyword = db.query(RealEstateKeyword).filter(
        RealEstateKeyword.user_id == current_user.id,
        RealEstateKeyword.is_active == True,
        RealEstateKeyword.platform.in_(("facebook_marketplace", "facebook_groups")),
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
        "by_platform": {p: c for p, c in by_platform},
        "facebook_session_valid": fb_session_valid,
        "has_facebook_keywords": has_fb_keyword,
    }


# MODIFICARE 18 — impactul stergerii unui keyword imobiliar (listinguri asociate).
@router.get("/keywords/{keyword_id}/impact")
def get_keyword_impact(
    keyword_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_count = db.query(func.count(RealEstateListing.id)).filter(
        RealEstateListing.keyword_id == keyword_id,
        RealEstateListing.user_id == current_user.id,
    ).scalar() or 0
    return {"listing_count": listing_count, "seen_count": 0}


@router.post("/scan-now")
@limiter.limit("5/minute")
def scan_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger immediate background scan for real estate keywords."""
    import threading
    from app.database import SessionLocal
    from app.services.real_estate_scanner import run_real_estate_scan
    from app.services.log_manager import set_log_user

    user_id = current_user.id

    def _background_scan():
        set_log_user(user_id)  # MON-4 — jurnalele scanului manual apartin acestui user
        _db = SessionLocal()
        try:
            # Butonul manual ocoleste intervalul de polling (force_polling); intervalul orar
            # (_within_hours) ramane respectat ca pana acum.
            run_real_estate_scan(_db, user_id=user_id, force_polling=True)
        except Exception as exc:
            print(f"[REScan manual] eroare user {user_id}: {exc}")
        finally:
            _db.close()

    threading.Thread(target=_background_scan, daemon=True).start()
    return {"ok": True, "message": "Scanare imobiliare pornită în background."}
