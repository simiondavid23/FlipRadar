"""Discord webhook delivery pentru alertele Radar.

Three-tier routing: webhook_all primeste TOATE deal-urile (daca e configurat),
webhook_buy_now primeste doar grade A si B (deal-uri prioritare), webhook_maybe
primeste C si D (deal-uri marginale). Userul poate configura oricate (sau zero).
"""
from typing import Optional
import requests


_SCORE_COLORS = {
    "A": 0x00FF00,
    "B": 0x3B82F6,
    "C": 0xFACC15,
    "D": 0xF97316,
}

_PLATFORM_LABEL = {
    "olx": "OLX",
    "vinted": "Vinted",
    "okazii": "Okazii",
    "facebook": "Facebook Marketplace",
}


def _fmt_dt(dt) -> str:
    if not dt:
        return "Necunoscut"
    try:
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "Necunoscut"


def _build_embed(
    listing: dict,
    keyword_name: str,
    score: str,
    resale_price: float,
    margin_pct: float,
    listed_at=None,
    found_at=None,
) -> dict:
    title = listing.get("title", "")[:240]
    color = _SCORE_COLORS.get(score, 0x64748B)
    platform_label = _PLATFORM_LABEL.get(listing.get("platform", ""), listing.get("platform", "?"))

    description = (
        f"💰 Cerut: **{listing.get('price', 0)} {listing.get('currency', 'RON')}** | "
        f"🎯 Revânzare: **{resale_price:.0f} RON** | "
        f"📈 Marjă: **{margin_pct:.0f}%**"
    )

    fields = [
        {"name": "Platformă", "value": platform_label, "inline": True},
        {"name": "Keyword", "value": keyword_name, "inline": True},
    ]
    if listing.get("location"):
        fields.append({"name": "Locație", "value": str(listing["location"])[:200], "inline": True})
    fields.append({"name": "📅 Postat pe platformă", "value": _fmt_dt(listed_at), "inline": True})
    fields.append({"name": "🔍 Găsit de FlipRadar", "value": _fmt_dt(found_at), "inline": True})

    embed = {
        "title": f"[{score}] {title}",
        "description": description,
        "color": color,
        "url": listing.get("url"),
        "fields": fields,
    }
    images = listing.get("images") or []
    if images:
        embed["thumbnail"] = {"url": images[0]}
    return embed


def send_discord_alert(
    webhook_url: str,
    listing: dict,
    keyword_name: str,
    score: str,
    resale_price: float,
    margin_pct: float,
    listed_at=None,
    found_at=None,
) -> bool:
    """POST la webhook. True daca status 200/204."""
    if not webhook_url:
        return False
    embed = _build_embed(listing, keyword_name, score, resale_price, margin_pct, listed_at, found_at)
    payload = {"embeds": [embed]}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True
        print(f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as exc:
        print(f"[Discord] Eroare la trimitere: {exc}")
        return False


def route_discord_alerts(
    settings,
    listing: dict,
    keyword_name: str,
    score: str,
    resale_price: float,
    margin_pct: float,
    listed_at=None,
    found_at=None,
) -> int:
    """Trimite la webhook-urile potrivite in functie de scor. Returneaza nr. de notificari trimise."""
    if not settings:
        return 0
    sent = 0
    if settings.discord_webhook_all:
        if send_discord_alert(settings.discord_webhook_all, listing, keyword_name, score, resale_price, margin_pct, listed_at, found_at):
            sent += 1
    if score in ("A", "B") and settings.discord_webhook_buy_now:
        if send_discord_alert(settings.discord_webhook_buy_now, listing, keyword_name, score, resale_price, margin_pct, listed_at, found_at):
            sent += 1
    if score in ("C", "D") and settings.discord_webhook_maybe:
        if send_discord_alert(settings.discord_webhook_maybe, listing, keyword_name, score, resale_price, margin_pct, listed_at, found_at):
            sent += 1
    return sent


def send_test_message(webhook_url: str) -> bool:
    """Trimite un mesaj test la webhook ca sa verifice configurarea."""
    if not webhook_url:
        return False
    payload = {
        "embeds": [{
            "title": "Test FlipRadar Radar",
            "description": "Acesta este un mesaj test. Webhook-ul Discord funcționează corect.",
            "color": 0x2563EB,
        }]
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as exc:
        print(f"[Discord] Test eroare: {exc}")
        return False
