"""Job APScheduler: check_real_estate_alerts.

Ruleaza la fiecare 30 minute. Pentru fiecare alerta imobiliara activa, ruleaza
scraperul platformei cu filtrele alertei, persista anunturile noi in
real_estate_listing (saved=False, listed_at/last_seen_at) si creeaza o Notification
de tip "real_estate_alert" cand apar anunturi noi.
"""
import asyncio
from datetime import datetime

from app.database import SessionLocal
from app.models.real_estate_alert import RealEstateAlert
from app.models.real_estate_listing import RealEstateListing
from app.models.notification import Notification
from app.scrapers.real_estate.olx_real_estate import search_olx_real_estate
from app.scrapers.real_estate.storia_scraper import search_storia
from app.scrapers.real_estate.imobiliare_ro_scraper import search_imobiliare_ro
from app.scrapers.real_estate.facebook_real_estate import search_facebook_real_estate

_SCRAPERS = {
    "olx": search_olx_real_estate,
    "storia": search_storia,
    "imobiliare": search_imobiliare_ro,
    "facebook": search_facebook_real_estate,
}


def _run_scraper(platform: str, filters: dict) -> list:
    # Platforma "toate" (sau necunoscuta) -> ruleaza toate scraperele si combina.
    if platform in _SCRAPERS:
        fns = [_SCRAPERS[platform]]
    else:
        fns = list(_SCRAPERS.values())
    out = []
    for fn in fns:
        try:
            out.extend(asyncio.run(fn(filters)) or [])
        except Exception as exc:
            print(f"[RealEstateScanner] {platform}/{getattr(fn, '__name__', '?')} error: {exc}")
    return out


def check_real_estate_alerts() -> int:
    """Returneaza numarul total de anunturi noi gasite in aceasta rulare."""
    print(f"[RealEstateScanner] Pornit la {datetime.now().strftime('%H:%M:%S')}")
    db = SessionLocal()
    total_new = 0
    try:
        alerts = (
            db.query(RealEstateAlert)
            .filter(RealEstateAlert.is_active == True)  # noqa: E712
            .all()
        )
        for alert in alerts:
            filters = dict(alert.filters or {})
            filters.setdefault("tip_anunt", alert.tip_anunt)
            filters.setdefault("tip_proprietate", alert.tip_proprietate)

            # Prima scanare pe (user, platforma) doar "seamana" baza, fara notificare,
            # ca sa nu inundam utilizatorul cu toate anunturile existente.
            had_any = (
                db.query(RealEstateListing.id)
                .filter(
                    RealEstateListing.user_id == alert.user_id,
                    RealEstateListing.platform == alert.platform,
                )
                .first()
                is not None
            )

            results = _run_scraper(alert.platform, filters)

            # Filtru keyword optional: pastreaza doar anunturile al caror titlu/descriere
            # contine vreunul dintre cuvintele cheie (cautate de utilizator).
            keywords = [str(k).lower() for k in (filters.get("keywords") or []) if str(k).strip()]
            if keywords:
                def _kw_match(r):
                    text = f"{r.get('titlu') or ''} {r.get('descriere') or ''}".lower()
                    return any(k in text for k in keywords)
                results = [r for r in results if _kw_match(r)]

            now = datetime.utcnow()
            new_count = 0
            for r in results:
                src = r.get("source_url")
                if not src:
                    continue
                existing = (
                    db.query(RealEstateListing)
                    .filter(
                        RealEstateListing.user_id == alert.user_id,
                        RealEstateListing.source_url == src,
                    )
                    .first()
                )
                if existing:
                    existing.last_seen_at = now
                    continue
                db.add(RealEstateListing(
                    user_id=alert.user_id,
                    platform=r.get("platform"),
                    external_id=r.get("external_id"),
                    tip_anunt=r.get("tip_anunt"),
                    tip_proprietate=r.get("tip_proprietate"),
                    camere=r.get("camere"),
                    suprafata_mp=r.get("suprafata_mp"),
                    etaj=r.get("etaj"),
                    pret=r.get("pret"),
                    moneda=r.get("moneda") or "EUR",
                    locatie_judet=r.get("locatie_judet"),
                    locatie_oras=r.get("locatie_oras"),
                    an_constructie=r.get("an_constructie"),
                    facilitati=r.get("facilitati"),
                    titlu=r.get("titlu"),
                    descriere=r.get("descriere"),
                    source_url=src,
                    thumbnail_url=r.get("thumbnail_url"),
                    listed_at=now,
                    last_seen_at=now,
                    saved=False,
                ))
                new_count += 1

            if new_count > 0 and had_any:
                db.add(Notification(
                    user_id=alert.user_id,
                    title="Anunturi imobiliare noi",
                    message=(
                        f"{new_count} anunturi noi pentru alerta ta "
                        f"({alert.tip_proprietate or 'imobil'} {alert.tip_anunt or ''} pe {alert.platform})."
                    ),
                    notification_type="real_estate_alert",
                    link="/dashboard/notifications",
                ))
                total_new += new_count
            db.commit()

        print(f"[RealEstateScanner] Finalizat — {total_new} anunturi noi.")
        return total_new
    except Exception as exc:
        print(f"[RealEstateScanner] EROARE: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()
