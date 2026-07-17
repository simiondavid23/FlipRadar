"""SCHED-1 — polling per (keyword, platforma) pentru joburile independente.

Teste PURE: fara DB, fara retea, fara sleep. Keyword-ul e un SimpleNamespace cu exact
atributele citite de helperi; `now` e injectat peste tot.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.radar_scanner import (
    RADAR_PLATFORMS, _PLATFORM_DELAY_RANGES,
    _mark_platform_scanned, _parse_platform_last_scan, _platform_scan_due,
)

_NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


def _kw(platform_last_scan=None, last_scan_at=None, poll=5):
    return SimpleNamespace(
        platform_last_scan=platform_last_scan,
        last_scan_at=last_scan_at,
        poll_interval_minutes=poll,
    )


def _js(**per_platform):
    """JSON-ul coloanei, din perechi platforma=datetime."""
    return json.dumps({p: t.isoformat() for p, t in per_platform.items()})


# ── _platform_scan_due ──────────────────────────────────────────────────────────
def test_keyword_nou_e_due():
    # Fara timestamp propriu si fara last_scan_at legacy -> prima scanare.
    assert _platform_scan_due(_kw(), "olx", now=_NOW) is True


def test_fallback_legacy_pe_last_scan_at_recent():
    # La deploy, randurile vechi au doar last_scan_at: NU trebuie sa porneasca toate
    # ca "prim-scan" (ar trage plafonul de prima scanare din RAD-1).
    kw = _kw(last_scan_at=_NOW - timedelta(minutes=2))
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


def test_fallback_legacy_pe_last_scan_at_vechi():
    kw = _kw(last_scan_at=_NOW - timedelta(minutes=30))
    assert _platform_scan_due(kw, "olx", now=_NOW) is True


def test_timestamp_propriu_recent_nu_e_due():
    kw = _kw(platform_last_scan=_js(olx=_NOW - timedelta(minutes=1)))
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


def test_timestamp_propriu_vechi_e_due():
    kw = _kw(platform_last_scan=_js(olx=_NOW - timedelta(minutes=10)))
    assert _platform_scan_due(kw, "olx", now=_NOW) is True


def test_exact_pe_interval_e_due():
    # Comparatia e ">=" -> fix la interval scanarea porneste.
    kw = _kw(platform_last_scan=_js(olx=_NOW - timedelta(minutes=5)), poll=5)
    assert _platform_scan_due(kw, "olx", now=_NOW) is True


def test_platformele_sunt_independente():
    # Miezul SCHED-1: Vinted scanat acum nu blocheaza OLX-ul.
    kw = _kw(platform_last_scan=_js(vinted=_NOW - timedelta(seconds=30)))
    assert _platform_scan_due(kw, "vinted", now=_NOW) is False
    assert _platform_scan_due(kw, "olx", now=_NOW) is True


def test_alta_platforma_recenta_nu_influenteaza_fallback_ul():
    # Vinted are timestamp propriu; OLX cade pe legacy, nu pe timestamp-ul Vinted.
    kw = _kw(platform_last_scan=_js(vinted=_NOW - timedelta(seconds=30)),
             last_scan_at=_NOW - timedelta(minutes=1))
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


def test_json_corupt_e_tratat_ca_gol():
    kw = _kw(platform_last_scan="{nu e json", last_scan_at=_NOW - timedelta(minutes=1))
    assert _parse_platform_last_scan(kw) == {}
    assert _platform_scan_due(kw, "olx", now=_NOW) is False  # cade pe legacy


def test_json_de_alt_tip_e_tratat_ca_gol():
    assert _parse_platform_last_scan(_kw(platform_last_scan="[1, 2]")) == {}


def test_timestamp_corupt_cade_pe_legacy():
    kw = _kw(platform_last_scan=json.dumps({"olx": "nu-i o data"}),
             last_scan_at=_NOW - timedelta(minutes=1))
    # fromisoformat crapa -> last=None -> due (nu arunca)
    assert _platform_scan_due(kw, "olx", now=_NOW) is True


def test_last_scan_at_naiv_e_tratat_ca_utc():
    kw = _kw(last_scan_at=(_NOW - timedelta(minutes=1)).replace(tzinfo=None))
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


def test_poll_interval_none_cade_pe_5_minute():
    kw = _kw(platform_last_scan=_js(olx=_NOW - timedelta(minutes=4)), poll=None)
    assert _platform_scan_due(kw, "olx", now=_NOW) is False
    kw2 = _kw(platform_last_scan=_js(olx=_NOW - timedelta(minutes=6)), poll=None)
    assert _platform_scan_due(kw2, "olx", now=_NOW) is True


# ── _mark_platform_scanned ──────────────────────────────────────────────────────
def test_mark_roundtrip():
    kw = _kw()
    _mark_platform_scanned(kw, "olx", now=_NOW)
    assert _parse_platform_last_scan(kw) == {"olx": _NOW.isoformat()}
    assert _platform_scan_due(kw, "olx", now=_NOW) is False


def test_mark_actualizeaza_si_last_scan_at():
    kw = _kw()
    _mark_platform_scanned(kw, "olx", now=_NOW)
    assert kw.last_scan_at == _NOW


def test_mark_pastreaza_celelalte_platforme():
    vechi = _NOW - timedelta(hours=2)
    kw = _kw(platform_last_scan=_js(vinted=vechi))
    _mark_platform_scanned(kw, "olx", now=_NOW)
    d = _parse_platform_last_scan(kw)
    assert d == {"vinted": vechi.isoformat(), "olx": _NOW.isoformat()}


def test_mark_suprascrie_aceeasi_platforma():
    kw = _kw(platform_last_scan=_js(olx=_NOW - timedelta(hours=1)))
    _mark_platform_scanned(kw, "olx", now=_NOW)
    assert _parse_platform_last_scan(kw) == {"olx": _NOW.isoformat()}


def test_mark_peste_json_corupt_nu_crapa():
    kw = _kw(platform_last_scan="{stricat")
    _mark_platform_scanned(kw, "olx", now=_NOW)
    assert _parse_platform_last_scan(kw) == {"olx": _NOW.isoformat()}


# ── Sincronizarea listei de platforme ───────────────────────────────────────────
def test_radar_platforms_sincron_cu_delay_ranges():
    # Fiecare platforma cu job trebuie sa aiba delay-ul ei de paginare (si invers).
    assert set(RADAR_PLATFORMS) == set(_PLATFORM_DELAY_RANGES)


def test_radar_platforms_fara_duplicate():
    assert len(RADAR_PLATFORMS) == len(set(RADAR_PLATFORMS)) == 8
