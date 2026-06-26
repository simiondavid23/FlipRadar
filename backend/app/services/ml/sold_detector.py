"""
Daily job: detect sold listings in market_listings.
For each listing without sold_at, makes a HEAD request to source_url.
404/410 response → listing sold → record sold_at + days_to_sell.
This generates training labels for the ML price prediction model.
"""
from datetime import datetime, timezone
from typing import Optional
import re
import requests as req
from sqlalchemy.orm import Session

from app.services.log_manager import log_manager


# Semnale de pagina "vandut/sters" per platforma. Folosite DOAR ca fallback cand
# HEAD e neconcludent (403/timeout/redirect ciudat) — diagnosticul a aratat ca
# toate platformele noastre intorc HEAD 404 real pentru anunturi sterse.
_OLX_SOLD_SIGNALS = [
    "acest anunț nu mai este disponibil",
    "anunțul nu mai este disponibil",
    "anuntul nu mai este disponibil",
    "oferta nu mai este activă",
    "oferta nu mai este activa",
    "this ad is no longer available",
    "anunț expirat",
    "anunt expirat",
    "oferta-inexistenta",
    "anunturi/d/404",
]

_VINTED_SOLD_SIGNALS = [
    "this item is no longer available",
    "acest articol nu mai este disponibil",
    "item not found",
    "articol negăsit",
]

_AUTOSCOUT24_SOLD_SIGNALS = [
    "anunțul nu mai este disponibil",
    "listing is no longer available",
    "dieses inserat ist nicht mehr",
    "nicht mehr verfügbar",
    "angebot nicht gefunden",
]

_KLEINANZEIGEN_SOLD_SIGNALS = [
    "anzeige nicht gefunden",
    "diese anzeige wurde",
    "leider nicht mehr",
    "ad not found",
    "nicht mehr verfügbar",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,de-DE;q=0.8",
    "Accept": "text/html,application/xhtml+xml,*/*",
}


def _detect_platform(url: str) -> str:
    """Detect platform from URL."""
    url_lower = (url or "").lower()
    if "olx.ro" in url_lower:
        return "olx"
    if "vinted.ro" in url_lower or "vinted.com" in url_lower:
        return "vinted"
    if "autovit.ro" in url_lower:
        return "autovit"
    if "autoscout24" in url_lower:
        return "autoscout24"
    if "kleinanzeigen" in url_lower or "ebay-kleinanzeigen" in url_lower:
        return "kleinanzeigen"
    if "mobile.de" in url_lower:
        return "mobile_de"
    return "unknown"


def _check_head_404(url: str) -> Optional[bool]:
    """HEAD request. True daca 404/410 (sters), False daca 200 (activ),
    None la neconcludent/eroare (alt status, timeout, 403)."""
    try:
        resp = req.head(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code in (404, 410):
            return True
        # Redirect catre o pagina de 404 (unele platforme pastreaza 200 dar
        # schimba URL-ul final).
        final_url = str(resp.url).lower()
        if any(x in final_url for x in ["/404", "inexistent", "not-found", "nenajden"]):
            return True
        if resp.status_code == 200:
            return False
        return None
    except Exception:
        return None


def _check_get_signals(url: str, signals: list) -> bool:
    """GET pagina si cauta semnale text de "vandut/sters". True daca gaseste."""
    try:
        resp = req.get(url, headers=_HEADERS, timeout=12, allow_redirects=True)
        final_url = str(resp.url).lower()
        if any(x in final_url for x in ["/404", "inexistent", "not-found", "nenajden"]):
            return True
        if resp.status_code in (404, 410):
            return True
        if resp.status_code != 200:
            return False
        page_text = resp.text.lower()
        return any(sig in page_text for sig in signals)
    except Exception:
        return False


def _check_vinted_api(url: str) -> bool:
    """Vinted: detecteaza prin PAGINA anuntului, nu prin API.

    API-ul public /api/v2/items/{id} raspunde 404 (HTML) la cereri
    neautentificate INDIFERENT daca anuntul exista — deci ar marca orice anunt
    ca vandut (fals-pozitiv, confirmat in diagnostic). Pagina anuntului insa e
    fiabila: HEAD 404 = sters, 200 = activ.
    """
    head = _check_head_404(url)
    if head is True:
        return True
    if head is False:
        return False
    # HEAD neconcludent → fallback pe semnale din pagina.
    return _check_get_signals(url, _VINTED_SOLD_SIGNALS)


def _check_url(url: str) -> bool:
    """Detectie "vandut/sters" constienta de platforma.

    Diagnosticul a aratat ca toate platformele colectate (olx, vinted, autovit,
    olx_auto→autovit) intorc HEAD 404 real pentru anunturi sterse si 200 pentru
    cele active. Deci HEAD 404 e semnalul primar; GET cu semnale ruleaza doar
    cand HEAD e neconcludent (evita fals-pozitive din fraze generice pe pagini
    active de ~1.7MB).
    """
    if not url or not url.startswith("http"):
        return False

    platform = _detect_platform(url)

    # Vinted — pagina anuntului (API neautentificat da mereu 404).
    if platform == "vinted":
        return _check_vinted_api(url)

    # Autovit / Mobile.de — HEAD 404 fiabil, fara fallback (autovit chiar
    # normalizeaza URL-ul dar pastreaza statusul corect).
    if platform in ("autovit", "mobile_de"):
        return _check_head_404(url) is True

    # OLX / AutoScout24 / Kleinanzeigen — HEAD 404 → sters; 200 → activ; doar
    # cand HEAD e neconcludent cautam semnale in pagina.
    if platform in ("olx", "autoscout24", "kleinanzeigen"):
        head = _check_head_404(url)
        if head is True:
            return True
        if head is False:
            return False
        signals = {
            "olx": _OLX_SOLD_SIGNALS,
            "autoscout24": _AUTOSCOUT24_SOLD_SIGNALS,
            "kleinanzeigen": _KLEINANZEIGEN_SOLD_SIGNALS,
        }[platform]
        return _check_get_signals(url, signals)

    # Platforma necunoscuta — HEAD 404 conservator.
    return _check_head_404(url) is True


def run_sold_detection(db: Session,
                       batch_size: int = 100) -> dict:
    """
    Check market_listings without sold_at for sold status.
    Processes batch_size listings per run to avoid timeouts.
    Returns stats dict.
    """
    from app.models.market_listing import MarketListing

    stats = {"checked": 0, "sold": 0, "errors": 0}

    try:
        # Fetch listings without sold_at, oldest last_seen_at first
        # (prioritize listings that haven't been checked recently)
        pending = db.query(MarketListing).filter(
            MarketListing.sold_at.is_(None),
            MarketListing.source_url.isnot(None),
            MarketListing.source_url != "",
        ).order_by(
            MarketListing.last_seen_at.asc()
        ).limit(batch_size).all()

        if not pending:
            log_manager.emit("catalog", "INFO",
                "ML sold detection: niciun listing de verificat")
            return stats

        log_manager.emit("catalog", "SCAN",
            f"ML sold detection: verificare {len(pending)} listinguri")

        for listing in pending:
            try:
                is_sold = _check_url(listing.source_url)
                stats["checked"] += 1

                if is_sold:
                    now = datetime.now(timezone.utc)
                    listing.sold_at = now

                    # Calculate days_to_sell from listed_at to sold_at.
                    # listed_at e stocat naiv (coloana DateTime fara timezone);
                    # il normalizam la UTC ca sa nu crape scaderea aware - naive.
                    if listing.listed_at:
                        listed = listing.listed_at
                        if listed.tzinfo is None:
                            listed = listed.replace(tzinfo=timezone.utc)
                        delta = now - listed
                        listing.days_to_sell = max(0, delta.days)
                    else:
                        listing.days_to_sell = None

                    stats["sold"] += 1
                    log_manager.emit("catalog", "OK",
                        f"ML vândut: {listing.title[:50]!r} "
                        f"({listing.category}) după "
                        f"{listing.days_to_sell or '?'} zile")
                else:
                    # Still active — update last_seen_at
                    listing.last_seen_at = datetime.now(timezone.utc)

            except Exception as exc:
                stats["errors"] += 1
                log_manager.emit("catalog", "WARN",
                    f"ML sold check eroare: {str(exc)[:60]}")
                continue

        db.commit()

        log_manager.emit("catalog", "OK",
            f"ML sold detection: {stats['checked']} verificate · "
            f"{stats['sold']} vândute · {stats['errors']} erori")

    except Exception as exc:
        db.rollback()
        log_manager.emit("catalog", "ERR",
            f"ML sold detection job eroare: {str(exc)[:100]}")

    return stats
