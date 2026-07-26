"""FASHION-1a — dimensiunea `variant` (marimea) pe ProductSource si PriceHistory.

Doua straturi, fara retea:
- migrarea portabila (engine SQLite temporar, ca la testul de migrare din
  test_products_from_url): rebuild-ul tabelei product_sources cu unique-ul pe
  triplet, ADD COLUMN pe price_history, idempotenta si paritatea intre schema
  migrata si cea produsa de create_all();
- codul variant-aware pe baza de test (SessionLocal + stub-uri, ca in
  test_retail_alerts): attach, minimul pe 30 de zile separat pe varianta,
  bucla de refresh si lookup-ul in_stock din adaugarea prin link.

Convenția: '' = fara varianta. Dupa acest task comportamentul e identic cu cel
de dinainte (variant e '' peste tot) — extractorul si UI-ul vin in FASHION-1b.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_source import ProductSource
from app.models.radar_settings import RadarSettings
from app.models.user import User
from app.services import catalog_health_watchdog
from app.utils.alert_checker import _refresh_all_scrapeable_products
from app.utils.db_migrate import _column_exists, _portable_migrations

URL = "https://www.emag.ro/tricou-fashion/pd/F1A/"

# Schema DINAINTE de FASHION-1a: unique pe (product_id, source), fara variant.
OLD_PRODUCT_SOURCES = """
    CREATE TABLE product_sources (
        id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        source_url VARCHAR NOT NULL,
        current_price FLOAT,
        currency VARCHAR NOT NULL,
        in_stock BOOLEAN,
        last_checked_at DATETIME,
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id),
        CONSTRAINT uq_product_source UNIQUE (product_id, source),
        FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
    )
"""
OLD_PRICE_HISTORY = """
    CREATE TABLE price_history (
        id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        price FLOAT NOT NULL,
        currency VARCHAR,
        source VARCHAR,
        recorded_at DATETIME,
        PRIMARY KEY (id),
        FOREIGN KEY(product_id) REFERENCES products (id)
    )
"""


def _legacy_engine(tmp_path, name="fashion1a.db"):
    """Baza SQLite temporara cu schema VECHE + date, gata de migrat."""
    engine = create_engine(f"sqlite:///{(tmp_path / name).as_posix()}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR)"))
        conn.execute(text(OLD_PRODUCT_SOURCES))
        for stmt in (
            "CREATE INDEX ix_product_sources_id ON product_sources (id)",
            "CREATE INDEX ix_product_sources_product_id ON product_sources (product_id)",
            "CREATE INDEX ix_product_sources_source ON product_sources (source)",
        ):
            conn.execute(text(stmt))
        conn.execute(text(OLD_PRICE_HISTORY))
        conn.execute(text("CREATE TABLE schema_migrations ("
                          "migration_name TEXT UNIQUE NOT NULL, applied_at TIMESTAMP)"))
        conn.execute(text("INSERT INTO products (id, name) VALUES (1, 'Tricou')"))
        # Doua surse pe acelasi produs (exact ce trebuie sa supravietuiasca rebuild-ului).
        conn.execute(text(
            "INSERT INTO product_sources "
            "(id, product_id, source, source_url, current_price, currency, in_stock, "
            " last_checked_at, created_at, updated_at) VALUES "
            "(1, 1, 'emag.ro', 'https://emag.ro/a', 100.0, 'RON', 1, "
            " '2026-01-02 10:00:00', '2026-01-01 09:00:00', '2026-01-02 10:00:00'), "
            "(2, 1, 'altex.ro', 'https://altex.ro/a', 120.5, 'RON', NULL, "
            " NULL, '2026-01-01 09:30:00', '2026-01-01 09:30:00')"))
        conn.execute(text(
            "INSERT INTO price_history (id, product_id, price, currency, source, recorded_at) "
            "VALUES (1, 1, 110.0, 'RON', 'emag.ro', '2026-01-01 09:00:00'), "
            "       (2, 1, 100.0, 'RON', 'emag.ro', '2026-01-02 10:00:00')"))
        conn.commit()
    return engine


def _run_migrations(engine):
    with engine.connect() as conn:
        _portable_migrations(conn, inspect(engine))


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


# ── migrarea ──────────────────────────────────────────────────────────────────

def test_migrarea_adauga_variant_si_pastreaza_datele(tmp_path):
    """Rebuild-ul tabelei nu pierde niciun rand si pune '' peste tot."""
    engine = _legacy_engine(tmp_path)
    _run_migrations(engine)

    assert _column_exists(inspect(engine), "product_sources", "variant")
    rows = _rows(engine, "SELECT id, product_id, source, source_url, current_price, "
                         "currency, in_stock, variant, last_checked_at, created_at, "
                         "updated_at FROM product_sources ORDER BY id")
    assert len(rows) == 2
    assert rows[0] == (1, 1, "emag.ro", "https://emag.ro/a", 100.0, "RON", 1, "",
                       "2026-01-02 10:00:00", "2026-01-01 09:00:00", "2026-01-02 10:00:00")
    assert rows[1] == (2, 1, "altex.ro", "https://altex.ro/a", 120.5, "RON", None, "",
                       None, "2026-01-01 09:30:00", "2026-01-01 09:30:00")
    engine.dispose()


def test_unique_ul_nou_respinge_duplicatul_dar_accepta_alta_marime(tmp_path):
    """Constrangerea e pe triplet: acelasi (produs, sursa, '') pica, marimea trece."""
    engine = _legacy_engine(tmp_path)
    _run_migrations(engine)

    insert = ("INSERT INTO product_sources "
              "(product_id, source, source_url, currency, variant) "
              "VALUES (1, 'emag.ro', 'https://emag.ro/dup', 'RON', :v)")
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text(insert), {"v": ""})
        conn.rollback()
        conn.execute(text(insert), {"v": "42"})
        conn.commit()

    variants = [r[0] for r in _rows(engine, "SELECT variant FROM product_sources "
                                            "WHERE source = 'emag.ro' ORDER BY id")]
    assert variants == ["", "42"]
    engine.dispose()


def test_migrarea_e_idempotenta(tmp_path):
    """A doua rulare nu re-executa nimic: cate o singura intrare inregistrata."""
    engine = _legacy_engine(tmp_path)
    _run_migrations(engine)
    _run_migrations(engine)  # fara exceptii

    with engine.connect() as conn:
        applied = dict(conn.execute(text(
            "SELECT migration_name, count(*) FROM schema_migrations "
            "WHERE migration_name IN ('rebuild_product_sources_variant', "
            "'add_price_history_variant') GROUP BY migration_name")).fetchall())
    assert applied == {"rebuild_product_sources_variant": 1, "add_price_history_variant": 1}
    # Datele au ramas intacte dupa a doua trecere.
    assert _rows(engine, "SELECT count(*) FROM product_sources")[0][0] == 2
    engine.dispose()


def test_schema_migrata_e_identica_cu_cea_din_create_all(tmp_path):
    """Paritate: acelasi set de coloane, aceleasi indexuri, acelasi refuz al
    duplicatului — indiferent daca baza a fost migrata sau creata de la zero."""
    from app.database import Base

    migrated = _legacy_engine(tmp_path, "migrata.db")
    _run_migrations(migrated)

    fresh = create_engine(f"sqlite:///{(tmp_path / 'noua.db').as_posix()}")
    Base.metadata.create_all(bind=fresh)

    def _cols(engine):
        return {c["name"] for c in inspect(engine).get_columns("product_sources")}

    def _idx(engine):
        return {i["name"] for i in inspect(engine).get_indexes("product_sources")}

    assert _cols(migrated) == _cols(fresh)
    assert "variant" in _cols(fresh)
    expected_idx = {"ix_product_sources_id", "ix_product_sources_product_id",
                    "ix_product_sources_source"}
    assert expected_idx <= _idx(migrated)
    assert _idx(migrated) == _idx(fresh)

    # Duplicatul (produs, sursa, '') e respins pe AMBELE cai.
    dup = ("INSERT INTO product_sources "
           "(product_id, source, source_url, currency, variant) "
           "VALUES (7, 'emag.ro', 'https://emag.ro/x', 'RON', '')")
    for engine in (migrated, fresh):
        with engine.connect() as conn:
            conn.execute(text(dup))
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(dup))
            conn.rollback()

    migrated.dispose()
    fresh.dispose()


def test_price_history_primeste_variant_gol_pe_randurile_vechi(tmp_path):
    engine = _legacy_engine(tmp_path)
    _run_migrations(engine)

    assert _column_exists(inspect(engine), "price_history", "variant")
    rows = _rows(engine, "SELECT id, price, source, variant FROM price_history ORDER BY id")
    assert rows == [(1, 110.0, "emag.ro", ""), (2, 100.0, "emag.ro", "")]
    engine.dispose()


def test_migrate_steps_da_inapoi_si_ddl_ul_pe_esec(tmp_path):
    """Garantia helperului: un esec dupa un DROP nu lasa baza injumatatita.
    (pysqlite ruleaza DDL in autocommit, deci fara tranzactie explicita tabela
    stearsa ar fi ramas stearsa iar migrarea s-ar fi reluat la infinit.)"""
    from app.utils.db_migrate import _migrate_steps

    engine = create_engine(f"sqlite:///{(tmp_path / 'atomic.db').as_posix()}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT)"))
        conn.execute(text("INSERT INTO t (id, a) VALUES (1, 'pastrat')"))
        conn.execute(text("CREATE TABLE schema_migrations ("
                          "migration_name TEXT UNIQUE NOT NULL, applied_at TIMESTAMP)"))
        conn.commit()
        _migrate_steps(conn, "probe_atomic", [
            "CREATE TABLE t_new (id INTEGER PRIMARY KEY, a TEXT)",
            "DROP TABLE t",
            "INSERT INTO t_new SELECT * FROM tabela_inexistenta",   # boom, dupa DROP
        ])

    tables = set(inspect(engine).get_table_names())
    assert "t" in tables and "t_new" not in tables
    assert _rows(engine, "SELECT id, a FROM t") == [(1, "pastrat")]
    # Nu s-a inregistrat nimic -> se reia curat la boot-ul urmator.
    assert _rows(engine, "SELECT count(*) FROM schema_migrations "
                         "WHERE migration_name = 'probe_atomic'")[0][0] == 0
    engine.dispose()


# ── codul variant-aware (pe baza de test) ─────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_watchdog():
    catalog_health_watchdog._reset_state()


def _mk_user(db, with_webhook=False):
    uniq = uuid.uuid4().hex[:10]
    user = User(email=f"f1a_{uniq}@example.com", username=f"f1a_{uniq}", hashed_password="x")
    db.add(user)
    db.flush()
    if with_webhook:
        db.add(RadarSettings(user_id=user.id,
                             discord_webhook_alerts="https://discord.com/api/webhooks/t/t"))
    return user


def _mk_product(db, user, price=100.0):
    p = Product(user_id=user.id, name="Tricou F1A", current_price=price, currency="RON")
    db.add(p)
    db.flush()
    return p


def _sources(product_id):
    db = SessionLocal()
    try:
        return {s.variant: s for s in db.query(ProductSource)
                .filter(ProductSource.product_id == product_id)
                .order_by(ProductSource.id).all()}
    finally:
        db.close()


def _history(product_id):
    db = SessionLocal()
    try:
        return db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id).order_by(PriceHistory.id).all()
    finally:
        db.close()


def test_attach_cu_varianta_creeaza_rand_separat_si_il_reactualizeaza():
    """(sursa, '42') e alt rand decat (sursa, ''); al doilea attach pe '42' il
    actualizeaza pe acelasi, iar istoricul poarta varianta."""
    from app.routers.products import attach_source_to_product

    db = SessionLocal()
    try:
        user = _mk_user(db)
        p = _mk_product(db, user)
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", variant=""))
        db.commit()
        pid = p.id

        attach_source_to_product(db, p, "emag.ro", URL + "?size=42", 90.0, "RON",
                                 variant="42")
        assert len(_sources(pid)) == 2

        attach_source_to_product(db, p, "emag.ro", URL + "?size=42", 85.0, "RON",
                                 variant="42")
    finally:
        db.close()

    rows = _sources(pid)
    assert set(rows) == {"", "42"}
    assert rows[""].current_price == 100.0           # randul fara varianta, neatins
    assert rows["42"].current_price == 85.0          # acelasi rand, actualizat
    assert [(h.price, h.variant) for h in _history(pid)] == [(90.0, "42"), (85.0, "42")]


def test_attach_fara_varianta_actualizeaza_randul_gol():
    """Back-compat exact: apelul fara `variant` ramane pe randul fara varianta,
    chiar daca sursa are deja un rand pe marime."""
    from app.routers.products import attach_source_to_product

    db = SessionLocal()
    try:
        user = _mk_user(db)
        p = _mk_product(db, user)
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", variant=""))
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL + "?size=42",
                             current_price=70.0, currency="RON", variant="42"))
        db.commit()
        pid = p.id

        attach_source_to_product(db, p, "emag.ro", URL, 95.0, "RON")
    finally:
        db.close()

    rows = _sources(pid)
    assert len(rows) == 2
    assert rows[""].current_price == 95.0
    assert rows["42"].current_price == 70.0          # marimea nu a fost atinsa
    assert [(h.price, h.variant) for h in _history(pid)] == [(95.0, "")]


def test_minimul_pe_30_zile_nu_amesteca_marimile(monkeypatch):
    """Flash-ul declansat pe randul '42' primeste minimul lui '42', nu pe al
    randului fara varianta (aceeasi sursa, preturi complet diferite)."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        user = _mk_user(db, with_webhook=True)
        p = _mk_product(db, user)
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", variant="42"))
        db.add(PriceHistory(product_id=p.id, price=90.0, currency="RON",
                            source="emag.ro", variant="42",
                            recorded_at=now - timedelta(days=3)))
        # Zgomot: aceeasi sursa, ALTA marime, minim mult mai mic.
        db.add(PriceHistory(product_id=p.id, price=10.0, currency="RON",
                            source="emag.ro", variant="",
                            recorded_at=now - timedelta(days=3)))
        db.commit()
    finally:
        db.close()

    captured = {}

    def _fake_embed(**kw):
        captured.update(kw)
        return {"fields": []}

    monkeypatch.setattr("app.utils.alert_checker.build_flash_deal_embed", _fake_embed)
    monkeypatch.setattr("app.utils.alert_checker.send_price_alert_notification",
                        lambda embed, settings, listing_id: True)
    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 80.0, "in_stock": None, "method": "url"})

    work = SessionLocal()
    try:
        _refresh_all_scrapeable_products(work)
    finally:
        work.close()

    assert captured["min_30d"] == 90.0


def test_bucla_de_refresh_scrie_istoricul_pe_varianta(monkeypatch):
    """Randul nou de PriceHistory mosteneste varianta sursei refrescate."""
    db = SessionLocal()
    try:
        user = _mk_user(db)
        p = _mk_product(db, user)
        db.add(ProductSource(product_id=p.id, source="emag.ro", source_url=URL,
                             current_price=100.0, currency="RON", variant="42"))
        db.commit()
        pid = p.id
    finally:
        db.close()

    # Pret in CRESTERE: izoleaza istoricul de fluxul de flash deal.
    monkeypatch.setattr("app.utils.alert_checker.refresh_source",
                        lambda **kw: {"price": 120.0, "in_stock": None, "method": "url"})

    work = SessionLocal()
    try:
        _refresh_all_scrapeable_products(work)
    finally:
        work.close()

    assert [(h.price, h.variant) for h in _history(pid)] == [(120.0, "42")]


def test_from_url_scrie_in_stock_pe_randul_fara_varianta(auth_client, monkeypatch):
    """Adaugarea prin link opereaza doar pe randul '' — chiar si cand randul pe
    marime are un id mai mic si un `.first()` nefiltrat l-ar fi prins pe el."""
    import app.routers.products as products

    res = {
        "name": "Tricou F1A", "price": 899.0, "currency": "RON", "in_stock": True,
        "is_aggregate": False, "image_url": None, "canonical_url": URL,
        "domain": "emag.ro", "method": "jsonld", "override_applied": False,
    }
    monkeypatch.setattr(products, "extract_product", lambda url, max_retries=3: dict(res))
    monkeypatch.setattr(products, "fetch_ean_from_url", lambda *a, **k: None)
    monkeypatch.setattr(products, "find_cross_shop_matches",
                        lambda *a, **k: {"ean_matches": [], "name_candidates": []})

    r = auth_client.post("/api/products/from-url", json={"url": URL})
    assert r.status_code == 200, r.text
    pid = r.json()["product"]["id"]

    # Rescriem sursele astfel incat randul pe marime sa aiba id-ul MAI MIC.
    db = SessionLocal()
    try:
        db.query(ProductSource).filter(ProductSource.product_id == pid).delete()
        db.add(ProductSource(product_id=pid, source="emag.ro", source_url=URL + "?size=42",
                             current_price=899.0, currency="RON", variant="42",
                             in_stock=False))
        db.commit()
        db.add(ProductSource(product_id=pid, source="emag.ro", source_url=URL,
                             current_price=899.0, currency="RON", variant="",
                             in_stock=False))
        db.commit()
    finally:
        db.close()

    rows = _sources(pid)
    assert rows["42"].id < rows[""].id, "premisa testului: marimea are id-ul mai mic"

    assert auth_client.post("/api/products/from-url", json={"url": URL}).status_code == 200

    rows = _sources(pid)
    assert rows[""].in_stock is True      # stocul a mers pe randul fara varianta
    assert rows["42"].in_stock is False   # marimea a ramas neatinsa
