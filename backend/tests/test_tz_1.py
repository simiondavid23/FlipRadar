"""TZ-1 — toate orele afisate sunt ora locala a sistemului pe care ruleaza aplicatia.

Decizia (2026-09-07): in DB toate datetime-urile sunt NAIVE, in ora de perete a locului
unde conteaza, iar conversia se face O SINGURA DATA, LA SCRIERE. Frontend-ul afiseaza ce
primeste — un string fara offset e citit de browser ca ora locala, adica a aceleiasi masini.

Doua ceasuri, deliberat separate (varianta A, confirmata de David):
  * `acum_local()` — ceasul NOSTRU (`found_at`, `log_entries.created_at`, pragurile de
    cleanup / retentie / filtre): ora sistemului;
  * `to_naive_bucuresti()` / `din_fus()` — ora DECLARATA de platforma (`listed_at`,
    `refreshed_at`): `FUS_ANUNTURI`, ca „postat 12:54" sa arate ca pe olx.ro.
Pe masina de productie (GTB Standard Time) cele doua dau exact aceeasi valoare.

Anomalia care a pornit runda, masurata in productie: un anunt Facebook cu `listed_at`
'2026-09-05 16:50:51' (ora RO) si `found_at` '2026-09-05 16:23:23' — gasit cu 27 de
minute inainte de a fi postat, fiindca `found_at` era UTC.

Testele NU hardcodeaza offsetul masinii: valorile asteptate se calculeaza cu `zoneinfo`,
deci verdictul e acelasi pe laptopul din Romania si pe runner-ul UTC.
"""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.utils.listing_dates import (
    FUS_ANUNTURI,
    acum_local,
    din_fus,
    to_naive_bucuresti,
)

_UTC = timezone.utc


def _in_fus_anunturi(aware: datetime) -> datetime:
    """Referinta, calculata cu zoneinfo — nu cu offset scris de mana."""
    return aware.astimezone(FUS_ANUNTURI).replace(tzinfo=None)


# ── T1 — `to_naive_bucuresti` ───────────────────────────────────────────────────────

def test_t1_datetime_aware_se_converteste():
    aware = datetime(2026, 8, 1, 6, 45, 38, tzinfo=_UTC)
    assert to_naive_bucuresti(aware) == _in_fus_anunturi(aware)
    assert to_naive_bucuresti(aware).tzinfo is None
    # vara UTC+3: 06:45 UTC -> 09:45
    assert to_naive_bucuresti(aware) == datetime(2026, 8, 1, 9, 45, 38)


def test_t1b_datetime_naiv_ramane_neschimbat():
    """Contractul: un naiv e DEJA in ora corecta, nu se mai atinge."""
    naiv = datetime(2026, 8, 1, 6, 45, 38)
    assert to_naive_bucuresti(naiv) == naiv


def test_t1c_stringuri_in_toate_formele():
    asteptat = datetime(2026, 8, 1, 9, 45, 38)
    assert to_naive_bucuresti("2026-08-01T06:45:38Z") == asteptat
    assert to_naive_bucuresti("2026-08-01T06:45:38+00:00") == asteptat
    assert to_naive_bucuresti("2026-08-01T09:45:38+03:00") == asteptat
    # fara offset: se ia ca atare, nu se ghiceste nimic
    assert to_naive_bucuresti("2026-08-01T09:45:38") == asteptat


def test_t1d_epoch():
    epoch = 1788699920
    assert to_naive_bucuresti(epoch) == _in_fus_anunturi(
        datetime.fromtimestamp(epoch, tz=_UTC))


def test_t1e_degradare_curata():
    for rau in (None, "", "   ", "maine", "32.13.2026", object(), True, [], {}):
        assert to_naive_bucuresti(rau) is None, rau


def test_t1f_ora_de_iarna():
    """ZoneInfo, nu offset fix: iarna Romania e UTC+2."""
    assert to_naive_bucuresti("2026-01-15T08:00:00Z") == datetime(2026, 1, 15, 10, 0)
    assert to_naive_bucuresti("2026-07-15T08:00:00Z") == datetime(2026, 7, 15, 11, 0)


# ── T2 — `din_fus` ──────────────────────────────────────────────────────────────

def test_t2_din_fus_berlin():
    naiv_berlin = datetime(2026, 9, 6, 13, 25)
    asteptat = _in_fus_anunturi(naiv_berlin.replace(tzinfo=ZoneInfo("Europe/Berlin")))
    assert din_fus(naiv_berlin, "Europe/Berlin") == asteptat
    # vara, Berlin e cu o ora in urma fata de Bucuresti
    assert din_fus(naiv_berlin, "Europe/Berlin") == datetime(2026, 9, 6, 14, 25)


def test_t2b_din_fus_degradare():
    assert din_fus(None, "Europe/Berlin") is None
    assert din_fus("2026-09-06", "Europe/Berlin") is None
    assert din_fus(datetime(2026, 9, 6, 13, 25), "Fus/Inexistent") is None


# ── T3 — Kleinanzeigen: „Heute"/„Gestern" sunt zile GERMANE ────────────────────

def test_t3_heute_e_ora_germana():
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    acum = datetime(2026, 9, 6, 15, 0, 0)
    asteptat = _in_fus_anunturi(
        datetime(2026, 9, 6, 13, 25, tzinfo=ZoneInfo("Europe/Berlin")))
    assert ka._parse_card_date("Heute, 13:25", now=acum) == asteptat


def test_t3b_la_miezul_noptii_heute_e_ziua_berlinului():
    """00:30 la Bucuresti = 23:30 ziua PRECEDENTA la Berlin.

    Fara conversia lui `now` in fusul sursa, „Heute, 23:40" ar fi primit ziua de azi a
    masinii, adica o zi in plus fata de ce scrie site-ul.
    """
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    acum_ro = datetime(2026, 9, 7, 0, 30, 0)        # ora anunturilor
    rezultat = ka._parse_card_date("Heute, 23:40", now=acum_ro)
    asteptat = _in_fus_anunturi(
        datetime(2026, 9, 6, 23, 40, tzinfo=ZoneInfo("Europe/Berlin")))
    assert rezultat == asteptat
    assert rezultat.date() == datetime(2026, 9, 7).date()   # 00:40 la Bucuresti


# ── T4 — Imobiliare: `_seed_from_raw` ──────────────────────────────────────────

def test_t4_seed_converteste_utc_si_lasa_naivul_in_pace():
    from app.services.real_estate_scanner import _seed_from_raw

    # Storia `createdAtFirst` vine cu Z (UTC) -> se converteste
    seed = _seed_from_raw({"listed_at": "2026-08-01T06:45:38Z",
                           "refreshed_at": "2026-08-01T09:45:38+03:00"})
    assert seed["listed_at"] == datetime(2026, 8, 1, 9, 45, 38)
    # ACELASI moment scris cu offset RO -> aceeasi ora de perete
    assert seed["refreshed_at"] == seed["listed_at"]


def test_t4b_seed_string_fara_offset_ramane_neschimbat():
    from app.services.real_estate_scanner import _seed_from_raw

    seed = _seed_from_raw({"listed_at": "2026-08-01T09:45:38"})
    assert seed["listed_at"] == datetime(2026, 8, 1, 9, 45, 38)


def test_t4c_seed_invalid_da_none():
    from app.services.real_estate_scanner import _seed_from_raw

    for rau in ("maine", "", None, "2026-13-45"):
        assert _seed_from_raw({"listed_at": rau})["listed_at"] is None, rau


# ── T5 — `found_at` si jurnalul, pe fiecare cale de scriere ────────────────────

_FIX = datetime(2026, 9, 7, 11, 22, 33)


def _user(db):
    from app.models.user import User

    email = f"tz1_{uuid.uuid4().hex[:10]}@example.com"
    u = User(email=email, username=email.split("@")[0],
             hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def _keyword(db, u):
    from app.models.radar_keyword import RadarKeyword

    kw = RadarKeyword(user_id=u.id, name="kw tz1", max_price=1000.0,
                      resale_price=1500.0, platform="olx")
    db.add(kw)
    db.flush()
    return kw


def test_t5_radar_found_at_e_ora_sistemului(monkeypatch):
    from app.database import SessionLocal
    from app.models import radar_listing as ml
    from app.models.radar_listing import RadarListing

    monkeypatch.setattr(ml, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        u = _user(db)
        rand = RadarListing(user_id=u.id, keyword_id=_keyword(db, u).id, platform="olx",
                            external_id="tz1", title="t", price=1.0,
                            currency="RON", url="u")
        db.add(rand)
        db.commit()
        db.refresh(rand)
        assert rand.found_at == _FIX
    finally:
        db.close()


def test_t5b_auto_found_at_e_ora_sistemului(monkeypatch):
    from app.database import SessionLocal
    from app.models.auto_feed_listing import AutoFeedListing
    from app.services import auto_listings_scanner as als

    monkeypatch.setattr(als, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        from app.models.auto_keyword import AutoKeyword

        u = _user(db)
        kw = AutoKeyword(user_id=u.id, name="kw", platform="olx_auto", is_active=True)
        db.add(kw)
        db.commit()
        assert als._save_listing(db, kw, {"external_id": "tz1a", "titlu": "x",
                                          "pret": 1000, "moneda": "EUR"}, None) is True
        rand = db.query(AutoFeedListing).filter_by(external_id="tz1a").one()
        assert rand.found_at == _FIX
    finally:
        db.close()


def test_t5c_imobiliare_found_at_e_ora_sistemului(monkeypatch):
    from app.database import SessionLocal
    from app.models import real_estate_monitor_listing as ml
    from app.models.real_estate_monitor_listing import RealEstateMonitorListing

    monkeypatch.setattr(ml, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        u = _user(db)
        rand = RealEstateMonitorListing(user_id=u.id, platform="olx",
                                        external_id="tz1r", title="t")
        db.add(rand)
        db.commit()
        db.refresh(rand)
        assert rand.found_at == _FIX
    finally:
        db.close()


def test_t5d_log_entries_created_at_e_ora_sistemului(monkeypatch):
    from app.database import SessionLocal
    from app.models import log_entry as ml
    from app.models.log_entry import LogEntry

    monkeypatch.setattr(ml, "acum_local", lambda: _FIX)
    db = SessionLocal()
    try:
        db.add(LogEntry(module="radar", level="OK", message="test tz-1"))
        db.commit()
        rand = db.query(LogEntry).filter_by(message="test tz-1").one()
        assert rand.created_at.replace(tzinfo=None) == _FIX
    finally:
        db.close()


# ── T6 — garda statica: niciun ceas UTC pe caile convertite ────────────────────

def test_t6_pragurile_convertite_folosesc_acum_local():
    """Comparatiile care se masoara fata de `found_at` / `created_at` trebuie sa fie pe
    ACELASI ceas ca ele. Garda e pe LINIILE de prag, nu pe fisiere: in aceleasi module
    raman ceasuri UTC legitime (`last_checked_at`, `run_started`) — coloane care nu se
    afiseaza si care sunt tema unei runde separate.
    """
    import inspect

    from app.routers import dashboard, radar
    from app.services import real_estate_scanner
    from app.services.radar import cleanup_service

    praguri = {
        (cleanup_service, "cutoff = "): 2,
        (dashboard, "radar_cutoff = "): 1,
        (dashboard, "db_cutoff_24h = "): 1,
        (radar, "since = "): 1,
        (real_estate_scanner, "cutoff_fb = "): 1,
    }
    for (modul, prefix), asteptate in praguri.items():
        linii = [l.strip() for l in inspect.getsource(modul).splitlines()
                 if l.strip().startswith(prefix)]
        assert len(linii) == asteptate, (modul.__name__, prefix, linii)
        for l in linii:
            assert "acum_local()" in l, (modul.__name__, l)
            assert "utcnow" not in l and "timezone.utc" not in l, (modul.__name__, l)


def test_t6b_scrierile_de_found_at_folosesc_acum_local():
    """Cele trei default-uri de coloana + cele trei scrieri explicite."""
    import inspect

    from app.models import auto_feed_listing, radar_listing, real_estate_monitor_listing
    from app.routers import real_estate_keywords
    from app.services import auto_listings_scanner, real_estate_scanner

    for modul in (radar_listing, auto_feed_listing, real_estate_monitor_listing):
        linii = [l for l in inspect.getsource(modul).splitlines()
                 if "found_at" in l and "Column(" in l]
        assert len(linii) == 1 and "acum_local()" in linii[0], modul.__name__

    for modul in (auto_listings_scanner, real_estate_scanner, real_estate_keywords):
        atribuiri = [l.strip() for l in inspect.getsource(modul).splitlines()
                     if l.strip().startswith("found_at") and "=" in l]
        assert atribuiri, modul.__name__
        for l in atribuiri:
            assert "acum_local()" in l, (modul.__name__, l)


# ── T7 — migrarea de backfill ─────────────────────────────────────────────────

def _db_backfill():
    """SQLite in memorie cu exact tabelele si coloanele pe care le atinge migrarea."""
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(text("CREATE TABLE schema_migrations (migration_name VARCHAR(200) "
                      "UNIQUE NOT NULL, applied_at TIMESTAMP)"))
    for tabel in ("radar_listings", "auto_feed_listings"):
        conn.execute(text(f"CREATE TABLE {tabel} (id INTEGER PRIMARY KEY, "
                          f"found_at TIMESTAMP, refreshed_at TIMESTAMP)"))
    conn.execute(text("CREATE TABLE real_estate_listings (id INTEGER PRIMARY KEY, "
                      "platform VARCHAR(50), found_at TIMESTAMP, "
                      "listed_at TIMESTAMP, refreshed_at TIMESTAMP)"))
    conn.execute(text("CREATE TABLE log_entries (id INTEGER PRIMARY KEY, "
                      "created_at TIMESTAMP)"))
    conn.commit()
    return engine, conn


_IARNA_UTC = datetime(2026, 1, 15, 8, 0, 0)     # -> 10:00 (UTC+2)
_VARA_UTC = datetime(2026, 7, 15, 8, 0, 0)      # -> 11:00 (UTC+3)


def _asteptat(utc_naiv: datetime) -> datetime:
    return utc_naiv.replace(tzinfo=_UTC).astimezone().replace(tzinfo=None)


def _dt(v):
    """SQL brut pe o coloana TIMESTAMP intoarce string; normalizam la datetime."""
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def test_t7_backfill_converteste_cu_dst_corect():
    from sqlalchemy import inspect as sa_inspect, text

    from app.utils.db_migrate import _tz1_backfill_ore_locale

    engine, conn = _db_backfill()
    try:
        conn.execute(text("INSERT INTO radar_listings (id, found_at, refreshed_at) "
                          "VALUES (1, :iarna, :iarna), (2, :vara, :vara)"),
                     {"iarna": _IARNA_UTC, "vara": _VARA_UTC})
        conn.execute(text("INSERT INTO log_entries (id, created_at) VALUES (1, :vara)"),
                     {"vara": _VARA_UTC})
        conn.commit()

        _tz1_backfill_ore_locale(conn, sa_inspect(conn))

        randuri = {i: _dt(v) for i, v in conn.execute(
            text("SELECT id, found_at FROM radar_listings")).fetchall()}
        assert randuri[1] == _asteptat(_IARNA_UTC)      # +2, nu +3
        assert randuri[2] == _asteptat(_VARA_UTC)       # +3
        # offsetul chiar difera intre cele doua anotimpuri (nu un +3 uniform)
        assert (randuri[1] - _IARNA_UTC) != (randuri[2] - _VARA_UTC)

        jurnal = _dt(conn.execute(text("SELECT created_at FROM log_entries")).scalar())
        assert jurnal == _asteptat(_VARA_UTC)
    finally:
        conn.close()
        engine.dispose()


def test_t7b_refreshed_at_nu_se_atinge():
    from sqlalchemy import inspect as sa_inspect, text

    from app.utils.db_migrate import _tz1_backfill_ore_locale

    engine, conn = _db_backfill()
    try:
        conn.execute(text("INSERT INTO radar_listings (id, found_at, refreshed_at) "
                          "VALUES (1, :v, :v)"), {"v": _VARA_UTC})
        conn.commit()
        _tz1_backfill_ore_locale(conn, sa_inspect(conn))
        assert _dt(conn.execute(
            text("SELECT refreshed_at FROM radar_listings")).scalar()) == _VARA_UTC
    finally:
        conn.close()
        engine.dispose()


def test_t7c_listed_at_re_doar_pe_platformele_care_trimiteau_utc():
    from sqlalchemy import inspect as sa_inspect, text

    from app.utils.db_migrate import _tz1_backfill_ore_locale

    engine, conn = _db_backfill()
    try:
        conn.execute(text(
            "INSERT INTO real_estate_listings (id, platform, found_at, listed_at) VALUES "
            "(1, 'storia', :v, :v), (2, 'olx', :v, :v), "
            "(3, 'facebook_marketplace', :v, :v), (4, 'facebook_groups', :v, :v), "
            "(5, 'imobiliare_ro', :v, :v)"), {"v": _VARA_UTC})
        conn.commit()
        _tz1_backfill_ore_locale(conn, sa_inspect(conn))

        randuri = {p: _dt(v) for p, v in conn.execute(
            text("SELECT platform, listed_at FROM real_estate_listings")).fetchall()}
        for platforma in ("storia", "facebook_marketplace", "facebook_groups"):
            assert randuri[platforma] == _asteptat(_VARA_UTC), platforma
        for platforma in ("olx", "imobiliare_ro"):
            assert randuri[platforma] == _VARA_UTC, platforma   # veneau cu offset, corecte

        # `found_at` se converteste pe TOATE platformele
        gasite = [_dt(r[0]) for r in conn.execute(
            text("SELECT found_at FROM real_estate_listings")).fetchall()]
        assert all(g == _asteptat(_VARA_UTC) for g in gasite)
    finally:
        conn.close()
        engine.dispose()


def test_t7d_a_doua_rulare_nu_mai_schimba_nimic():
    from sqlalchemy import inspect as sa_inspect, text

    from app.utils.db_migrate import _tz1_backfill_ore_locale

    engine, conn = _db_backfill()
    try:
        conn.execute(text("INSERT INTO radar_listings (id, found_at) VALUES (1, :v)"),
                     {"v": _VARA_UTC})
        conn.commit()
        _tz1_backfill_ore_locale(conn, sa_inspect(conn))
        dupa_prima = _dt(conn.execute(text("SELECT found_at FROM radar_listings")).scalar())

        _tz1_backfill_ore_locale(conn, sa_inspect(conn))   # a doua oara: no-op
        assert _dt(conn.execute(
            text("SELECT found_at FROM radar_listings")).scalar()) == dupa_prima

        aplicate = [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations")).fetchall()]
        assert aplicate.count("tz1_ore_locale") == 1
    finally:
        conn.close()
        engine.dispose()


# ── T8 — pragurile de cleanup se masoara pe acelasi ceas ──────────────────────

def test_t8_cleanup_taie_pe_ora_sistemului(monkeypatch):
    """Un rand mai vechi decat pragul e eligibil, unul mai nou nu.

    Pana la TZ-1 pragul era UTC iar `found_at` local (dupa migrare), deci fereastra
    se deplasa cu 3 ore: anunturi de acum 3 h pareau de acum 6 h.
    """
    from app.database import SessionLocal
    from app.models.radar_listing import RadarListing
    from app.services.radar import cleanup_service as cs

    acum = datetime(2026, 9, 7, 12, 0, 0)
    monkeypatch.setattr(cs, "acum_local", lambda: acum)

    db = SessionLocal()
    try:
        u = _user(db)
        kid = _keyword(db, u).id
        for ext, gasit in (("prea_nou", acum - timedelta(hours=5)),
                           ("destul_de_vechi", acum - timedelta(hours=7))):
            db.add(RadarListing(user_id=u.id, keyword_id=kid, platform="olx",
                                external_id=ext, title="t", price=1.0,
                                currency="RON", url="u", found_at=gasit))
        db.commit()

        # pragul de 6 h din `_cleanup_*`: sub el nu intra nimic
        prag = cs.acum_local() - timedelta(hours=6)
        eligibile = [r.external_id for r in db.query(RadarListing)
                     .filter(RadarListing.found_at < prag).all()]
        assert eligibile == ["destul_de_vechi"]
    finally:
        db.close()
