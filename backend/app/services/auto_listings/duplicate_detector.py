"""Detectare duplicate pentru anunturi auto — specific cazului OLX Auto <-> Autovit,
unde OLX Group cross-posteaza automat anunturile de dealeri intre cele 2 platforme.

Mirror pe services/real_estate/duplicate_detector.py (acelasi shape de return si aceleasi
niveluri 1/2/3/4), dar cu criterii specifice masinilor (make+model+an+pret+km) in loc de
zona/camere/suprafata. Helper-ele generice (hash imagine + _prices_close) vin din
services/shared/image_hash.py.

AtENTIE: AutoFeedListing NU are coloane make/model (doar `title`) si NU are seller_id —
de aceea marca+modelul se deriva din titlu (_make_model_key), iar Level 1b foloseste
combinatia make+model+an+pret+km (nu seller_id ca la imobiliare).

Level 1: 1a acelasi `url` · 1b make+model+an+pret+km identice pe platforme diferite -> auto-group
Level 2: pHash <=10 SAU (pHash <=20 SI color_hist >=0.85) -> auto-group
Level 3: price ±3% + make+model + an ±1 + km ±10%, platforme diferite -> doar semnalat (badge)
Level 4: fara potrivire -> nicio actiune
"""
import re
import uuid
from typing import Optional
from sqlalchemy.orm import Session

from app.services.shared.image_hash import (
    compute_phash, compute_color_hist, phash_distance, hist_similarity, _prices_close)


def _make_model_key(title: str) -> Optional[str]:
    """Marca+model normalizate din titlu = primele 2 tokenuri ne-numerice, lowercased.
    Ex: 'Volkswagen Passat 1.6 TDI Comfortline' -> 'volkswagen passat';
        'BMW 320d Touring' -> 'bmw 320d'. AutoFeedListing nu are coloane make/model."""
    if not title:
        return None
    toks = [t for t in re.findall(r"[a-z0-9]+", title.lower()) if not t.isdigit()]
    if not toks:
        return None
    return " ".join(toks[:2])


def _km_close(k1: Optional[int], k2: Optional[int], tolerance: float = 0.10) -> bool:
    """Analog lui _areas_close de la imobiliare, dar pentru km. Daca unul lipseste,
    nu penalizam (return True)."""
    if not k1 or not k2:
        return True
    return abs(k1 - k2) / max(k1, k2) <= tolerance


def _same_currency(a, b) -> bool:
    return (getattr(a, "currency", None) or "").upper() == (getattr(b, "currency", None) or "").upper()


def check_auto_duplicates(listing, db: Session, user_id: int) -> tuple:
    """Returneaza (duplicate_level, group_id_or_none, matched_listing_or_none)."""
    from app.models.auto_feed_listing import AutoFeedListing

    mm = _make_model_key(listing.title)

    # Level 1a: acelasi URL sursa (acelasi anunt indexat de doua ori). Coloana e `url`.
    if getattr(listing, "url", None):
        l1a = db.query(AutoFeedListing).filter(
            AutoFeedListing.user_id == user_id,
            AutoFeedListing.url == listing.url,
            AutoFeedListing.id != listing.id,
        ).first()
        if l1a:
            group_id = l1a.duplicate_group_id or str(uuid.uuid4())
            return 1, group_id, l1a

    # Level 1b: aceeasi masina cross-postata — make+model (din titlu) + an + pret + km +
    # moneda, TOATE identice, pe platforme DIFERITE. Practic sigur pentru cross-post OLX Group.
    if mm and listing.year and listing.price and listing.km:
        cands = db.query(AutoFeedListing).filter(
            AutoFeedListing.user_id == user_id,
            AutoFeedListing.id != listing.id,
            AutoFeedListing.platform != listing.platform,
            AutoFeedListing.year == listing.year,
            AutoFeedListing.km == listing.km,
            AutoFeedListing.price == listing.price,
        ).all()
        for cand in cands:
            if _same_currency(listing, cand) and _make_model_key(cand.title) == mm:
                group_id = cand.duplicate_group_id or str(uuid.uuid4())
                return 1, group_id, cand

    # Level 2: image hash match (prima poza), acelasi prag ca la imobiliare.
    if listing.phash:
        candidates = db.query(AutoFeedListing).filter(
            AutoFeedListing.user_id == user_id,
            AutoFeedListing.phash.isnot(None),
            AutoFeedListing.id != listing.id,
        ).all()
        for cand in candidates:
            dist = phash_distance(listing.phash, cand.phash)
            if dist <= 10:
                group_id = cand.duplicate_group_id or str(uuid.uuid4())
                return 2, group_id, cand
            if dist <= 20 and listing.color_hist and cand.color_hist:
                sim = hist_similarity(listing.color_hist, cand.color_hist)
                if sim >= 0.85:
                    group_id = cand.duplicate_group_id or str(uuid.uuid4())
                    return 2, group_id, cand

    # Level 3: text (semnalat, NU auto-grupat) — price ±3% + make+model + an ±1 + km ±10%,
    # pe platforme diferite (feature-ul e despre cross-post, deci reducem zgomotul same-platform).
    if mm and listing.price and listing.year:
        candidates = db.query(AutoFeedListing).filter(
            AutoFeedListing.user_id == user_id,
            AutoFeedListing.id != listing.id,
            AutoFeedListing.platform != listing.platform,
            AutoFeedListing.year.isnot(None),
            AutoFeedListing.price.isnot(None),
            AutoFeedListing.year.between(listing.year - 1, listing.year + 1),
        ).all()
        for cand in candidates:
            if _make_model_key(cand.title) != mm or not _same_currency(listing, cand):
                continue
            if _prices_close(float(listing.price), float(cand.price), 0.03) \
                    and _km_close(listing.km, cand.km, 0.10):
                return 3, None, cand

    return 4, None, None
