"""SCHED-2 — joburile per platforma la Auto Anunturi + Imobiliare Monitor.

Teste la nivel de serviciu (fixture-urile DB din conftest), fara retea: `_call_scraper`
e stubuit si doar inregistreaza platforma keyword-ului scanat, iar cursul BNR e fixat
(run_real_estate_scan il cere la fiecare scan, prin import local).

Miezul verificat: `platform=X` scaneaza DOAR keyword-urile platformei X; `platform=None`
(scan-now manual / comportamentul vechi) le scaneaza pe toate.
"""
import pytest

import app.services.auto_listings_scanner as auto_scanner
import app.services.real_estate_scanner as re_scanner
from app.services.auto_listings_scanner import AUTO_PLATFORMS, run_auto_scan
from app.services.real_estate_scanner import RE_PLATFORMS, run_real_estate_scan


@pytest.fixture
def _fix_bnr(monkeypatch):
    # run_real_estate_scan face `from app.services.bnr_exchange import get_eur_ron`
    # LOCAL (in interiorul functiei) -> patch-uim modulul-sursa (ca in test_scorer_imobiliare).
    monkeypatch.setattr("app.services.bnr_exchange.get_eur_ron", lambda: 5.0)


def _user(db, email="sched2@example.com"):
    from app.models.user import User

    # username derivat din email — `users.username` are index unic, iar un test
    # poate crea doi useri (vezi test_auto_platforma_si_user_id_se_combina).
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _spy(monkeypatch, module):
    """Stub pe _call_scraper: inregistreaza platforma fiecarui keyword scanat, nu scaneaza."""
    scanate = []

    def _fals(kw, *a, **k):
        scanate.append(kw.platform)
        return []

    monkeypatch.setattr(module, "_call_scraper", _fals)
    return scanate


# ── Auto Anunturi ───────────────────────────────────────────────────────────────
def _seed_auto(db):
    """Doua keyword-uri active, pe platforme diferite, fara interval orar.
    resale_price ramane None ca _resale_price_ron sa nu ceara cursul BNR (retea)."""
    from app.models.auto_keyword import AutoKeyword

    user = _user(db, "sched2_auto@example.com")
    for p in ("autovit", "olx_auto"):
        db.add(AutoKeyword(user_id=user.id, name=f"kw_{p}", platform=p, is_active=True,
                           active_hours_start=None, active_hours_end=None))
    db.commit()
    return user


def test_auto_jobul_platformei_scaneaza_doar_platforma_lui(monkeypatch):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_auto(db)
        scanate = _spy(monkeypatch, auto_scanner)
        run_auto_scan(db, platform="autovit")
        assert scanate == ["autovit"], f"jobul autovit a atins si: {scanate}"
    finally:
        db.close()


def test_auto_fara_platforma_le_scaneaza_pe_toate(monkeypatch):
    # platform=None = scan-now manual / comportamentul de dinainte de SCHED-2.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_auto(db)
        scanate = _spy(monkeypatch, auto_scanner)
        run_auto_scan(db)
        assert sorted(scanate) == ["autovit", "olx_auto"]
    finally:
        db.close()


def test_auto_platforma_fara_keyword_uri_nu_scaneaza_nimic(monkeypatch):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_auto(db)
        scanate = _spy(monkeypatch, auto_scanner)
        run_auto_scan(db, platform="mobile_de")
        assert scanate == []
    finally:
        db.close()


def test_auto_platforma_si_user_id_se_combina(monkeypatch):
    # Filtrele sunt cumulative: alt user -> niciun keyword, chiar daca platforma exista.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_auto(db)
        altul = _user(db, "sched2_alt@example.com")
        db.commit()
        scanate = _spy(monkeypatch, auto_scanner)
        run_auto_scan(db, user_id=altul.id, platform="autovit")
        assert scanate == []
    finally:
        db.close()


# ── Imobiliare Monitor ──────────────────────────────────────────────────────────
def _seed_re(db):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    user = _user(db, "sched2_re@example.com")
    for p in ("storia", "olx"):
        db.add(RealEstateMonitorKeyword(user_id=user.id, name=f"kw_{p}", platform=p,
                                        is_active=True, active_hours_start=None,
                                        active_hours_end=None))
    db.commit()
    return user


def test_re_jobul_platformei_scaneaza_doar_platforma_lui(monkeypatch, _fix_bnr):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_re(db)
        scanate = _spy(monkeypatch, re_scanner)
        run_real_estate_scan(db, platform="storia", force_polling=True)
        assert scanate == ["storia"], f"jobul storia a atins si: {scanate}"
    finally:
        db.close()


def test_re_fara_platforma_le_scaneaza_pe_toate(monkeypatch, _fix_bnr):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_re(db)
        scanate = _spy(monkeypatch, re_scanner)
        run_real_estate_scan(db, force_polling=True)
        assert sorted(scanate) == ["olx", "storia"]
    finally:
        db.close()


def test_re_polling_ul_ramane_autoritatea_scadentei(monkeypatch, _fix_bnr):
    # Jobul platformei doar RESTRANGE multimea; fara force_polling, un keyword
    # nescadent (tocmai scanat) nu e atins nici de jobul platformei lui.
    from datetime import datetime, timezone

    from app.database import SessionLocal
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    db = SessionLocal()
    try:
        user = _seed_re(db)
        kw = (db.query(RealEstateMonitorKeyword)
              .filter(RealEstateMonitorKeyword.user_id == user.id,
                      RealEstateMonitorKeyword.platform == "storia").first())
        kw.last_scan_at = datetime.now(timezone.utc)   # tocmai scanat -> nescadent
        db.commit()
        scanate = _spy(monkeypatch, re_scanner)
        run_real_estate_scan(db, platform="storia")
        assert scanate == []
    finally:
        db.close()


# ── Santinele: listele trebuie sa ramana sincrone cu ramurile din _call_scraper ──
def test_auto_platforms_pinuit():
    assert AUTO_PLATFORMS == ["autovit", "olx_auto", "mobile_de", "autoscout24",
                              "facebook_auto", "kleinanzeigen_auto"]


def test_re_platforms_pinuit():
    assert RE_PLATFORMS == ["olx", "storia", "imobiliare_ro",
                            "facebook_marketplace", "facebook_groups"]
