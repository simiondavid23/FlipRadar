"""SEEN-2 — scaderile de pret readuc anunturile respinse si alerteaza randurile active.

DE CE EXISTA: pana acum, un anunt VAZUT dar fara rand in feed (aruncat pe vechime sau pe
marja negativa) nu mai producea nimic, niciodata. Un anunt de grad D care scadea 15% si
devenea grad A ramanea tacut, iar `radar_seen_ids` nu retinea niciun pret, deci nici
n-avea cum sa observe scaderea.

Deciziile aparate aici:
  D-S1  scaderea se judeca fata de PRIMUL pret vazut, nu de ultimul — asa coborarile
        treptate (6900 -> 6700 -> 6400) se cumuleaza in loc sa fie fiecare „prea mica";
  D-S2  un anunt revenit ocoleste filtrul de vechime;
  D-S3  marja se recalculeaza pe pretul nou, deci si respinsii pe marja negativa revin;
  D-S4  randurile ACTIVE alerteaza cand scaderea le-a urcat intr-un grad A/B/C.

REGULA DE TEST (lectia CUR-1 b2 / TIDY-1 a): tot ce e CABLARE se testeaza prin
`_scan_user`, nu apeland direct functia cablata. Fiecare scenariu de aici ruleaza scanuri
succesive — primul stabileste starea, urmatoarele masoara reaparitia.

Fara retea: `_run_scraper` si `catalog_ron` sunt pinuite, notificarile capturate.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import radar_scanner as rs


# ── infrastructura ──────────────────────────────────────────────────────────────
def _enable(uid: int, platforma: str = "vinted") -> None:
    from app.database import SessionLocal
    from app.models.radar_settings import RadarSettings
    db = SessionLocal()
    try:
        s = db.query(RadarSettings).filter(RadarSettings.user_id == uid).first()
        if s is None:
            s = RadarSettings(user_id=uid)
            db.add(s)
        setattr(s, f"platform_{platforma}_enabled", True)
        db.commit()
    finally:
        db.close()


def _kw(auth_client, resale_price=8000.0, max_age_days=None, min_margin_pct=10.0,
        notify_discord=True) -> int:
    r = auth_client.post("/api/radar/keywords", json={
        "name": f"kw {uuid.uuid4().hex[:6]}", "max_price": 100000.0,
        "resale_price": resale_price, "platforms": ["vinted"],
        "notify_email": False, "notify_discord": notify_discord,
    })
    assert r.status_code == 200, r.text
    kid = r.json()["id"]
    from app.database import SessionLocal
    from app.models.radar_keyword import RadarKeyword
    db = SessionLocal()
    try:
        k = db.query(RadarKeyword).get(kid)
        k.max_age_days = max_age_days
        k.min_margin_pct = min_margin_pct
        db.commit()
    finally:
        db.close()
    return kid


def _anunt(ext: str, price: float, currency="RON", zile_vechime=0) -> dict:
    return {
        "external_id": ext, "title": "Bicicleta de test", "price": price,
        "currency": currency, "url": "https://vinted.ro/x",
        "images": ["https://img/x.jpg"], "description": None, "location": "Cluj",
        "seller_name": None, "seller_id": None, "platform": "vinted",
        "listed_at": datetime.utcnow() - timedelta(days=zile_vechime),
    }


def _scan(monkeypatch, uid: int, anunt: dict, notif=None, cursuri=None):
    """Un ciclu complet prin `_scan_user`, cu scraperul si cursurile pinuite."""
    from app.database import SessionLocal
    from app.models.user import User
    from app.services import bnr_exchange, currency_service

    monkeypatch.setattr(bnr_exchange, "get_eur_ron", lambda: 5.0)
    monkeypatch.setattr(bnr_exchange, "get_usd_ron", lambda: 4.5)
    monkeypatch.setattr(currency_service, "catalog_ron",
                        lambda: dict(cursuri or {"RON": 1.0}))
    monkeypatch.setattr(rs, "_run_scraper",
                        lambda *a, **k: [dict(anunt)] if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(rs, "is_push_configured", lambda: False)
    monkeypatch.setattr(rs, "send_radar_notification",
                        lambda **kw: (notif.append(kw) if notif is not None else None) or 1)
    # `_platform_scan_due` tine de cadenta, nu de SEEN-2: fara asta al doilea scan din
    # aceeasi secunda ar fi sarit ca „nu e due" si n-am masura nimic.
    monkeypatch.setattr(rs, "_platform_scan_due", lambda kw, p, now=None: True)

    db = SessionLocal()
    try:
        rs._scan_user(db, db.query(User).get(uid))
    finally:
        db.close()


def _rand(uid: int, ext: str):
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    db = SessionLocal()
    try:
        return (db.query(RadarListing)
                .filter(RadarListing.user_id == uid, RadarListing.external_id == ext)
                .first())
    finally:
        db.close()


def _seen(uid: int, ext: str):
    from app.database import SessionLocal
    from app.models.radar_seen_id import RadarSeenId
    db = SessionLocal()
    try:
        return (db.query(RadarSeenId)
                .filter(RadarSeenId.user_id == uid, RadarSeenId.external_id == ext)
                .first())
    finally:
        db.close()


@pytest.fixture
def user(auth_client):
    uid = auth_client.get("/api/auth/me").json()["id"]
    _enable(uid)
    return uid


# ── 1. anunt prea vechi -> revine cand scade destul (D-S1 + D-S2) ───────────────
def test_anunt_prea_vechi_revine_dupa_scadere(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0, max_age_days=5)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 6900.0, zile_vechime=30), notif)

    assert _rand(user, ext) is None, "prima scanare: prea vechi, deci fara rand"
    s = _seen(user, ext)
    assert s is not None and s.pret_initial == 6900.0 and s.pret_ultim == 6900.0
    assert s.moneda == "RON"
    assert notif == []

    _scan(monkeypatch, user, _anunt(ext, 5900.0, zile_vechime=30), notif)

    rand = _rand(user, ext)
    assert rand is not None, "scaderea de 14.5% trebuia sa-l readuca in feed"
    assert rand.price == 5900.0
    assert rand.pret_anterior == 6900.0
    assert rand.score == "B"                      # marja 26.25% fata de resale 8000
    assert rand.status == "active"
    assert len(notif) == 1
    assert notif[0]["listing_id"].startswith("pricedrop-seen-")


# ── 2. scaderea se judeca fata de PRIMUL pret, nu de ultimul (D-S1) ─────────────
def test_scaderea_se_cumuleaza_fata_de_primul_pret(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0, max_age_days=5)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 6900.0, zile_vechime=30), notif)
    _scan(monkeypatch, user, _anunt(ext, 6700.0, zile_vechime=30), notif)

    assert _rand(user, ext) is None, "-2.9% e sub pragul de 5%"
    s = _seen(user, ext)
    assert s.pret_ultim == 6700.0
    assert s.pret_initial == 6900.0, "referinta NU se muta pe ultimul pret"
    assert notif == []

    # -7.2% fata de PRIMUL (6900), dar doar -4.5% fata de ultimul (6700).
    _scan(monkeypatch, user, _anunt(ext, 6400.0, zile_vechime=30), notif)

    rand = _rand(user, ext)
    assert rand is not None, "cumulat fata de 6900 trece pragul — dovada D-S1"
    assert rand.pret_anterior == 6900.0
    assert len(notif) == 1


# ── 3. marja negativa la prima vedere, deal la a doua (D-S3) ───────────────────
def test_respins_pe_marja_revine_cand_devine_deal(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 9000.0), notif)      # peste resale -> respins

    assert _rand(user, ext) is None
    assert _seen(user, ext).pret_initial == 9000.0
    assert notif == []

    _scan(monkeypatch, user, _anunt(ext, 4000.0), notif)      # -55%, marja 50%

    rand = _rand(user, ext)
    assert rand is not None and rand.score == "A"
    assert rand.pret_anterior == 9000.0
    assert len(notif) == 1


# ── 4. rand ACTIV urcat intr-un grad de scadere (D-S4) ─────────────────────────
def test_rand_activ_alerteaza_cand_scaderea_il_urca_in_grad(user, auth_client, monkeypatch):
    # resale 8000, pret 7500 -> marja 6.25% -> grad D (peste min_margin 5, sub grad C)
    _kw(auth_client, resale_price=8000.0, min_margin_pct=5.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 7500.0), notif)

    rand = _rand(user, ext)
    assert rand is not None and rand.score == "D"
    notif.clear()

    _scan(monkeypatch, user, _anunt(ext, 6375.0), notif)      # -15% -> marja 20.3% -> C

    rand = _rand(user, ext)
    assert rand.score == "C"
    assert rand.pret_anterior == 7500.0
    assert len(notif) == 1, "D-S4: scaderea l-a urcat intr-un grad -> alerta"


def test_rand_activ_ramas_grad_d_nu_alerteaza(user, auth_client, monkeypatch):
    # resale 8000, min_margin 5: 7500 -> 6.25% (D); 7100 -> 11.25%... prea sus.
    # Alegem resale 7800: 7500 -> 3.8% (sub min_margin -> D/filtrat), 7000 -> 10.2% (C).
    # Ca sa ramana D dupa scadere, tinem marja intre min_margin si pragul de C:
    _kw(auth_client, resale_price=8000.0, min_margin_pct=1.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 7920.0), notif)      # marja 1% -> D
    assert _rand(user, ext).score == "D"
    notif.clear()

    _scan(monkeypatch, user, _anunt(ext, 7300.0), notif)      # -7.8% -> marja 8.75% -> tot D

    rand = _rand(user, ext)
    assert rand.score == "D", "ramane sub pragul gradului C"
    assert rand.pret_anterior == 7920.0, "scaderea a fost reala, doar n-a meritat alerta"
    assert notif == []


# ── 5. scadere sub prag pe rand activ ──────────────────────────────────────────
def test_scadere_sub_prag_nu_atinge_referinta(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 4000.0), notif)
    notif.clear()
    _scan(monkeypatch, user, _anunt(ext, 3880.0), notif)      # -3%

    rand = _rand(user, ext)
    assert rand.price == 3880.0
    assert rand.pret_anterior is None, 'sub prag: referinta nu se scrie'
    assert notif == []


# ── 6. randurile SALVATE isi pastreaza comportamentul vechi ────────────────────
def test_rand_salvat_alerteaza_si_pe_grad_d(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0, min_margin_pct=1.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 7920.0), notif)      # marja 1% -> D
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    db = SessionLocal()
    try:
        r = db.query(RadarListing).filter(RadarListing.external_id == ext).first()
        r.status = "saved"
        db.commit()
    finally:
        db.close()
    notif.clear()

    _scan(monkeypatch, user, _anunt(ext, 7400.0), notif)      # -6.6%, tot grad D

    assert len(notif) == 1, "pe salvate, orice scadere >= 5% alerteaza (nemodificat)"
    assert _rand(user, ext).score == "D"


# ── 7. backfill pentru randurile de dinainte de SEEN-2 ─────────────────────────
def test_randul_vechi_fara_pret_initial_se_backfilleaza(user, auth_client, monkeypatch):
    from app.database import SessionLocal
    from app.models.radar_seen_id import RadarSeenId

    _kw(auth_client, resale_price=8000.0, max_age_days=5)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    db = SessionLocal()
    try:                                    # rand ca inainte de SEEN-2: preturi NULL
        db.add(RadarSeenId(user_id=user, platform="vinted", external_id=ext))
        db.commit()
    finally:
        db.close()

    _scan(monkeypatch, user, _anunt(ext, 6900.0, zile_vechime=30), notif)

    s = _seen(user, ext)
    assert s.pret_initial == 6900.0, "prima reaparitie doar stabileste referinta"
    assert _rand(user, ext) is None
    assert notif == []

    _scan(monkeypatch, user, _anunt(ext, 6000.0, zile_vechime=30), notif)

    assert _rand(user, ext) is not None, "de la a doua reaparitie, scaderile se vad"
    assert len(notif) == 1


# ── 8. monede diferite nu se compara ───────────────────────────────────────────
def test_moneda_diferita_nu_produce_revenire(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0, max_age_days=5)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, user, _anunt(ext, 6900.0, zile_vechime=30), notif)
    _scan(monkeypatch, user, _anunt(ext, 1000.0, currency="EUR", zile_vechime=30), notif)

    assert _rand(user, ext) is None, "RON vs EUR nu se compara — posibila anomalie"
    assert _seen(user, ext).pret_initial == 6900.0
    assert notif == []


# ── 8b. calea de revenire converteste moneda prin catalogul BNR ────────────────
def test_revenirea_scoreaza_prin_catalogul_de_monede(user, auth_client, monkeypatch):
    """Cablarea `cursuri` pe calea de revenire: 900 GBP × 6.0 = 5400 RON fata de 8000
    revanzare -> marja 32.5% -> grad B. Fara catalog, 900 ar fi citit ca 900 RON
    (marja 88.75% -> grad A fals)."""
    _kw(auth_client, resale_price=8000.0, max_age_days=5)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    notif = []
    cursuri = {"GBP": 6.0, "RON": 1.0}

    _scan(monkeypatch, user, _anunt(ext, 1200.0, currency="GBP", zile_vechime=30),
          notif, cursuri=cursuri)
    _scan(monkeypatch, user, _anunt(ext, 900.0, currency="GBP", zile_vechime=30),
          notif, cursuri=cursuri)

    rand = _rand(user, ext)
    assert rand is not None and rand.currency == "GBP"
    assert rand.score == "B", "scorat pe 5400 RON, nu pe 900"
    assert abs(rand.margin_pct - 32.5) < 0.01


# ── 9. migrarea ────────────────────────────────────────────────────────────────
_COLOANE = {"radar_seen_ids": ("pret_initial", "pret_ultim", "moneda"),
            "radar_listings": ("pret_anterior",)}
_MIGRARI = {"add_radar_seen_ids_pret_initial", "add_radar_seen_ids_pret_ultim",
            "add_radar_seen_ids_moneda", "add_radar_listings_pret_anterior"}


@pytest.fixture
def baza_proaspata(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from app.database import Base
    from app.utils import db_migrate
    eng = create_engine(f"sqlite:///{(tmp_path / 'seen2.db').as_posix()}")
    monkeypatch.setattr(db_migrate, "engine", eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


def _coloane(eng, tabela):
    from sqlalchemy import inspect
    return {c["name"] for c in inspect(eng).get_columns(tabela)}


def test_baza_proaspata_are_coloanele(baza_proaspata):
    for tabela, coloane in _COLOANE.items():
        prezente = _coloane(baza_proaspata, tabela)
        for c in coloane:
            assert c in prezente, f"{tabela}.{c}"


def test_baza_veche_primeste_coloanele_si_e_idempotenta(baza_proaspata):
    from sqlalchemy import text
    from app.utils import db_migrate

    with baza_proaspata.begin() as conn:      # simulam o baza dinainte de SEEN-2
        for tabela, coloane in _COLOANE.items():
            for c in coloane:
                conn.execute(text(f"ALTER TABLE {tabela} DROP COLUMN {c}"))
    for tabela, coloane in _COLOANE.items():
        assert not (set(coloane) & _coloane(baza_proaspata, tabela))

    db_migrate.run_migrations()

    for tabela, coloane in _COLOANE.items():
        assert set(coloane) <= _coloane(baza_proaspata, tabela)
    with baza_proaspata.connect() as conn:
        aplicate = [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))]
    assert _MIGRARI <= set(aplicate)

    db_migrate.run_migrations()               # a doua rulare: fara exceptii, fara dubluri
    with baza_proaspata.connect() as conn:
        din_nou = [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))]
    assert sorted(din_nou) == sorted(aplicate)


# ── serializarea de feed ───────────────────────────────────────────────────────
def test_feed_expune_pret_anterior(user, auth_client, monkeypatch):
    _kw(auth_client, resale_price=8000.0)
    ext = f"vinted_{uuid.uuid4().hex[:10]}"
    _scan(monkeypatch, user, _anunt(ext, 4000.0), [])
    _scan(monkeypatch, user, _anunt(ext, 3000.0), [])

    r = auth_client.get("/api/radar/listings")
    assert r.status_code == 200, r.text
    al_nostru = [x for x in r.json()["items"] if x["external_id"] == ext]
    assert al_nostru, r.json()
    assert al_nostru[0]["pret_anterior"] == 4000.0
