"""Cleanup periodic — marcheaza listinguri ca sold/removed si le sterge cand dispar.

CLEAN-1: polling-ul e single-threaded, cu delay politicos intre verificari si pe
curl_cffi cu impersonate (stack-ul `requests` gol era blocat de marketplace-uri, iar
orice eroare era mascata ca 'active'). `cleanup_sold_listings` ruleaza ca job propriu
la 30 min (inainte: "la ~10 cicluri" din orchestrator, imprevizibil de rar);
`cleanup_removed_listings_daily` ruleaza o data pe zi din scheduler.
"""
import random
import time
from datetime import datetime, timedelta, timezone

from curl_cffi import requests as curl_requests
from sqlalchemy.orm import Session

from app.models.radar_listing import RadarListing
from app.services.log_manager import log_manager


_IMPERSONATE = "chrome110"   # conventia proiectului pentru site-uri HTML
_HTTP_TIMEOUT = 10
_DELAY_RANGE = (0.4, 1.0)    # delay politicos intre verificari consecutive

# CLEAN-1 — markeri text DOAR unde stringurile sunt suficient de specifice ca sa
# nu produca stergeri false (cleanup-ul zilnic sterge definitiv). Vinted: "sold"/
# "vandut" apar in bundle-uri JS si in anunturi conexe de pe pagina -> scos;
# 404-ul e acoperit de fluxul gone din RAD-1. Publi24/LaJumate/Autovit/Mobile.de:
# markerii se stabilesc empiric cu scripts/diagnostics/cleanup_sonda.py (CLEAN-2).
# Facebook: login-wall 200 neautentificat -> neverificabil, sarit in _check_url.
_SOLD_MARKERS = {
    "olx": ["anunț expirat", "anunt expirat", "anunțul a fost șters", "this offer has expired"],
    "okazii": ["vandut", "vândut", "anunt expirat", "anunț expirat"],
}


def _classify(status_code: int, body: str | None, platform: str) -> str:
    """PURA: decizia pe baza statusului si (optional) a body-ului.
    Returneaza 'active' | 'sold' | 'removed' | 'unknown'.
    'unknown' = blocat/eroare/nedecidabil — apelantii NU modifica statusul si
    NU sterg pe unknown (inainte, orice eroare era mascata ca 'active')."""
    if status_code in (404, 410):
        return "removed"
    if status_code != 200:
        return "unknown"
    markers = _SOLD_MARKERS.get((platform or "").lower())
    if not markers:
        return "active"
    if body is None:
        return "active"   # 200 la HEAD, fara body cerut -> nu putem decide sold, dar exista
    low = body.lower()
    return "sold" if any(m in low for m in markers) else "active"


def _check_url(url: str, platform: str) -> str:
    """HEAD intai (ieftin; OLX intoarce 404 real). GET doar cand e nevoie de body
    (platforme cu markeri) sau cand HEAD e blocat/nesuportat (403/405/5xx).
    Orice exceptie de retea -> 'unknown'."""
    p = (platform or "").lower()
    if p == "facebook":
        return "unknown"
    needs_body = p in _SOLD_MARKERS
    try:
        resp = curl_requests.head(url, impersonate=_IMPERSONATE,
                                  timeout=_HTTP_TIMEOUT, allow_redirects=True)
        status = resp.status_code
    except Exception:
        return "unknown"
    if status in (404, 410):
        return "removed"
    if status == 200 and not needs_body:
        return "active"
    # HEAD blocat/nesuportat SAU platforma cere body pentru markeri -> GET
    try:
        resp = curl_requests.get(url, impersonate=_IMPERSONATE,
                                 timeout=_HTTP_TIMEOUT, allow_redirects=True)
    except Exception:
        return "unknown"
    return _classify(resp.status_code, resp.text or "", p)


def cleanup_sold_listings(db: Session) -> int:
    """Verifica listingurile active mai vechi de 1h si actualizeaza statusul.

    Returneaza numarul de listinguri actualizate.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    candidates = (
        db.query(RadarListing)
        .filter(RadarListing.status == "active", RadarListing.found_at < cutoff)
        .order_by(RadarListing.last_checked_at.asc().nullsfirst())
        .limit(50)
        .all()
    )
    updated = 0
    for listing in candidates:
        new_status = _check_url(listing.url, listing.platform)
        listing.last_checked_at = datetime.now(timezone.utc)
        # CLEAN-1 — 'unknown' (blocat/eroare/neverificabil) NU atinge statusul; doar
        # last_checked_at avanseaza, ca rotatia sa treaca mai departe la urmatoarele.
        if new_status not in ("active", "unknown"):
            listing.status = new_status
            updated += 1
        time.sleep(random.uniform(*_DELAY_RANGE))
    if candidates:
        db.commit()
    if updated:
        print(f"[RadarCleanup] {updated} listinguri marcate ca sold/removed.")
    return updated


def cleanup_removed_listings_daily(db: Session) -> int:
    """Job zilnic: verifica TOATE listingurile (orice status) si sterge definitiv
    cele care nu mai exista pe marketplace (404/410 sau markeri sold).
    Include listinguri salvate si ignorate — odata ce anuntul dispare, nu mai are rost sa fie urmarit.

    CLEAN-1: iterarea nu mai foloseste offset. Randurile verificate primesc
    last_checked_at=now si sar la coada ordonarii, deci un offset aplicat peste
    ordinea re-amestecata sarea ~jumatate din randuri. Acum filtram pe
    last_checked_at < startul rularii: fiecare rand verificat iese din setul de
    candidati -> terminare garantata, zero sarituri.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    run_started = datetime.now(timezone.utc)
    BATCH_SIZE = 50
    MAX_CHECKS = 1000   # plafon de siguranta per rulare (ajustabil)
    total_checked = 0
    total_deleted = 0

    eligible = db.query(RadarListing).filter(RadarListing.found_at < cutoff).count()
    log_manager.emit("radar", "CLEAN", f"Cleanup zilnic pornit · {eligible} anunțuri eligibile (max {MAX_CHECKS}/rulare)")

    while total_checked < MAX_CHECKS:
        candidates = (
            db.query(RadarListing)
            .filter(
                RadarListing.found_at < cutoff,
                # doar randuri neatinse in ACEASTA rulare -> terminare garantata, zero sarituri
                (RadarListing.last_checked_at.is_(None)) | (RadarListing.last_checked_at < run_started),
            )
            .order_by(RadarListing.last_checked_at.asc().nullsfirst())
            .limit(BATCH_SIZE)
            .all()
        )
        if not candidates:
            break
        batch_deleted = 0
        for listing in candidates:
            result = _check_url(listing.url, listing.platform)
            listing.last_checked_at = datetime.now(timezone.utc)
            total_checked += 1
            if result in ("removed", "sold"):
                db.delete(listing)
                batch_deleted += 1
            time.sleep(random.uniform(*_DELAY_RANGE))
        db.commit()
        total_deleted += batch_deleted

    if total_deleted:
        print(f"[RadarDailyCleanup] {total_deleted} anunțuri șterse definitiv (dispărute de pe marketplace).")
        log_manager.emit("radar", "WARN", f"{total_deleted} anunțuri nu mai există pe marketplace → șterse definitiv")
    log_manager.emit("radar", "OK",
        f"Cleanup finalizat · {total_checked} verificate · {total_deleted} șterse · {eligible - total_deleted} rămase")
    return total_deleted
