"""
Background task for checking price alerts.
Runs periodically to compare product prices against alert thresholds.
Handles both price_drop and price_rise directions and converts currencies when needed.
When an alert fires, a matching Notification is created and (if SMTP configured) an email is sent.

Inainte de verificare, re-scrapeaza pretul curent pentru produsele cu alerte
active (din magazinele integrate), ca sa lucram cu valori reale de pe site,
nu cu pretul vechi din momentul adaugarii produsului.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.alert import Alert
from app.models.product import Product
from app.models.user import User
from app.models.notification import Notification
from app.models.price_history import PriceHistory
from app.services.currency_service import convert
from app.services.email_service import send_alert_email, is_configured as email_is_configured
from app.services.scraper_service import refresh_price_from_source


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


def _refresh_prices_for_alerts(db: Session, product_ids: set[int]) -> int:
    """Re-scrape pretul pentru produsele referite de alertele active.

    Pentru fiecare produs din `product_ids`, incearca sa preia pretul curent
    de pe magazinul-sursa (Altex, eMAG, sole, FarmaciaTei, PCGarage). Daca
    obtine un pret nou, actualizeaza `Product.current_price` si adauga o
    intrare in `price_history`. Returneaza numarul de produse refrshate.
    """
    refreshed = 0
    for pid in product_ids:
        product = db.query(Product).filter(Product.id == pid).first()
        if not product:
            continue
        new_price = refresh_price_from_source(
            source=product.source,
            source_url=product.source_url,
            product_name=product.name,
            product_code=product.product_code,
        )
        if new_price is None:
            print(f"[AlertChecker] Nu am putut prelua pretul pentru \"{product.name[:50]}\" ({product.source}). Folosesc pretul stocat: {product.current_price} {product.currency}")
            continue
        old_price = product.current_price
        if old_price != new_price:
            product.current_price = new_price
            db.add(PriceHistory(
                product_id=product.id,
                price=new_price,
                currency=product.currency or "EUR",
                source=product.source,
            ))
            refreshed += 1
            print(f"[AlertChecker] Pret actualizat pentru \"{product.name[:50]}\": {old_price} -> {new_price} {product.currency}")
        else:
            # acelasi pret — nu adaugam istoric, doar log
            print(f"[AlertChecker] Pret neschimbat pentru \"{product.name[:50]}\": {new_price} {product.currency}")
    if refreshed > 0:
        db.commit()
    return refreshed


def check_alerts() -> int:
    """Compare product prices against active user alerts.

    Returns the number of alerts that were triggered in this run.
    """
    db: Session = SessionLocal()
    try:
        active_alerts = (
            db.query(Alert)
            .filter(Alert.is_active == True, Alert.is_triggered == False)
            .all()
        )

        # Pas 1: re-scrapeaza preturile produselor cu alerte active.
        product_ids = {a.product_id for a in active_alerts if a.product_id}
        if product_ids:
            print(f"[AlertChecker] Refresh preturi pentru {len(product_ids)} produs(e) cu alerte active...")
            _refresh_prices_for_alerts(db, product_ids)

        triggered_count = 0
        emails_sent = 0
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

        return triggered_count

    except Exception as e:
        print(f"[AlertChecker] Eroare: {e}")
        db.rollback()
        return 0
    finally:
        db.close()
