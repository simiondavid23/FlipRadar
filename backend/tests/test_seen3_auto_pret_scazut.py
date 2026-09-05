"""SEEN-3 — pe Auto, o scadere de pret retine referinta si alerteaza cand urca gradul.

DE CE EXISTA: Auto n-are tabela de „vazut", n-are filtru de vechime si nu respinge pe
marja — orice anunt gasit devine rand, iar la reaparitie pretul si gradul se actualizau
DEJA (SAVED-BRIDGE). Dar in tacere: fara referinta la pretul de la care a scazut si fara
alerta, chiar daca anuntul trecea din D in A. Notificarea pleca doar la prima vedere.

Ce apara fisierul (echivalentul D-S4 din SEEN-2):
  * `pret_anterior` se scrie DOAR peste pragul de 5% — badge-ul comun (UI-1) se aprinde
    din el, deci o fluctuatie de 1% nu are voie sa-l aprinda;
  * alerta pleaca pe randurile SALVATE (ca inainte, orice scadere peste prag) SI pe cele
    active pe care scaderea le-a urcat intr-un grad A/B/C;
  * cheia de dedup Discord poarta nivelul de pret, ca aceeasi scadere sa nu se
    re-notifice ciclu de ciclu.

DIFERENTA FATA DE RADAR, deliberata: aici referinta e pretul dinaintea ULTIMEI scaderi,
nu primul pret vazut. Radar are `radar_seen_ids`, care supravietuieste si cand anuntul
n-are rand in feed; pe Auto randul e mereu viu si nu exista a doua memorie. Scenariul 3
masoara exact aceasta semantica, ca sa nu fie confundata cu un bug.

REGULA DE TEST (CUR-1 b2 / TIDY-1 a): tot ce e cablare se testeaza prin `run_auto_scan`,
nu apeland `_save_listing` direct. Fara retea: `_call_scraper` si `get_eur_ron` pinuite,
notificarile capturate.
"""
import uuid

import pytest

from app.services import auto_listings_scanner as als


# ── infrastructura ──────────────────────────────────────────────────────────────
def _seed(db, resale_price=None, notify_discord=True):
    """User + keyword facebook_auto (platforma fara filtre server-side de an).

    `resale_price_currency="RON"` e ESENTIAL: implicitul modelului e EUR, iar
    `_resale_price_ron` l-ar inmulti cu cursul — pragurile de grad din teste ar iesi de
    cinci ori mai sus si toate anunturile ar fi grad A.
    """
    from app.models.auto_keyword import AutoKeyword
    from app.models.radar_settings import RadarSettings
    from app.models.user import User

    email = f"seen3_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    kw = AutoKeyword(user_id=u.id, name="kw seen3", platform="facebook_auto",
                     is_active=True, active_hours_start=None, active_hours_end=None,
                     resale_price=resale_price, resale_price_currency="RON",
                     notify_discord=notify_discord, notify_email=False)
    db.add(kw)
    db.add(RadarSettings(user_id=u.id))       # `_notify` cere randul de settings
    db.commit()
    return u, kw


def _card(ext: str, pret: float, moneda="EUR") -> dict:
    return {"external_id": ext, "titlu": f"BMW {ext}", "pret": pret,
            "currency": moneda, "url": f"https://autovit.ro/{ext}",
            "an": 2018, "km": 100000}


def _scan(monkeypatch, db, carduri, notif=None):
    """Un ciclu complet prin `run_auto_scan`, cu scraperul si cursul pinuite."""
    monkeypatch.setattr(als, "_call_scraper",
                        lambda kw, *a, **k: [dict(c) for c in carduri]
                        if k.get("page", 1) == 1 else [])
    monkeypatch.setattr(als.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(als, "get_eur_ron", lambda: 5.0)
    import app.services.discord_service as ds
    monkeypatch.setattr(ds, "send_auto_notification",
                        lambda *a, **k: (notif.append(a) if notif is not None else None) or 1)
    als.run_auto_scan(db, platform="facebook_auto")


def _rand(db, ext: str):
    from app.models.auto_feed_listing import AutoFeedListing
    db.expire_all()
    return (db.query(AutoFeedListing)
            .filter(AutoFeedListing.external_id == ext).first())


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ── 1. scaderea urca gradul -> referinta + alerta (D-S4) ────────────────────────
def test_scaderea_care_urca_gradul_alerteaza(monkeypatch, db):
    # resale 100000 RON; 20000 EUR = 100000 RON -> marja 0% -> grad D (sub min 10%).
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, db, [_card(ext, 20000.0)], notif)

    rand = _rand(db, ext)
    assert rand is not None and rand.grade == "D"
    assert rand.pret_anterior is None, "prima vedere: n-are de la ce sa scada"
    notif.clear()

    # 17000 EUR = 85000 RON -> marja 15% -> grad C; scadere 15%.
    _scan(monkeypatch, db, [_card(ext, 17000.0)], notif)

    rand = _rand(db, ext)
    assert float(rand.price) == 17000.0
    assert float(rand.pret_anterior) == 20000.0
    assert rand.grade == "C"
    assert len(notif) == 1, "D-S4: scaderea l-a urcat intr-un grad -> alerta"
    listing_dict, grad, _scor, _nume, _settings, listing_id, _db = notif[0]
    assert listing_id == f"auto-pricedrop-{rand.id}-17000"
    assert listing_dict["title"].startswith("Pret scazut 15%: ")


# ── 2. sub prag: nimic ──────────────────────────────────────────────────────────
def test_scadere_sub_prag_nu_atinge_referinta(monkeypatch, db):
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, db, [_card(ext, 20000.0)], notif)
    notif.clear()
    _scan(monkeypatch, db, [_card(ext, 19400.0)], notif)      # -3%

    rand = _rand(db, ext)
    assert float(rand.price) == 19400.0, "pretul tot se actualizeaza"
    assert rand.pret_anterior is None, "sub prag, referinta nu se scrie"
    assert notif == []


# ── 3. ramane grad D + semantica „ultima scadere" ──────────────────────────────
def test_ramas_grad_d_nu_alerteaza_iar_referinta_e_ultima_scadere(monkeypatch, db):
    # resale 60000 RON: 20000 EUR = 100000 RON -> marja negativa -> grad None/D.
    _seed(db, resale_price=60000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, db, [_card(ext, 20000.0)], notif)
    notif.clear()

    _scan(monkeypatch, db, [_card(ext, 17000.0)], notif)      # -15%, tot sub resale
    rand = _rand(db, ext)
    assert float(rand.pret_anterior) == 20000.0
    assert rand.grade not in ("A", "B", "C"), "17000 EUR = 85000 RON > 60000 resale"
    assert notif == [], "scaderea n-a urcat gradul si randul nu e salvat"

    _scan(monkeypatch, db, [_card(ext, 15300.0)], notif)      # inca -10%

    rand = _rand(db, ext)
    assert float(rand.price) == 15300.0
    assert float(rand.pret_anterior) == 17000.0, (
        "pe Auto referinta e pretul dinaintea ULTIMEI scaderi, nu primul pret vazut "
        "(diferenta deliberata fata de Radar — vezi docstring-ul fisierului)")


# ── 4. randurile SALVATE alerteaza si pe grad D ────────────────────────────────
def test_rand_salvat_alerteaza_si_pe_grad_d(monkeypatch, db):
    """Gradul trebuie sa fie D REAL (marja pozitiva dar sub `min_margin_pct`), nu None:
    `_notify` respinge din prima linie orice grad in afara de A/B/C/D, deci un anunt cu
    marja NEGATIVA ramane tacut si cand e salvat. Granita e a lui `_notify`, dinainte de
    SEEN-3, si e corecta — un anunt fara grad n-are ce raporta."""
    from app.models.auto_feed_listing import AutoFeedListing

    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, db, [_card(ext, 20000.0)], notif)      # 100000 RON -> marja 0% -> D
    rand = db.query(AutoFeedListing).filter(AutoFeedListing.external_id == ext).first()
    rand.status = "saved"
    db.commit()
    notif.clear()

    _scan(monkeypatch, db, [_card(ext, 18600.0)], notif)      # -7%; marja 7% -> tot D

    rand = _rand(db, ext)
    assert rand.grade == "D", "sub min_margin_pct (10%), deci nu urca in grad"
    assert float(rand.pret_anterior) == 20000.0
    assert len(notif) == 1, "pe salvate, orice scadere peste prag alerteaza"


# ── 5. moneda diferita: garda existenta ────────────────────────────────────────
def test_moneda_diferita_nu_atinge_nimic(monkeypatch, db):
    _seed(db, resale_price=100000.0)
    ext = f"a{uuid.uuid4().hex[:10]}"
    notif = []

    _scan(monkeypatch, db, [_card(ext, 20000.0, moneda="EUR")], notif)
    notif.clear()
    _scan(monkeypatch, db, [_card(ext, 10000.0, moneda="RON")], notif)

    rand = _rand(db, ext)
    assert float(rand.price) == 20000.0, "pretul NU s-a atins"
    assert rand.pret_anterior is None
    assert notif == []


# ── 6. pragul e acelasi cu al Radarului ────────────────────────────────────────
def test_pragul_e_acelasi_cu_radarul():
    """Constanta e declarata local (module separate), deci nimic n-o tine sincronizata
    in afara acestui test. Imobiliare foloseste acelasi 0.05, literal in scanner."""
    from app.utils.radar_scanner import _PRICE_DROP_MIN as RADAR_PRAG

    assert als._PRICE_DROP_MIN == RADAR_PRAG == 0.05


# ── 7. migrarea ────────────────────────────────────────────────────────────────
@pytest.fixture
def baza_proaspata(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from app.database import Base
    from app.utils import db_migrate
    eng = create_engine(f"sqlite:///{(tmp_path / 'seen3.db').as_posix()}")
    monkeypatch.setattr(db_migrate, "engine", eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


def _coloane(eng):
    from sqlalchemy import inspect
    return {c["name"] for c in inspect(eng).get_columns("auto_feed_listings")}


def test_baza_proaspata_are_coloana(baza_proaspata):
    assert "pret_anterior" in _coloane(baza_proaspata)


def test_baza_veche_primeste_coloana(baza_proaspata):
    from sqlalchemy import text
    from app.utils import db_migrate

    with baza_proaspata.begin() as conn:
        conn.execute(text("ALTER TABLE auto_feed_listings DROP COLUMN pret_anterior"))
    assert "pret_anterior" not in _coloane(baza_proaspata)

    db_migrate.run_migrations()

    assert "pret_anterior" in _coloane(baza_proaspata)
    with baza_proaspata.connect() as conn:
        aplicate = [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))]
    assert "add_auto_feed_listings_pret_anterior" in aplicate

    db_migrate.run_migrations()               # idempotenta
    with baza_proaspata.connect() as conn:
        din_nou = [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))]
    assert sorted(din_nou) == sorted(aplicate)


# ── 8. feed-ul serializeaza cheia ca numar ─────────────────────────────────────
def test_feed_intoarce_pret_anterior_ca_numar(auth_client, monkeypatch):
    """`Numeric` ajunge Decimal in Python; fara conversie explicita, FastAPI ar crapa
    la serializare (sau ar trimite un tip pe care badge-ul nu-l poate citi)."""
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing

    uid = auth_client.get("/api/auth/me").json()["id"]
    ext = f"a{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        db.add(AutoFeedListing(user_id=uid, keyword_id=None, platform="autovit",
                               external_id=ext, title="BMW test", price=17000,
                               currency="EUR", status="active", grade="C",
                               pret_anterior=20000))
        db.commit()
    finally:
        db.close()

    r = auth_client.get("/api/auto-listings/feed")
    assert r.status_code == 200, r.text
    date = r.json()
    randuri = date["items"] if isinstance(date, dict) else date
    al_nostru = [x for x in randuri if x["external_id"] == ext]
    assert al_nostru, date
    assert al_nostru[0]["pret_anterior"] == 20000.0
    assert isinstance(al_nostru[0]["pret_anterior"], float)
