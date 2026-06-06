"""Web Push notifications cu VAPID (pywebpush).

Sare elegant peste daca pywebpush nu e instalat sau VAPID keys lipsesc —
restul aplicatiei nu observa nimic. Subscriptions expirate (HTTP 410) sunt
sterse automat din DB ca sa nu polueze tabelul cu endpoint-uri moarte.
"""
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS_EMAIL
from app.models.push_subscription import PushSubscription


def is_push_configured() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def send_push_notification(subscription: PushSubscription, title: str, body: str, url: str = "/") -> bool:
    """Trimite o singura notificare. Returneaza True daca delivery a reusit."""
    if not is_push_configured():
        return False
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[Push] pywebpush nu e instalat — skip.")
        return False

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/flipradar-logo.svg",
    }, ensure_ascii=False)

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"},
        )
        return True
    except WebPushException as exc:
        # 410 Gone = subscription expirat — semnalam la apelant ca sa-l stearga.
        code = getattr(exc.response, "status_code", None) if getattr(exc, "response", None) else None
        if code == 410:
            print(f"[Push] Subscription expirat ({subscription.endpoint[:50]}...) — va fi sters.")
            raise _SubscriptionGone()
        print(f"[Push] WebPushException: {exc}")
        return False
    except Exception as exc:
        print(f"[Push] Eroare: {exc}")
        return False


class _SubscriptionGone(Exception):
    """Marker intern — apelantul stie sa stearga subscription-ul."""
    pass


def notify_user_push(db: Session, user_id: int, title: str, body: str, url: str = "/") -> int:
    """Trimite la toate subscriptions ale userului. Returneaza nr. de succese."""
    if not is_push_configured():
        return 0
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not subs:
        return 0
    sent = 0
    to_delete = []
    for sub in subs:
        try:
            ok = send_push_notification(sub, title, body, url)
            if ok:
                sent += 1
        except _SubscriptionGone:
            to_delete.append(sub.id)
    if to_delete:
        db.query(PushSubscription).filter(PushSubscription.id.in_(to_delete)).delete(synchronize_session=False)
        db.commit()
    return sent
