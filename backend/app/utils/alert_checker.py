"""
Background task for checking price alerts.
Runs periodically to compare product prices against alert thresholds.
Handles both price_drop and price_rise directions and converts currencies when needed.
When an alert fires, a Discord webhook alert is queued and (if SMTP configured) an email is sent.

Inainte de verificare, re-scrapeaza pretul curent pentru toate produsele
scrapeable (din magazinele integrate), nu doar cele cu alerte. Cererile sunt
secventiale cu delay aleator intre ele ca sa nu fie blocate ca trafic abuziv.
"""
import random
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.alert import Alert
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.user import User
from app.models.price_history import PriceHistory
from app.models.tracked_product import TrackedProduct
from app.models.radar_settings import RadarSettings
from app.services.currency_service import convert
from app.services.email_service import send_alert_email, is_configured as email_is_configured
from app.services.scraper_service import refresh_price_from_source
from app.services import catalog_health_watchdog
from app.services.discord_service import (
    build_alert_embed, build_flash_deal_embed, send_price_alert_notification,
)

_SCRAPE_DELAY_RANGE = (0.6, 1.4)


def _recompute_primary_snapshot(product: Product) -> None:
    sources_with_price = [s for s in product.sources if s.current_price is not None]
    if not sources_with_price:
        return
    base_currency = product.currency or "EUR"
    def price_in_base(s: ProductSource) -> float:
        if (s.currency or base_currency).upper() == base_currency.upper():
            return float(s.current_price)
        try:
            return float(convert(s.current_price, s.currency, base_currency))
        except Exception:
            return float(s.current_price)
    cheapest = min(sources_with_price, key=price_in_base)
    product.current_price = cheapest.current_price
    product.currency = cheapest.currency or base_currency
    product.source = cheapest.source
    product.source_url = cheapest.source_url


# FlipRadar — Flash Deal: cand un produs urmarit (din catalogul propriu sau din
# Radar Preturi) scade brusc cu cel putin pragul setat de utilizator, trimite o
# alerta pe webhook-ul Discord dedicat. Notificarea in-app a fost eliminata in
# NOTIF-1; dedup-ul e acum exclusiv cel al cozii Discord (24h pe produs+user+pret nou).
def _check_and_send_flash_deals(db, product, old_price: float, new_price: float, source: str):
    drop_pct = (old_price - new_price) / old_price

    # Gaseste user_id-urile care au produsul in catalog (owner) sau il monitorizeaza
    owner_ids = [r[0] for r in db.query(Product.user_id).filter(Product.id == product.id).all()]
    watcher_ids = [r[0] for r in db.query(TrackedProduct.user_id).filter(
        TrackedProduct.product_id == product.id,
        TrackedProduct.monitoring_active == True,
    ).all()]
    user_ids = set(owner_ids + watcher_ids)

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            continue
        threshold = float(user.flash_deal_threshold or 0.15)
        if drop_pct < threshold:
            continue

        # Flash Deal pe Discord (webhook dedicat de alerte). Dedup-ul e exclusiv
        # cel al cozii Discord: 24h pe (produs, user, pret nou) — un pret nou diferit
        # retrimite. Bloc independent: o eroare aici nu opreste bucla.
        try:
            st = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
            if st is not None:
                fd_embed = build_flash_deal_embed(
                    product_name=product.name, old_price=float(old_price),
                    new_price=float(new_price), currency=product.currency or "EUR",
                    drop_pct=drop_pct, source=source, product_url=product.source_url,
                )
                fd_lid = f"flashdeal-{product.id}-{user_id}-{new_price}"
                send_price_alert_notification(fd_embed, st, fd_lid)
        except Exception as exc:
            print(f"[AlertChecker] Discord flash deal esuat (user {user_id}): {exc}")


def _refresh_all_scrapeable_products(db: Session) -> int:
    """Re-scrape pretul pentru fiecare ProductSource din DB. Cererile sunt
    secventiale cu delay aleator intre ele ca sa nu fie blocate ca trafic
    abuziv. Dupa refresh, snapshot-ul Product (current_price, source,
    source_url) e recalculat = sursa cu pretul cel mai mic. Returneaza
    numarul de surse cu pret schimbat.
    """
    rows = db.query(ProductSource).all()
    total = len(rows)
    if total == 0:
        return 0
    print(f"[AlertChecker] Refresh preturi pentru {total} sursa(e) scrapeabila(e)...")
    # C-15: ciclu de watchdog — deschis DUPA total==0, ca un ciclu gol sa nu se deschida.
    catalog_health_watchdog.open_cycle()

    refreshed = 0
    touched_products: dict[int, Product] = {}
    now = datetime.now(timezone.utc)
    for i, ps in enumerate(rows):
        if i > 0:
            time.sleep(random.uniform(*_SCRAPE_DELAY_RANGE))
        product = ps.product
        new_price = refresh_price_from_source(
            source=ps.source,
            source_url=ps.source_url,
            product_name=product.name,
            sku=product.sku,
        )
        ps.last_checked_at = now
        catalog_health_watchdog.note_refresh(ps.source, success=(new_price is not None))
        if new_price is None:
            print(f"[AlertChecker] Nu am putut prelua pretul pentru \"{product.name[:50]}\" ({ps.source}). Folosesc pretul stocat: {ps.current_price} {ps.currency}")
            continue
        old_price = ps.current_price
        if old_price != new_price:
            ps.current_price = new_price
            db.add(PriceHistory(
                product_id=product.id,
                price=new_price,
                currency=ps.currency or "EUR",
                source=ps.source,
            ))
            refreshed += 1
            touched_products[product.id] = product
            print(f"[AlertChecker] Pret actualizat pentru \"{product.name[:50]}\" ({ps.source}): {old_price} -> {new_price} {ps.currency}")
            # FlipRadar — la o scadere de pret, verifica daca e Flash Deal.
            if old_price and new_price and old_price != new_price and new_price < old_price:
                _check_and_send_flash_deals(db, product, float(old_price), float(new_price), ps.source)
        else:
            print(f"[AlertChecker] Pret neschimbat pentru \"{product.name[:50]}\" ({ps.source}): {new_price} {ps.currency}")
    for product in touched_products.values():
        _recompute_primary_snapshot(product)
    # C-17: commit NECONDITIONAT — ps.last_checked_at e setat pe TOATE sursele
    # mai sus, chiar si cand niciun pret nu s-a schimbat. Conditia veche il
    # pierdea la db.close() in ciclurile "linistite" (si il salva doar
    # accidental cand Pasul 2 comitea o alerta declansata), iar UI-ul de pe
    # pagina de detaliu ("Verificat: ...") ramanea inghetat. Early-return-ul
    # pe total==0 exista deja mai sus, deci nu comitem niciodata pe gol.
    db.commit()
    # C-15: o eroare de watchdog nu trebuie sa rupa check_alerts.
    try:
        catalog_health_watchdog.close_cycle(db)
    except Exception as exc:
        print(f"[Watchdog Catalog] close esuat: {exc}")
    return refreshed


def _get_user_settings(db, user_id, cache):
    """ALERT-1 — RadarSettings per user, cache-uit pe durata unei rulari check_alerts."""
    if user_id not in cache:
        cache[user_id] = db.query(RadarSettings).filter(RadarSettings.user_id == user_id).first()
    return cache[user_id]


def check_alerts() -> int:
    """Compare product prices against active user alerts.

    Returns the number of alerts that were triggered in this run.
    """
    print(f"[AlertChecker] Pornit la {datetime.now().strftime('%H:%M:%S')}")
    db: Session = SessionLocal()
    triggered_count = 0
    emails_sent = 0
    try:
        # Pas 1: refresh pret pentru toate produsele scrapeable, nu doar cele
        # cu alerte. Pasul 2 (evaluarea alertelor) vede deja preturile fresh.
        _refresh_all_scrapeable_products(db)

        active_alerts = (
            db.query(Alert)
            .filter(Alert.is_active == True, Alert.is_triggered == False)
            .all()
        )

        smtp_on = email_is_configured()
        # ALERT-1 — cache per-rulare de RadarSettings (1 query/user) pentru webhook Discord.
        settings_cache = {}

        # Pas 2: verifica fiecare alerta. Query-ul pe Product re-citeste
        # din DB, deci preturile actualizate la pasul 1 sunt vizibile aici.
        for alert in active_alerts:
            product = db.query(Product).filter(Product.id == alert.product_id).first()
            if not product or product.current_price is None:
                continue

            product_currency = (product.currency or "EUR").upper()
            alert_currency = (alert.currency or "EUR").upper()

            if product_currency == alert_currency:
                price_in_alert_currency = product.current_price
            else:
                price_in_alert_currency = convert(
                    product.current_price, product_currency, alert_currency
                )

            alert_type = alert.alert_type or "price_drop"
            triggered = (
                alert_type == "price_drop" and price_in_alert_currency <= alert.target_price
            ) or (
                alert_type == "price_rise" and price_in_alert_currency >= alert.target_price
            )

            if triggered:
                alert.is_triggered = True
                alert.triggered_at = datetime.now(timezone.utc)
                triggered_count += 1

                # ALERT-1 — notificare Discord pe webhook-ul dedicat (bloc independent:
                # o eroare aici NU afecteaza notificarea in-app / emailul de mai jos).
                try:
                    st = _get_user_settings(db, alert.user_id, settings_cache)
                    if st is not None:
                        embed = build_alert_embed(
                            product_name=product.name,
                            current_price=float(price_in_alert_currency),
                            target_price=float(alert.target_price),
                            currency=alert_currency,
                            alert_type=alert_type,
                            product_url=product.source_url,
                        )
                        lid = f"alert-{alert.id}-{int(alert.triggered_at.timestamp())}"
                        if send_price_alert_notification(embed, st, lid):
                            print(f"[AlertChecker] Alerta {alert.id} pusa in coada Discord.")
                except Exception as exc:
                    print(f"[AlertChecker] Discord esuat pentru alerta {alert.id}: {exc}")

                if smtp_on:
                    user = db.query(User).filter(User.id == alert.user_id).first()
                    if user and user.email:
                        direction = "a scazut sub" if alert_type == "price_drop" else "a urcat peste"
                        ok = send_alert_email(
                            to=user.email,
                            product_name=product.name,
                            current_price=price_in_alert_currency,
                            target_price=alert.target_price,
                            currency=alert_currency,
                            direction=direction,
                            product_link=product.source_url,
                        )
                        if ok:
                            emails_sent += 1
                        else:
                            print(f"[AlertChecker] Emailul nu a putut fi trimis catre {user.email} pentru alerta {alert.id} (vezi log-uri SMTP de mai sus).")
                    else:
                        print(f"[AlertChecker] Alerta {alert.id} declansata, dar utilizatorul nu are email setat — email omis.")
                else:
                    print(f"[AlertChecker] Alerta {alert.id} declansata, dar SMTP NU e configurat in .env — email omis, alerta merge doar pe Discord (daca webhook setat).")

        if triggered_count > 0:
            db.commit()
            extra = f" ({emails_sent} emailuri trimise)" if smtp_on else ""
            print(f"[AlertChecker] {triggered_count} alerte declansate{extra}.")
        else:
            print(f"[AlertChecker] Verificat {len(active_alerts)} alerte - nicio declansare.")

        print(f"[AlertChecker] Finalizat. Alerte declansate: {triggered_count}, emailuri trimise: {emails_sent}")
        return triggered_count

    except Exception as e:
        print(f"[AlertChecker] EROARE NEASTEPTATA: {e}")
        import traceback
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()
