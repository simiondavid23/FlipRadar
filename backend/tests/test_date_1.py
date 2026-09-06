"""DATE-1 — doua date pe anunt: `listed_at` (prima publicare) si `refreshed_at`
(ultima reactualizare).

Pana acum o data etichetata "Reactualizat azi" ateriza in `listed_at`, deci filtrul
de vechime RAD-1 (`_too_old` pe `radar_keyword.max_age_days`) lasa sa treaca drept
"nou" un anunt de patru luni bumpat ieri. Regula cablata aici, valabila pentru toate
scraperele: o data ETICHETATA ca actualizare merge in `refreshed_at` si NICIODATA in
`listed_at`; una neetichetata sau etichetata ca publicare merge in `listed_at`.

Totul offline: fixture-uri si mock-uri, zero cereri de retea.
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text

_FIX_OLX_OFFER = os.path.join(os.path.dirname(__file__), "fixtures", "olx_offer.json")


# ── T1 — migrarile adauga coloana si sunt idempotente ────────────────────────────

_TABELE = ("radar_listings", "auto_feed_listings", "real_estate_listings")


def test_t1_migrarile_adauga_refreshed_at_si_sunt_idempotente():
    """Pe un SQLite in memorie cu cele trei tabele FARA coloana, `_portable_migrations`
    o adauga; a doua rulare nu crapa si nu dubleaza nimic.

    De ce `_portable_migrations` si nu blocurile istorice de langa cele de `listed_at`:
    `run_migrations` iese devreme pe SQLite (`if engine.dialect.name == "sqlite":
    return`), deci tot ce e sub acel return e cod mort pe singurul dialect ramas.
    """
    from app.utils.db_migrate import _portable_migrations

    engine = create_engine("sqlite://")   # in-memory, o singura conexiune
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE schema_migrations (
                migration_name VARCHAR(200) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        for tabel in _TABELE:
            conn.execute(text(
                f"CREATE TABLE {tabel} (id INTEGER PRIMARY KEY, listed_at TIMESTAMP)"))
        conn.commit()

        for tabel in _TABELE:
            assert "refreshed_at" not in {c["name"] for c in inspect(conn).get_columns(tabel)}

        _portable_migrations(conn, inspect(conn))
        for tabel in _TABELE:
            coloane = {c["name"] for c in inspect(conn).get_columns(tabel)}
            assert "refreshed_at" in coloane, f"{tabel} n-a primit refreshed_at"

        # A doua rulare: idempotenta (fara exceptie, fara coloana dubla).
        _portable_migrations(conn, inspect(conn))
        for tabel in _TABELE:
            nume = [c["name"] for c in inspect(conn).get_columns(tabel)]
            assert nume.count("refreshed_at") == 1

        aplicate = {r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))}
    assert {"add_radar_listings_refreshed_at", "add_auto_feed_refreshed_at",
            "add_re_listing_refreshed_at"} <= aplicate


def test_t1b_modelele_declara_refreshed_at():
    """Instalarile noi primesc coloana din create_all(), nu din migrare."""
    from app.models.auto_feed_listing import AutoFeedListing
    from app.models.radar_listing import RadarListing
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing

    for model in (RadarListing, AutoFeedListing, RealEstateMonitorListing):
        coloane = {c.name for c in model.__table__.columns}
        assert "listed_at" in coloane and "refreshed_at" in coloane, model.__name__


# ── T2 — forma standard a scraperelor are ambele chei ────────────────────────────

def test_t2_make_listing_are_ambele_chei_implicit_none():
    from app.scrapers.auto.listings._common import make_listing

    d = make_listing(platform="olx_auto")
    assert d["listed_at"] is None and d["refreshed_at"] is None

    acum = datetime(2026, 9, 6, 10, 0, 0)
    d = make_listing(platform="olx_auto", listed_at=acum, refreshed_at=acum)
    assert d["listed_at"] == acum and d["refreshed_at"] == acum


def test_t2b_make_re_listing_are_ambele_chei_implicit_none():
    from app.scrapers.real_estate._common import make_re_listing

    d = make_re_listing(platform="olx")
    assert d["listed_at"] is None and d["refreshed_at"] is None

    d = make_re_listing(platform="olx", listed_at="2026-05-01T10:00:00",
                        refreshed_at="2026-09-05T18:30:00")
    assert d["listed_at"] == "2026-05-01T10:00:00"
    assert d["refreshed_at"] == "2026-09-05T18:30:00"


# ── T3 — feed-ul Auto persista ambele date la INSERT ─────────────────────────────

def _seed_user_kw_auto(db):
    """User + AutoKeyword fara resale_price (ca `_resale_price_ron` sa nu ceara BNR)."""
    from app.models.auto_keyword import AutoKeyword
    from app.models.user import User

    email = f"date1_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0], hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    kw = AutoKeyword(user_id=u.id, name="kw date-1", platform="facebook_auto", is_active=True)
    db.add(kw)
    db.commit()
    return u, kw


def test_t3_save_listing_auto_persista_ambele_date():
    """Valorile vin naiv-local de la scrapere (`_naiv_local` la Facebook Auto);
    `_save_listing` le scrie ca atare, fara conversie."""
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    from app.services import auto_listings_scanner as als

    publicat = datetime(2026, 5, 2, 9, 15, 0)       # naiv local
    reactualizat = datetime(2026, 9, 5, 18, 30, 0)  # naiv local

    db = SessionLocal()
    try:
        _u, kw = _seed_user_kw_auto(db)
        raw = {
            "external_id": "fb_date1",
            "titlu": "Golf 5",
            "pret": 4500,
            "moneda": "EUR",
            "listed_at": publicat,
            "refreshed_at": reactualizat,
        }
        assert als._save_listing(db, kw, raw, None) is True

        rand = db.query(AutoFeedListing).filter(
            AutoFeedListing.external_id == "fb_date1").one()
        assert rand.listed_at == publicat
        assert rand.refreshed_at == reactualizat
    finally:
        db.close()


# ── T4 — cardul OLX: eticheta decide coloana ─────────────────────────────────────

_CARD_OLX = """
<html><body>
  <div data-cy="l-card">
    <a href="/d/oferta/test-IDabc123.html"><h4>iPhone 12 exemplu</h4></a>
    <p data-testid="ad-price">1 200 lei</p>
    <p data-testid="location-date">Cluj-Napoca - {data}</p>
    <img src="https://ireland.apollo.olxcdn.com/v1/files/x.jpg;s=200x200" />
  </div>
</body></html>
"""


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


def _cauta_olx(monkeypatch, text_data: str) -> dict:
    """Ruleaza `search_olx` pe un card fals (HTTP mockuit) si intoarce anuntul."""
    from app.services.radar import olx_scraper as olx

    monkeypatch.setattr(olx.curl_requests, "get",
                        lambda url, **kw: _Resp(200, _CARD_OLX.format(data=text_data)))
    monkeypatch.setattr(olx, "get_proxy_config", lambda: None)
    monkeypatch.setattr(olx.time, "sleep", lambda s: None)
    rezultate = olx.search_olx("iphone", 5000)
    assert len(rezultate) == 1, f"cardul n-a fost parsat: {rezultate}"
    return rezultate[0]


def test_t4_card_olx_reactualizat_merge_in_refreshed_at(monkeypatch):
    item = _cauta_olx(monkeypatch, "Reactualizat azi la 14:20")
    assert item["refreshed_at"] is not None
    assert item["refreshed_at"].hour == 14 and item["refreshed_at"].minute == 20
    assert item["listed_at"] is None, "o reactualizare NU are voie in listed_at"


def test_t4b_card_olx_fara_eticheta_ramane_listed_at(monkeypatch):
    item = _cauta_olx(monkeypatch, "Azi la 14:20")
    assert item["listed_at"] is not None
    assert item["listed_at"].hour == 14 and item["listed_at"].minute == 20
    assert item["refreshed_at"] is None


def test_t4c_card_olx_postat_e_publicare(monkeypatch):
    # "Postat" e eticheta de PUBLICARE — ramane pe listed_at.
    item = _cauta_olx(monkeypatch, "Postat ieri la 09:05")
    assert item["listed_at"] is not None and item["refreshed_at"] is None


def test_t4d_detector_de_eticheta_e_pur():
    from app.services.radar.olx_scraper import _este_reactualizare

    assert _este_reactualizare("Reactualizat azi la 14:20") is True
    assert _este_reactualizare("REACTUALIZAT AZI") is True
    assert _este_reactualizare("Azi la 14:20") is False
    assert _este_reactualizare("Postat ieri") is False
    assert _este_reactualizare(None) is False


# ── T5 — enrichment-ul OLX: reactualizarea nu ajunge in listed_at ────────────────

def _data_offer() -> dict:
    with open(_FIX_OLX_OFFER, encoding="utf-8") as f:
        return json.load(f)["data"]


def test_t5_enrichment_olx_separa_created_de_last_refresh():
    """`/api/v1/offers/{id}` expune AMBELE chei: `created_time` (publicare) si
    `last_refresh_time` (repromovare). Fiecare in coloana ei."""
    from app.services.radar.olx_scraper import _map_olx_offer

    out = _map_olx_offer(_data_offer())
    assert out["listed_at"] == datetime(2026, 7, 7, 12, 8, 9)
    assert out["refreshed_at"] == datetime(2026, 7, 7, 12, 11, 10)
    assert out["listed_at"].tzinfo is None and out["refreshed_at"].tzinfo is None


def test_t5b_reactualizarea_nu_ajunge_niciodata_in_listed_at():
    """Chiar cand publicarea lipseste din payload, valoarea de reactualizare NU
    o inlocuieste — altfel RAD-1 ar vedea un anunt vechi ca pe unul de azi."""
    from app.services.radar.olx_scraper import _map_olx_offer

    data = _data_offer()
    data.pop("created_time")
    out = _map_olx_offer(data)
    assert "listed_at" not in out
    assert out["refreshed_at"] == datetime(2026, 7, 7, 12, 11, 10)


# ── T6 — Imobiliare: ISO -> datetime, invalid -> None ────────────────────────────

def test_t6_seed_imobiliare_converteste_refreshed_at():
    from app.services.real_estate_scanner import _seed_from_raw

    seed = _seed_from_raw({"listed_at": "2026-05-01T10:00:00",
                           "refreshed_at": "2026-09-05T18:30:00"})
    assert seed["listed_at"] == datetime(2026, 5, 1, 10, 0, 0)
    assert seed["refreshed_at"] == datetime(2026, 9, 5, 18, 30, 0)


def test_t6b_seed_imobiliare_refreshed_at_invalid_da_none():
    from app.services.real_estate_scanner import _seed_from_raw

    for valoare in ("maine", "", None, "2026-13-45"):
        seed = _seed_from_raw({"refreshed_at": valoare})
        assert seed["refreshed_at"] is None, valoare


# ── T7 — radar_scanner: enrichment-ul duce refreshed_at pana in rand ─────────────

def test_t7_enrichment_inline_copiaza_refreshed_at(monkeypatch):
    """Cheia trebuie sa fie in tuplul de chei copiate din detaliu in listing."""
    from app.utils import radar_scanner as rs

    reactualizat = datetime(2026, 9, 5, 18, 30, 0)
    monkeypatch.setattr(rs, "fetch_olx_offer_details",
                        lambda nid: {"seller_name": "Ion", "refreshed_at": reactualizat})
    monkeypatch.setattr(rs, "fetch_olx_seller_rating", lambda sid: {})
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    monkeypatch.setitem(rs._enrich_counters, "olx", 0)

    listing = {"olx_numeric_id": 306490159, "platform": "olx"}
    rs._maybe_enrich_olx_inline(listing)
    assert listing["refreshed_at"] == reactualizat


def test_t7b_backlog_actualizeaza_randul_cu_refreshed_at(monkeypatch):
    """Ramura de actualizare a randului existent (backlog-ul de dupa scan)."""
    from app.database import SessionLocal
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_listing import RadarListing
    from app.models.user import User
    from app.utils import radar_scanner as rs

    reactualizat = datetime(2026, 9, 5, 18, 30, 0)
    monkeypatch.setattr(rs, "fetch_olx_offer_details",
                        lambda nid: {"refreshed_at": reactualizat})
    monkeypatch.setattr(rs, "fetch_olx_seller_rating", lambda sid: {})
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    monkeypatch.setitem(rs._enrich_counters, "olx_backlog", 0)

    db = SessionLocal()
    try:
        email = f"date1b_{uuid.uuid4().hex[:10]}@example.com"
        u = User(email=email, username=email.split("@")[0],
                 hashed_password="x", is_active=True)
        db.add(u)
        db.flush()
        kw = RadarKeyword(user_id=u.id, name="kw date-1", max_price=1000.0,
                          resale_price=1500.0, platform="olx")
        db.add(kw)
        db.flush()
        rand = RadarListing(
            user_id=u.id, keyword_id=kw.id, platform="olx", external_id="olx_abc",
            title="t", price=100.0, currency="RON", url="https://olx.ro/x",
            attributes_json=json.dumps({"olx_numeric_id": 306490159}),
        )
        db.add(rand)
        db.commit()

        rs._enrich_olx_backlog(db, u)
        db.refresh(rand)
        assert rand.refreshed_at == reactualizat
    finally:
        db.close()


# ── T8 — RAD-1 ramane pe listed_at (fail-open asumat) ────────────────────────────

def test_t8_too_old_ramane_pe_listed_at():
    """Documentare explicita: fail-open asumat la DATE-1; RAD-1 ramane pe listed_at.

    Un anunt fara data de publicare TRECE de filtru chiar daca a fost reactualizat
    acum sase luni. Decizia e deliberata (nu aruncam anunturi despre care nu stim
    nimic); mutarea filtrului pe refreshed_at ar fi alta runda.
    """
    from app.utils.radar_scanner import _too_old

    acum = datetime(2026, 9, 6, 12, 0, 0)
    vechi = acum - timedelta(days=180)

    assert _too_old(listed_at=None, max_age_days=30, now=acum) is False
    # Aceeasi valoare pusa pe listed_at ar fi respinsa — dovada ca filtrul chiar
    # masoara ceva, deci fail-open-ul de mai sus vine din lipsa datei, nu din prag.
    assert _too_old(listed_at=vechi, max_age_days=30, now=acum) is True


def test_t8b_feed_radar_expune_refreshed_at():
    """Contractul de feed: cheia exista MEREU, langa listed_at, in acelasi format."""
    from app.models.radar_listing import RadarListing
    from app.routers.radar import _listing_to_dict

    rand = RadarListing(
        user_id=1, keyword_id=None, platform="olx", external_id="x",
        title="t", price=1.0, currency="RON", url="u",
        listed_at=datetime(2026, 5, 1, 10, 0, 0),
        refreshed_at=datetime(2026, 9, 5, 18, 30, 0),
        found_at=datetime(2026, 9, 5, 19, 0, 0, tzinfo=timezone.utc),
    )
    d = _listing_to_dict(rand)
    assert d["listed_at"] == "2026-05-01T10:00:00"
    assert d["refreshed_at"] == "2026-09-05T18:30:00"

    gol = RadarListing(user_id=1, platform="olx", title="t", price=1.0,
                       currency="RON", url="u")
    assert _listing_to_dict(gol)["refreshed_at"] is None


# ── HOTFIX CI — parserul ISO nu are voie sa depinda de fusul masinii ────────────

def test_iso_parser_da_ora_bucurestiului_indiferent_de_offsetul_din_input():
    """Acelasi MOMENT, scris in trei fusuri: acelasi rezultat, ora Bucurestiului.

    Bug-ul reparat: `.astimezone()` fara argument converteste la fusul MASINII. Pe
    laptopul din Romania iesea ora corecta, pe runner-ul GitHub Actions (UTC) iesea cu
    3 ore mai putin, si patru teste care asertau ora absoluta picau doar acolo.

    Asertia e pe o valoare FIXA (nu derivata din ceasul masinii), deci testul are
    acelasi verdict pe orice runner — asta e tot rostul lui.
    """
    from app.utils.listing_dates import iso_to_naive_local

    asteptat = datetime(2026, 9, 2, 12, 54, 54)          # 2 sept = ora de vara, UTC+3
    for intrare in ("2026-09-02T12:54:54+03:00",         # cum trimite OLX vara
                    "2026-09-02T09:54:54+00:00",
                    "2026-09-02T09:54:54Z",
                    "2026-09-02T11:54:54+02:00",
                    "2026-09-02T04:54:54-05:00"):
        assert iso_to_naive_local(intrare) == asteptat, intrare


def test_iso_parser_respecta_ora_de_iarna():
    """Romania trece pe UTC+2 iarna — de aia e ZoneInfo, nu un offset fix de +3."""
    from app.utils.listing_dates import iso_to_naive_local

    assert iso_to_naive_local("2026-01-15T08:00:00+00:00") == datetime(2026, 1, 15, 10, 0)
    assert iso_to_naive_local("2026-01-15T10:00:00+02:00") == datetime(2026, 1, 15, 10, 0)
    # aceeasi zi calendaristica, vara: +3
    assert iso_to_naive_local("2026-07-15T08:00:00+00:00") == datetime(2026, 7, 15, 11, 0)


def test_input_naiv_ramane_neschimbat():
    """Fara offset nu se ghiceste nimic — valoarea e deja locala prin conventie."""
    from app.utils.listing_dates import iso_to_naive_local

    assert iso_to_naive_local("2026-09-02T12:54:54") == datetime(2026, 9, 2, 12, 54, 54)


def test_niciun_astimezone_fara_argument_pe_caile_de_data():
    """Garda structurala: `.astimezone()` fara argument = fusul masinii.

    Prinde regresia si pe un laptop din Romania, unde asertiile pe ora absoluta trec
    oricum. `facebook_scraper._naiv_local` e EXCLUS deliberat: acolo contractul e
    relativ la `datetime.now()` (vezi test_fb_radar_adapter / test_fb_auto_adapter,
    care compara varsta naiva cu varsta UTC), deci fusul masinii e cel corect.
    """
    import ast
    import inspect

    from app.scrapers.real_estate import olx_real_estate
    from app.services.radar import olx_scraper
    from app.utils import listing_dates

    for modul in (listing_dates, olx_scraper, olx_real_estate):
        # Se inspecteaza APELURILE, prin ast, nu textul: docstring-urile vorbesc
        # despre `astimezone().replace(tzinfo=None)` ca sa explice exact capcana asta.
        goale = [n for n in ast.walk(ast.parse(inspect.getsource(modul)))
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "astimezone"
                 and not n.args and not n.keywords]
        assert not goale, (modul.__name__, [n.lineno for n in goale])


def test_cele_doua_parsere_olx_deleaga_la_helperul_comun():
    """Regula de fus traieste intr-un singur loc; copiile doar deleaga."""
    from app.scrapers.real_estate.olx_real_estate import _parse_iso_dt as re_parse
    from app.services.radar.olx_scraper import _parse_iso_dt as radar_parse

    asteptat = datetime(2026, 7, 7, 12, 8, 9)
    for parser in (radar_parse, re_parse):
        assert parser("2026-07-07T12:08:09+03:00") == asteptat
        assert parser("2026-07-07T09:08:09+00:00") == asteptat
        assert parser(None) is None
        assert parser("maine") is None
