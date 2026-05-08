"""SMTP email service.

Configured via env vars (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM).
If SMTP_HOST is empty, send_email() returns False without raising — the rest
of the app keeps working without email. This keeps email an opt-in feature.
"""
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_email(to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Send an email via configured SMTP server. Returns True on success."""
    if not is_configured():
        print("[Email] SMTP nu este configurat - email omis.")
        return False
    if not to:
        return False

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        print(f"[Email] Trimis catre {to}: {subject}")
        return True
    except Exception as exc:
        print(f"[Email] Eroare la trimitere catre {to}: {exc}")
        return False


def send_alert_email(to: str, product_name: str, current_price: float,
                      target_price: float, currency: str, direction: str,
                      product_link: Optional[str] = None) -> bool:
    """Send an alert email when a price alert triggers."""
    subject = f"FlipRadar: alerta pret pentru {product_name[:60]}"
    text = (
        f"Salut!\n\n"
        f"Pretul produsului \"{product_name}\" {direction} tinta ta.\n\n"
        f"Pret curent: {current_price:.2f} {currency}\n"
        f"Tinta: {target_price:.2f} {currency}\n"
    )
    if product_link:
        text += f"\nVezi produsul: {product_link}\n"
    text += "\n-- FlipRadar"

    html = f"""\
<html><body style="font-family: Arial, sans-serif; color: #0f172a;">
  <h2 style="color: #2563eb;">Alerta pret FlipRadar</h2>
  <p>Pretul produsului <strong>{product_name}</strong> {direction} tinta ta.</p>
  <table style="border-collapse: collapse; margin-top: 12px;">
    <tr><td style="padding: 6px 12px; background: #f1f5f9;">Pret curent</td>
        <td style="padding: 6px 12px; font-weight: bold;">{current_price:.2f} {currency}</td></tr>
    <tr><td style="padding: 6px 12px; background: #f1f5f9;">Tinta</td>
        <td style="padding: 6px 12px;">{target_price:.2f} {currency}</td></tr>
  </table>
  {f'<p style="margin-top: 16px;"><a href="{product_link}" style="color: #2563eb;">Vezi produsul in FlipRadar</a></p>' if product_link else ''}
  <p style="margin-top: 24px; font-size: 12px; color: #64748b;">-- FlipRadar</p>
</body></html>"""
    return send_email(to, subject, text, html)
