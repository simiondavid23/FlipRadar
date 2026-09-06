"""Mesaje Discord de SERVICIU pentru Radar: testul de webhook din Setari si alertele
de sistem (backup, watchdog-uri, sesiune Facebook).

FRONT-1b: alertele de DEAL nu mai trec pe aici. Rutarea pe trei niveluri
(all / buy_now / maybe) traieste in `app/services/discord_service.send_radar_notification`,
cu coada globala, rate-limit si dedup; embed-ul de deal se construieste acolo, in
`build_radar_embed`. Ce era aici era un duplicat ramas fara apelanti.
"""
import requests


# FRONT-1b: `_fmt_dt`, `_build_embed`, `send_discord_alert` si `route_discord_alerts`
# au disparut de aici. Erau calea VECHE de alerte Radar (rutare pe trei webhook-uri,
# embed bogat) si nu mai erau apelate de nimeni: scanner-ul trece de mult prin
# `app/services/discord_service.send_radar_notification` (coada globala, rate-limit +
# dedup), care isi construieste embed-ul cu `build_radar_embed`. FRONT-1b a mutat acolo
# campurile de data, deci duplicatul n-avea de ce sa mai existe.
#
# Modulul RAMANE: `send_test_message` (routers/radar.py) si `send_system_alert`
# (backup_service, catalog_health_watchdog, facebook_group_service, radar/health_watchdog)
# sunt vii, cu cinci apelanti in total.


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


def send_system_alert(webhook_url: str, text: str) -> bool:
    """Mesaj simplu de sistem (watchdog) la webhook. True daca status 200/204."""
    if not webhook_url:
        return False
    payload = {"content": text}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as exc:
        print(f"[Discord] System alert eroare: {exc}")
        return False
