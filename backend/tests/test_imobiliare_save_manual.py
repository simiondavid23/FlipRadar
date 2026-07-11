"""IM-5 — salvările din Căutarea Manuală intră în tabelul MONITOR (real_estate_listings)
cu status="saved"; + endpointul vechi /api/real-estate/search cu facebook nu mai crapă.

Aceleași fixtures/stil ca testele IM-2/IM-3 (auth_client din conftest, inserare/citire directă
în DB pentru verificare).
"""
from app.database import SessionLocal
from app.models.user import User
from app.models.real_estate_monitor_listing import RealEstateMonitorListing as RealEstateListing

_SAVE = "/api/real-estate-monitor/listings/save-manual"


def _me_id(auth_client) -> int:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _get(db, listing_id):
    return db.query(RealEstateListing).filter(RealEstateListing.id == listing_id).first()


def test_save_manual_creeaza_monitor_saved(auth_client):
    payload = {"platform": "olx", "external_id": "olx-123", "tip_anunt": "inchiriere",
               "tip_proprietate": "apartament", "camere": 2, "suprafata_mp": 55, "etaj": "3",
               "pret": 350, "moneda": "EUR", "locatie_oras": "Cluj-Napoca",
               "titlu": "Apartament 2 camere", "descriere": "zona buna",
               "source_url": "https://olx.ro/d/olx-123"}
    r = auth_client.post(_SAVE, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["existing"] is False
    db = SessionLocal()
    try:
        li = _get(db, body["id"])
        assert li is not None
        assert li.status == "saved"
        assert li.source == "manual"
        assert li.keyword_id is None
        assert li.platform == "olx"
        assert li.rooms == 2 and li.area_sqm == 55
        assert float(li.price) == 350.0
    finally:
        db.close()


def test_save_manual_normalizeaza_platforma(auth_client):
    r = auth_client.post(_SAVE, json={"platform": "imobiliare", "external_id": "im-1",
                                      "titlu": "Casă"})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert _get(db, r.json()["id"]).platform == "imobiliare_ro"
    finally:
        db.close()


def test_save_manual_idempotent(auth_client):
    payload = {"platform": "olx", "external_id": "dup-1", "titlu": "Anunț"}
    r1 = auth_client.post(_SAVE, json=payload)
    assert r1.status_code == 200, r1.text
    lid = r1.json()["id"]
    assert r1.json()["existing"] is False
    # între timp userul îl ignoră
    db = SessionLocal()
    try:
        li = _get(db, lid); li.status = "ignored"; db.commit()
    finally:
        db.close()
    # a doua salvare -> același rând, existing=True, redevine "saved"
    r2 = auth_client.post(_SAVE, json=payload)
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == lid
    assert r2.json()["existing"] is True
    db = SessionLocal()
    try:
        assert _get(db, lid).status == "saved"
        cnt = db.query(RealEstateListing).filter(
            RealEstateListing.external_id == "dup-1", RealEstateListing.platform == "olx").count()
        assert cnt == 1   # un singur rând
    finally:
        db.close()


def test_save_manual_fallback_external_id(auth_client):
    # fără external_id, cu source_url -> external_id = source_url
    url = "https://storia.ro/ap-xyz"
    r = auth_client.post(_SAVE, json={"platform": "storia", "source_url": url, "titlu": "X"})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert _get(db, r.json()["id"]).external_id == url
    finally:
        db.close()
    # fără external_id ȘI fără source_url -> 422
    r2 = auth_client.post(_SAVE, json={"platform": "storia", "titlu": "Fără id"})
    assert r2.status_code == 422


def test_save_manual_extract_din_titlu(auth_client):
    # fără camere/suprafață în payload -> fallback regex (extract_all, IM-1)
    r = auth_client.post(_SAVE, json={"platform": "olx", "external_id": "ex-25",
                                      "titlu": "Garsoniera 25 mp etaj 2, Floreasca"})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        li = _get(db, r.json()["id"])
        assert li.rooms == 1        # "garsoniera" -> 1 cameră
        assert li.area_sqm == 25    # "25 mp"
    finally:
        db.close()


def test_save_manual_scopat_pe_user(auth_client):
    uid = _me_id(auth_client)
    db = SessionLocal()
    try:
        other = User(email="other_im5@example.com", username="other_im5", hashed_password="x")
        db.add(other); db.commit(); db.refresh(other)
        other_id = other.id   # capturam ca int (obiectul devine detached dupa close)
        # B are deja un rând cu același (platform, external_id)
        b_row = RealEstateListing(user_id=other_id, platform="olx", external_id="shared-ext",
                                  title="Al lui B", status="saved", source="manual")
        db.add(b_row); db.commit(); db.refresh(b_row)
        b_id = b_row.id
    finally:
        db.close()
    # A salvează același external_id -> rând NOU al lui A (idempotența e scopată pe user)
    r = auth_client.post(_SAVE, json={"platform": "olx", "external_id": "shared-ext",
                                      "titlu": "Al lui A"})
    assert r.status_code == 200, r.text
    assert r.json()["existing"] is False   # nu a "prins" rândul lui B
    assert r.json()["id"] != b_id
    db = SessionLocal()
    try:
        assert _get(db, r.json()["id"]).user_id == uid
        b_after = _get(db, b_id)
        assert b_after.user_id == other_id and b_after.title == "Al lui B"   # B neatins
    finally:
        db.close()


def test_search_vechi_facebook_nu_crapa(auth_client):
    # facebook scos din builders -> selected gol -> early return, fără apel de rețea, fără 500
    r = auth_client.get("/api/real-estate/search", params={"platforms": "facebook"})
    assert r.status_code == 200, r.text
    assert r.json() == {"results": [], "by_platform": {}, "count": 0}
