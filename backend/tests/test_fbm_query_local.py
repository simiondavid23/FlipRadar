"""FBM-1d — plasa locala de query pentru Facebook Marketplace.

Query-ul FBM pleaca si server-side, dar suportul lui pe pagina de CATEGORIE e
neconfirmat (dovedit ignorat pe propertyforsale, neverificat pe propertyrentals),
iar scanner-ul avea incredere oarba in sursa. Verificam ca `_matches_query_local`
se aplica acum si platformei facebook_marketplace, fara sa atinga celelalte cazuri.

Model de test: ca in test_sched2_platform_split — fixture-urile DB din conftest,
`_call_scraper` stubuit (fara retea) si cursul BNR fixat.
"""
import pytest

import app.services.real_estate_scanner as re_scanner
from app.services.real_estate_scanner import run_real_estate_scan


@pytest.fixture
def _fix_bnr(monkeypatch):
    # run_real_estate_scan face `from app.services.bnr_exchange import get_eur_ron`
    # LOCAL (in interiorul functiei) -> patch-uim modulul-sursa.
    monkeypatch.setattr("app.services.bnr_exchange.get_eur_ron", lambda: 5.0)


def _user(db, email):
    from app.models.user import User

    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _keyword(db, user, platform, query):
    from app.models.real_estate_monitor_keyword import RealEstateMonitorKeyword

    kw = RealEstateMonitorKeyword(
        user_id=user.id, name=f"kw_{platform}", platform=platform, is_active=True,
        query=query, tip_anunt="inchiriere", active_hours_start=None,
        active_hours_end=None, notify_discord=False, notify_email=False)
    db.add(kw)
    db.commit()
    return kw


# Doua carduri in forma emisa de search_facebook_real_estate. Primul poarta termenul
# cu DIACRITICE, ca sa exerseze si plierea din _norm_ascii (query-ul e fara).
_CARDURI = [
    {"external_id": "111", "title": "Garsonieră mobilată, Zorilor", "price": 350.0,
     "currency": "EUR", "location": "Cluj-Napoca", "url": "https://fb.test/111",
     "source_url": "https://fb.test/111", "thumbnail_url": "", "platform": "facebook_marketplace"},
    {"external_id": "222", "title": "Apartament 3 camere, Manastur", "price": 500.0,
     "currency": "EUR", "location": "Cluj-Napoca", "url": "https://fb.test/222",
     "source_url": "https://fb.test/222", "thumbnail_url": "", "platform": "facebook_marketplace"},
]


def _stub_scraper(monkeypatch, carduri=None):
    monkeypatch.setattr(re_scanner, "_call_scraper",
                        lambda kw, *a, **k: list(_CARDURI if carduri is None else carduri))


def _ext_ids(db, user):
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing

    return sorted(r.external_id for r in db.query(RealEstateMonitorListing)
                  .filter(RealEstateMonitorListing.user_id == user.id).all())


def test_fbm_query_local_respinge_cardul_nepotrivit(monkeypatch, _fix_bnr):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbm_query@example.com")
        _keyword(db, user, "facebook_marketplace", "garsoniera")
        _stub_scraper(monkeypatch)
        run_real_estate_scan(db, user_id=user.id, force_polling=True)
        # doar cardul al carui titlu contine termenul (pliat de diacritice) ramane
        assert _ext_ids(db, user) == ["111"]
    finally:
        db.close()


def test_fbm_query_gol_nu_filtreaza(monkeypatch, _fix_bnr):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbm_noquery@example.com")
        _keyword(db, user, "facebook_marketplace", None)
        _stub_scraper(monkeypatch)
        run_real_estate_scan(db, user_id=user.id, force_polling=True)
        assert _ext_ids(db, user) == ["111", "222"]
    finally:
        db.close()


def test_olx_ramane_nefiltrat_local(monkeypatch, _fix_bnr):
    # Control pe alta platforma: la OLX cautarea la sursa e confirmata, deci acelasi
    # query NU trebuie sa mai taie nimic local.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, "fbm_olx@example.com")
        _keyword(db, user, "olx", "garsoniera")
        _stub_scraper(monkeypatch)
        run_real_estate_scan(db, user_id=user.id, force_polling=True)
        assert _ext_ids(db, user) == ["111", "222"]
    finally:
        db.close()
