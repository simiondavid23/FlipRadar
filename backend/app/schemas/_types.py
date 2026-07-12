"""Tipuri partajate pentru schemele Pydantic.

UTCDateTime: serializeaza datetime-uri stocate ca UTC (naive sau aware) in format
ISO cu sufix explicit "Z", ca frontend-ul sa le interpreteze corect ca UTC.

ATENTIE: se aplica DOAR campurilor generate de server in UTC (created_at,
updated_at, triggered_at, added_at, recorded_at, last_checked_at etc.).
NU se aplica datelor de domeniu in ora locala (listed_at, posted_at,
auction_date) si nici datelor de business introduse de utilizator
(purchased_at, sold_at).
"""
from datetime import datetime, timezone
from typing import Annotated
from pydantic import PlainSerializer


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str, when_used="json")]
