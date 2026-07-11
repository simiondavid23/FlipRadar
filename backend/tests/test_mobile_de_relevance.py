"""AA-7 — relevanta mobile.de: post-filtrul pur _relevant_title + guard-ul detail_fetched
(pattern Vinted) pe endpoint-ul de detaliu. auth_client din conftest + monkeypatch DETAIL_FETCHERS.
"""
from app.database import SessionLocal
from app.models.auto_feed_listing import AutoFeedListing
from app.scrapers.auto.listings.mobile_de_scraper import _relevant_title

_DETAIL_URL = "/api/auto-listings/feed/{}/detail"
_EMPTY = {"images": [], "description": None, "seller_name": None, "listed_at": None}


def _me_id(auth_client) -> int:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_mobilede(db, user_id):
    row = AutoFeedListing(user_id=user_id, platform="mobile_de", title="VW Passat 1.6 TDI",
                          price=15000, status="active",
                          url="https://suchen.mobile.de/fahrzeuge/details.html?id=123")
    db.add(row); db.commit(); db.refresh(row)
    return row.id


# ── post-filtru pur _relevant_title ─────────────────────────────────────────────────
def test_relevant_comma_dot():
    assert _relevant_title("VW Passat 1,6 TDI Comfortline", "Passat", "1.6 TDI") is True


def test_relevant_missing_model():
    assert _relevant_title("VW Golf 1.6 TDI", "Passat", "") is False


def test_relevant_missing_query_token():
    assert _relevant_title("VW Passat 2.0 TDI", "Passat", "1.6 TDI") is False


def test_relevant_empty_model_query():
    assert _relevant_title("Orice titlu, fara constrangeri", "", "") is True


def test_relevant_case_insensitive():
    assert _relevant_title("vw PASSAT 1.6 tdi kombi", "passat", "1.6 TDI") is True


# ── guard detail_fetched (pattern Vinted) pe endpoint ───────────────────────────────
def test_detail_fetched_ramane_false_pe_empty(auth_client, monkeypatch):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        lid = _mk_mobilede(db, uid)
    finally:
        db.close()
    from app.scrapers.auto.listings import detail as detail_mod
    monkeypatch.setitem(detail_mod.DETAIL_FETCHERS, "mobile_de", lambda url: dict(_EMPTY))
    r = auth_client.get(_DETAIL_URL.format(lid))
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id == lid).first().detail_fetched is False
    finally:
        db.close()


def test_detail_fetched_true_pe_descriere(auth_client, monkeypatch):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        lid = _mk_mobilede(db, uid)
    finally:
        db.close()
    from app.scrapers.auto.listings import detail as detail_mod
    monkeypatch.setitem(detail_mod.DETAIL_FETCHERS, "mobile_de",
                        lambda url: {**_EMPTY, "description": "Descriere reala din detaliu"})
    r = auth_client.get(_DETAIL_URL.format(lid))
    assert r.status_code == 200, r.text
    assert r.json().get("description") == "Descriere reala din detaliu"
    db = SessionLocal()
    try:
        assert db.query(AutoFeedListing).filter(AutoFeedListing.id == lid).first().detail_fetched is True
    finally:
        db.close()
