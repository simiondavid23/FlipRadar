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

# CLEAN-2 — markeri text DOAR unde sonda i-a confirmat empiric pe pagini sold, fara
# fals-pozitive pe pagini active (cleanup-ul zilnic sterge definitiv).
#   • OLX: SCOS. Paginile ACTIVE (1.7MB) contin toate frazele de sold in bundle-urile
#     i18n ("expirat", "vandut", "nu mai este disponibil", "sters", "dezactivat") ->
#     orice marker text da fals-pozitiv. Anunturile disparute raspund 410, deci OLX
#     merge pe status pur. Acceptat: un anunt OLX "vandut dar inca servit cu 200"
#     ramane nedetectat (mai bine nedetectat decat sters gresit).
#   • Okazii: PASTRAT. Markeri confirmati de sonda pe pagini sold; paginile sunt mici
#     (<120KB), deci riscul de fals-pozitiv e redus. Se scot daca apar fals-pozitive.
#   • Vinted: scos inca din CLEAN-1 (aceeasi problema de bundle); 404-ul e acoperit
#     de fluxul gone din RAD-1.
#   • Facebook: login-wall 200 neautentificat -> neverificabil, sarit in _check_url.
_SOLD_MARKERS = {
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
    """CLEAN-2 — HEAD-ul NU mai e crezut singur: sonda a dovedit ca Publi24
    raspunde 404 la HEAD pe anunturi VII (GET 200). Singura decizie luata direct
    din HEAD este 'active' la 200 pe platforme fara markeri. Orice altceva
    (inclusiv 404/410 la HEAD) se confirma prin GET; _classify ramane autoritatea."""
    p = (platform or "").lower()
    if p == "facebook":
        return "unknown"
    needs_body = p in _SOLD_MARKERS
    try:
        head = curl_requests.head(url, impersonate=_IMPERSONATE,
                                  timeout=_HTTP_TIMEOUT, allow_redirects=True)
    except Exception:
        return "unknown"
    if head.status_code == 200 and not needs_body:
        return "active"
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
