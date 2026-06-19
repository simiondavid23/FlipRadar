"""
Background task for checking price alerts.
Runs periodically to compare product prices against alert thresholds.
Handles both price_drop and price_rise directions and converts currencies when needed.
When an alert fires, a matching Notification is created and (if SMTP configured) an email is sent.

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
from app.models.notification import Notification
from app.models.price_history import PriceHistory
from app.models.watchlist import WatchlistItem
from app.services.currency_service import convert
from app.services.email_service import send_alert_email, is_configured as email_is_configured
from app.services.scraper_service import refresh_price_from_source

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


def _make_notification(alert: Alert, product: Product, price_in_alert_currency: float) -> Notification:
    direction = "a scazut sub" if (alert.alert_type or "price_drop") == "price_drop" else "a urcat peste"
    currency = (alert.currency or "EUR").upper()
    title = f"Alerta pret: {product.name}"
    message = (
        f"Pretul curent ({price_in_alert_currency:.2f} {currency}) "
        f"{direction} tinta ta ({alert.target_price:.2f} {currency})."
    )
    return Notification(
        user_id=alert.user_id,
        title=title,
        message=message,
        notification_type="alert",
        link=f"/dashboard/products/{product.id}",
    )


# FlipRadar — Flash Deal: cand un produs urmarit (din catalogul propriu sau din
# Radar Preturi) scade brusc cu cel putin pragul setat de utilizator, creeaza o
# notificare in-app, evitand duplicatele din ultimele 6 ore (deduplicare pe link/produs).
def _check_and_create_flash_deal_notifications(db, product, old_price: float, new_price: float, source: str):
    drop_pct = (old_price - new_price) / old_price

    # Gaseste user_id-urile care au produsul in catalog (owner) sau in watchlist
    owner_ids = [r[0] for r in db.query(Product.user_id).filter(Product.id == product.id).all()]
    watcher_ids = [r[0] for r in db.query(WatchlistItem.user_id).filter(WatchlistItem.product_id == product.id).all()]
    user_ids = set(owner_ids + watcher_ids)

    from datetime import timedelta
    recent_cutoff = datetime.utcnow() - timedelta(hours=6)
    link = f"/dashboard/products/{product.id}"

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            continue
        threshold = float(user.flash_deal_threshold or 0.15)
        if drop_pct < threshold:
            continue

        # Evita duplicate: nicio alta notificare flash_deal pentru acelasi produs
        # (acelasi link) si acelasi user in ultimele 6 ore.
        exists = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.notification_type == "flash_deal",
            Notification.link == link,
            Notification.created_at >= recent_cutoff,
        ).first()
        if exists:
            continue

        db.add(Notification(
            user_id=user_id,
            title="Flash Deal detectat",
            message=(
                f"{product.name}: {old_price} {product.currency} -> "
                f"{new_price} {product.currency} "
                f"(-{round(drop_pct * 100, 1)}% pe {source})"
            ),
            notification_type="flash_deal",
            link=link,
        ))


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
                _check_and_create_flash_deal_notifications(db, product, float(old_price), float(new_price), ps.source)
        else:
            print(f"[AlertChecker] Pret neschimbat pentru \"{product.name[:50]}\" ({ps.source}): {new_price} {ps.currency}")
    for product in touched_products.values():
        _recompute_primary_snapshot(product)
    if refreshed > 0 or touched_products:
        db.commit()
    return refreshed


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
                alert.triggered_at = datetime.utcnow()
                db.add(_make_notification(alert, product, price_in_alert_currency))
                triggered_count += 1

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
                    print(f"[AlertChecker] Alerta {alert.id} declansata, dar SMTP NU e configurat in .env — doar notificare in-app.")

        if triggered_count > 0:
            db.commit()
            extra = f" ({emails_sent} emailuri trimise)" if smtp_on else ""
            print(f"[AlertChecker] {triggered_count} alerte declansate si notificari create{extra}.")
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
