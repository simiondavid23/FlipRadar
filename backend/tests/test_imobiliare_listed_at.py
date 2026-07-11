"""IM-7 — data postarii (listed_at): parser pur OLX + seed + split locatie/data. Toate pure."""
from datetime import datetime

from app.scrapers.real_estate.olx_real_estate import _parse_olx_date
from app.services.real_estate_scanner import _seed_from_raw

_NOW = datetime(2026, 7, 11, 15, 0, 0)


def test_parse_azi():
    assert _parse_olx_date("Azi la 14:30", _NOW) == datetime(2026, 7, 11, 14, 30)


def test_parse_ieri():
    assert _parse_olx_date("Ieri la 09:05", _NOW) == datetime(2026, 7, 10, 9, 5)


def test_parse_data_plina():
    # ora lipsa -> 00:00
    assert _parse_olx_date("11 iulie 2026", _NOW) == datetime(2026, 7, 11, 0, 0)


def test_parse_diacritice_si_case():
    # "3 Martie 2026" si varianta cu diacritice in luna -> identic (NFKD normalizeaza)
    ref = datetime(2026, 3, 3, 0, 0)
    assert _parse_olx_date("3 Martie 2026", _NOW) == ref
    assert _parse_olx_date("3 Mărţie 2026", _NOW) == ref


def test_parse_necunoscut_none():
    assert _parse_olx_date("Reactualizat azi", _NOW) is None   # nu incepe cu azi/ieri, fara data plina
    assert _parse_olx_date("", _NOW) is None
    assert _parse_olx_date(None, _NOW) is None


def test_seed_listed_at():
    # raw cu listed_at ISO -> datetime in seed
    assert _seed_from_raw({"listed_at": "2026-07-11T14:30:00"})["listed_at"] == datetime(2026, 7, 11, 14, 30)
    # string invalid -> None (try/except)
    assert _seed_from_raw({"listed_at": "not-a-date"})["listed_at"] is None
    # lipsa -> None
    assert _seed_from_raw({})["listed_at"] is None


def test_split_locatie_data():
    # split pe " - " cu maxsplit=1: locatia cu cratima interna ramane intacta, data se extrage
    raw = "Cluj-Napoca - Azi la 10:00"
    parts = raw.split(" - ", 1)
    assert parts[0].strip() == "Cluj-Napoca"
    assert _parse_olx_date(parts[1], _NOW) == datetime(2026, 7, 11, 10, 0)
