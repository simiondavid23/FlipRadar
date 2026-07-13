"""MON-TZ — serializare UTC explicita (sufix "Z") pentru timestamp-urile de server.

Timestamp-urile generate de server sunt stocate ca UTC dar naiv (fara tzinfo);
fara sufix, frontend-ul (`new Date(...)`) le interpreteaza ca ora locala -> decalaj.
`UTCDateTime` (app/schemas/_types.py) le serializeaza cu sufix "Z".

Acopera:
- helperul pur `_to_utc_iso` (naiv -> UTC/Z, aware -> convertit la UTC + Z);
- serializarea la nivel de schema (AlertResponse).
"""
from datetime import datetime, timezone, timedelta

from app.schemas._types import _to_utc_iso
from app.schemas.alert import AlertResponse


# ── 1. Unitar pe _to_utc_iso ─────────────────────────────────────────────────
def test_to_utc_iso_naiv_primeste_sufix_Z():
    # datetime naiv = presupus UTC -> ISO cu sufix "Z", nu "+00:00".
    out = _to_utc_iso(datetime(2026, 7, 12, 9, 30, 0))
    assert out == "2026-07-12T09:30:00Z"
    assert out.endswith("Z")
    assert "+00:00" not in out


def test_to_utc_iso_aware_convertit_la_utc():
    # 12:30 la +03:00 == 09:30 UTC -> ora scazuta cu 3, sufix "Z".
    aware = datetime(2026, 7, 12, 12, 30, 0, tzinfo=timezone(timedelta(hours=3)))
    out = _to_utc_iso(aware)
    assert out == "2026-07-12T09:30:00Z"
    assert out.endswith("Z")


# ── 2. Serializare la nivel de schema ────────────────────────────────────────
def _alert(created_at, triggered_at):
    return AlertResponse(
        id=1, user_id=1, product_id=1, target_price=1.0, currency="EUR",
        alert_type="price_drop", is_active=True, is_triggered=False,
        triggered_at=triggered_at, created_at=created_at, product=None,
    )


def test_alert_response_json_are_sufix_Z():
    body = _alert(datetime(2026, 7, 12, 9, 30, 0), None).model_dump_json()
    assert '"created_at":"2026-07-12T09:30:00Z"' in body


def test_alert_response_triggered_at_none_ramane_null():
    # Optional[UTCDateTime] = None -> null in JSON, fara eroare de serializare.
    body = _alert(datetime(2026, 7, 12, 9, 30, 0), None).model_dump_json()
    assert '"triggered_at":null' in body


def test_alert_response_triggered_at_setat_primeste_Z():
    body = _alert(
        datetime(2026, 7, 12, 9, 30, 0), datetime(2026, 7, 12, 10, 0, 0)
    ).model_dump_json()
    assert '"triggered_at":"2026-07-12T10:00:00Z"' in body
