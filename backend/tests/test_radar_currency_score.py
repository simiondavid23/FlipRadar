"""RADAR-CUR — scorul Radar se calculeaza in RON, indiferent de moneda anuntului.

`kw.resale_price` e MEREU in RON (RadarKeyword nu are coloana de moneda, iar UI-ul
scrie "X RON revanzare"). Pana la fix, pretul BRUT al anuntului intra in
calculate_score, deci un anunt cotat in EUR (Facebook, uneori Vinted) era comparat
cifra-la-cifra cu un pret de revanzare in RON: 500 EUR "comparat" cu 4000 RON dadea
87.5% marja (grad A fals) in loc de 37.5% cat e real la 5 lei/euro, iar un anunt de
900 EUR (4500 RON, deci in pierdere) primea grad A si alerta.

Fix: `_price_to_ron` aduce pretul in RON cu cursul BNR luat O SINGURA DATA pe scan;
pretul persistat si comparatiile de scadere raman pe valorile BRUTE.

Testele nu ating reteaua: get_eur_ron e monkeypatch-uit cu un curs fix (5.0).
"""
import json
import types
import uuid

import pytest

from app.utils import radar_scanner as rs


# ── _price_to_ron: functie pura, fara DB/retea ───────────────────────────────────

def test_ron_ramane_neschimbat():
    assert rs._price_to_ron(250.0, "RON", 5.0) == 250.0
    assert rs._price_to_ron(250.0, "ron", 5.0) == 250.0     # case-insensitive


def test_moneda_absenta_ramane_neschimbata():
    # Conventia scraperelor: lipsa monedei inseamna RON.
    assert rs._price_to_ron(250.0, None, 5.0) == 250.0
    assert rs._price_to_ron(250.0, "", 5.0) == 250.0


def test_eur_se_inmulteste_cu_cursul():
    assert rs._price_to_ron(100.0, "EUR", 5.0) == 500.0
    assert rs._price_to_ron(100.0, "eur", 4.97) == pytest.approx(497.0)


def test_moneda_necunoscuta_ramane_neconvertita_si_avertizeaza_o_singura_data(monkeypatch):
    logs = []
    monkeypatch.setattr(rs.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)))
    rs._unknown_currency_warned.clear()
    try:
        # Fail-open: mai bine un scor aproximativ decat un anunt aruncat.
        assert rs._price_to_ron(100.0, "USD", 5.0) == 100.0
        assert rs._price_to_ron(200.0, "USD", 5.0) == 200.0
        warns = [m for lvl, m in logs if lvl == "WARN"]
        assert len(warns) == 1                  # un singur WARN pe scan, per moneda
        assert "USD" in warns[0]
    finally:
        rs._unknown_currency_warned.clear()


def test_pret_absent_sau_neparsabil_da_none():
    assert rs._price_to_ron(None, "RON", 5.0) is None
    assert rs._price_to_ron("", "EUR", 5.0) is None
    assert rs._price_to_ron("n/a", "RON", 5.0) is None


def test_pret_string_parsabil():
    assert rs._price_to_ron("100", "RON", 5.0) == 100.0
    assert rs._price_to_ron("100.5", "EUR", 5.0) == pytest.approx(502.5)


def test_fara_curs_valid_pretul_ramane_brut():
    # BNR indisponibil (eur_ron None) -> fail-open, la fel ca la moneda necunoscuta.
    assert rs._price_to_ron(100.0, "EUR", None) == 100.0


# ── infrastructura pentru scanul propriu-zis ─────────────────────────────────────

def _mk_keyword(auth_client, resale_price: float) -> int:
    r = auth_client.post("/api/radar/keywords", json={
        "name": f"kw {uuid.uuid4().hex[:6]}",
        "max_price": 100000.0,
        "resale_price": resale_price,     # in RON, ca peste tot in Radar
        "platforms": ["facebook"],
        "notify_email": False,
        "notify_discord": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _enable_facebook(uid: int) -> None:
    """Facebook e dezactivat implicit in RadarSettings — altfel scanul il sare."""
    from app.database import SessionLocal
    from app.models.radar_settings import RadarSettings
    db = SessionLocal()
    try:
        s = db.query(RadarSettings).filter(RadarSettings.user_id == uid).first()
        if s is None:
            s = RadarSettings(user_id=uid)
            db.add(s)
        s.platform_facebook_enabled = True
        db.commit()
    finally:
        db.close()


def _fb_listing(ext: str, price: float, currency: str) -> dict:
    return {
        "external_id": ext,
        "title": "Bicicleta de test",
        "price": price,
        "currency": currency,
        "url": "https://facebook.com/marketplace/item/1",
        "images": ["https://img/x.jpg"],
        "location": "București",
        "platform": "facebook",
        "seller_name": "Vanzator Test",
    }


def _scan(monkeypatch, uid: int, listing: dict, eur_ron: float = 5.0) -> None:
    """Ruleaza _scan_user cu scraperul si cursul BNR inlocuite (fara retea)."""
    from app.database import SessionLocal
    from app.models.user import User
    from app.services import bnr_exchange

    monkeypatch.setattr(bnr_exchange, "get_eur_ron", lambda: eur_ron)
    monkeypatch.setattr(rs, "_run_scraper",
                        lambda *a, **k: [dict(listing)] if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(rs, "send_radar_notification", lambda **kwargs: 0)
    monkeypatch.setattr(rs, "is_push_configured", lambda: False)

    db = SessionLocal()
    try:
        rs._scan_user(db, db.query(User).get(uid))
    finally:
        db.close()


def _feed_row(uid: int, ext: str):
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    db = SessionLocal()
    try:
        return (db.query(RadarListing)
                .filter(RadarListing.user_id == uid, RadarListing.external_id == ext)
                .first())
    finally:
        db.close()


def _is_seen(uid: int, ext: str) -> bool:
    from app.database import SessionLocal
    from app.models.radar_seen_id import RadarSeenId
    db = SessionLocal()
    try:
        return db.query(RadarSeenId).filter(
            RadarSeenId.user_id == uid,
            RadarSeenId.platform == "facebook",
            RadarSeenId.external_id == ext).first() is not None
    finally:
        db.close()


# ── bucla principala de salvare (call site #1) ───────────────────────────────────

def test_anunt_in_eur_e_scorat_pe_valoarea_in_ron(auth_client, monkeypatch):
    """TINTA: gradul din feed reflecta valoarea REALA in RON a unui anunt in EUR.

    500 EUR × 5.0 = 2500 RON fata de 4000 RON revanzare -> marja 37.5% -> grad B.
    Fara conversie, cifra bruta 500 dadea 87.5% -> grad A fals.
    """
    uid = auth_client.get("/api/auth/me").json()["id"]
    _enable_facebook(uid)
    _mk_keyword(auth_client, resale_price=4000.0)
    ext = f"fb_{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, uid, _fb_listing(ext, price=500.0, currency="EUR"))

    row = _feed_row(uid, ext)
    assert row is not None                                  # anuntul E in feed
    assert row.price == 500.0 and row.currency == "EUR"     # pretul persistat ramane BRUT
    assert row.margin_pct == pytest.approx(37.5)            # (4000 - 2500) / 4000
    assert row.score == "B"


def test_anunt_scump_in_eur_nu_mai_primeste_grad_fals(auth_client, monkeypatch):
    """900 EUR = 4500 RON > 4000 RON revanzare -> marja negativa -> nu intra in feed.
    Fara conversie, cifra bruta 900 dadea 77.5% marja: un „chilipir" inexistent,
    salvat si notificat.
    """
    uid = auth_client.get("/api/auth/me").json()["id"]
    _enable_facebook(uid)
    _mk_keyword(auth_client, resale_price=4000.0)
    ext = f"fb_{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, uid, _fb_listing(ext, price=900.0, currency="EUR"))

    assert _feed_row(uid, ext) is None
    assert _is_seen(uid, ext)          # marcat vazut, ca la orice marja negativa


def test_control_aceeasi_cifra_in_ron_ramane_neatinsa(auth_client, monkeypatch):
    """CONTROL: acelasi 900, dar in RON, e un deal real si ramane grad A.
    Dovedeste ca fixul CONVERTESTE moneda, nu ca inaspreste pragul de marja.
    """
    uid = auth_client.get("/api/auth/me").json()["id"]
    _enable_facebook(uid)
    _mk_keyword(auth_client, resale_price=4000.0)
    ext = f"fb_{uuid.uuid4().hex[:10]}"

    _scan(monkeypatch, uid, _fb_listing(ext, price=900.0, currency="RON"))

    row = _feed_row(uid, ext)
    assert row is not None
    assert row.margin_pct == pytest.approx(77.5)            # (4000 - 900) / 4000
    assert row.score == "A"


# ── _refresh_seen_listing / puntea SAVED-BRIDGE (call site #2) ───────────────────

class _KwStub:
    """Stub minimal pentru RadarKeyword — doar atributele citite de punte."""
    def __init__(self, resale_price=1000.0):
        self.resale_price = resale_price
        self.min_margin_pct = 10.0
        self.grade_a_min = None
        self.grade_b_min = None
        self.grade_c_min = None
        self.notify_discord = False
        self.name = "kw-test"


def test_refresh_seen_recalculeaza_scorul_pe_valoarea_in_ron(auth_client, monkeypatch):
    """Un anunt salvat care reapare cu pret in EUR primeste scorul pe valoarea in RON.

    140 EUR × 5.0 = 700 RON fata de 1000 RON revanzare -> marja 30% -> grad B.
    Fara conversie, cifra bruta 140 dadea 86% -> grad A fals.
    """
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing

    uid = auth_client.get("/api/auth/me").json()["id"]
    kid = _mk_keyword(auth_client, resale_price=1000.0)
    ext = f"fb_{uuid.uuid4().hex[:10]}"

    db = SessionLocal()
    try:
        row = RadarListing(user_id=uid, keyword_id=kid, external_id=ext,
                           platform="facebook", title="Bicicleta de test",
                           price=200.0, currency="EUR",
                           url="https://facebook.com/marketplace/item/1",
                           images=json.dumps(["https://img/x.jpg"]),
                           score="A", margin_pct=86.0, status="active")
        db.add(row); db.commit(); db.refresh(row)
        rid = row.id
    finally:
        db.close()

    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    db = SessionLocal()
    try:
        out = rs._refresh_seen_listing(
            db, types.SimpleNamespace(id=uid), _KwStub(resale_price=1000.0),
            "facebook", {"external_id": ext, "price": 140.0, "currency": "EUR"},
            settings=None, eur_ron=5.0)
    finally:
        db.close()
    assert out == "updated"

    db = SessionLocal()
    try:
        row = db.query(RadarListing).get(rid)
        assert row.price == 140.0                    # pretul persistat ramane BRUT (EUR)
        assert row.margin_pct == pytest.approx(30.0)  # (1000 - 700) / 1000
        assert row.score == "B"
    finally:
        db.close()
