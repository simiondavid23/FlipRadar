"""DB-CLEAN — coloanele si tabela orfane ies din baza, modelul mort iese din cod.

Ce se dovedeste aici:
  * o baza PROASPATA nu mai capata `radar_keywords.car_filters`, nici toggle-urile
    `platform_autovit_enabled` / `platform_mobilede_enabled`, nici `marketplace_saved`
    sau `radar_presets`;
  * o baza VECHE (care le are) le pierde la prima rulare a migratiilor, iar cele
    patru migrari se inregistreaza in `schema_migrations`;
  * a doua rulare e inofensiva (garzile + `_applied`);
  * datele vecine din `radar_settings` supravietuiesc rescrierii de tabela pe care
    SQLite o face la DROP COLUMN.

Mecanismul de baza: conftest.py da o baza pe SESIUNE, deja migrata la importul lui
`app.main` — aici avem nevoie de una virgina PER scenariu, deci fiecare test isi
face propriul engine pe fisier temporar si il pinuim in `db_migrate` (run_migrations
citeste `engine` din globals-urile modulului). Baza sesiunii ramane neatinsa.
"""
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.utils import db_migrate

# Cele patru migrari introduse de DB-CLEAN.
MIGRARI = {
    "drop_radar_keywords_car_filters",
    "drop_radar_settings_platform_autovit_enabled",
    "drop_radar_settings_platform_mobilede_enabled",
    "drop_marketplace_saved_table",
}


@pytest.fixture
def baza_proaspata(monkeypatch, tmp_path):
    """Engine propriu pe fisier temporar, cu schema din modelele vii."""
    cale = tmp_path / f"dbclean_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{cale.as_posix()}")
    monkeypatch.setattr(db_migrate, "engine", engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


def _coloane(engine, tabela):
    return {c["name"] for c in inspect(engine).get_columns(tabela)}


def _tabele(engine):
    return set(inspect(engine).get_table_names())


def _aplicate(engine):
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT migration_name FROM schema_migrations"))]


def _imbatraneste(engine):
    """Reface pe o baza proaspata exact ce a mai ramas pe cele vechi."""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE radar_keywords ADD COLUMN car_filters TEXT"))
        conn.execute(text(
            "ALTER TABLE radar_settings ADD COLUMN platform_autovit_enabled "
            "BOOLEAN NOT NULL DEFAULT 1"))
        conn.execute(text(
            "ALTER TABLE radar_settings ADD COLUMN platform_mobilede_enabled "
            "BOOLEAN NOT NULL DEFAULT 1"))
        conn.execute(text(
            "CREATE TABLE marketplace_saved (id INTEGER PRIMARY KEY, user_id INTEGER)"))


def _fara_esecuri(capsys):
    """_migrate inghite exceptiile si le tipareste — deci un DROP negardat nu ar
    rupe suita, ci ar lasa doar o linie in iesire. O verificam explicit."""
    iesire = capsys.readouterr().out
    esuate = [l for l in iesire.splitlines() if "[DB Migrate] Failed" in l]
    assert not esuate, "\n".join(esuate)


# ── 1. Baza proaspata: ADD-urile istorice chiar au disparut ─────────────────────
def test_baza_proaspata_nu_are_orfanii(baza_proaspata, capsys):
    db_migrate.run_migrations()

    assert "car_filters" not in _coloane(baza_proaspata, "radar_keywords")
    setari = _coloane(baza_proaspata, "radar_settings")
    assert "platform_autovit_enabled" not in setari
    assert "platform_mobilede_enabled" not in setari

    tabele = _tabele(baza_proaspata)
    assert "marketplace_saved" not in tabele
    assert "radar_presets" not in tabele

    # Garzile de introspectie: pe o baza fara coloanele astea niciun DROP nu se
    # executa, deci nici nu se inregistreaza si nici nu esueaza.
    assert not (MIGRARI & set(_aplicate(baza_proaspata)))
    _fara_esecuri(capsys)


# ── 2. Baza veche: cele patru dispar si se inregistreaza ────────────────────────
def test_baza_veche_pierde_orfanii(baza_proaspata, capsys):
    _imbatraneste(baza_proaspata)
    assert "car_filters" in _coloane(baza_proaspata, "radar_keywords")
    assert "marketplace_saved" in _tabele(baza_proaspata)

    db_migrate.run_migrations()

    assert "car_filters" not in _coloane(baza_proaspata, "radar_keywords")
    setari = _coloane(baza_proaspata, "radar_settings")
    assert "platform_autovit_enabled" not in setari
    assert "platform_mobilede_enabled" not in setari
    assert "marketplace_saved" not in _tabele(baza_proaspata)

    assert MIGRARI <= set(_aplicate(baza_proaspata))
    _fara_esecuri(capsys)


# ── 3. Idempotenta ──────────────────────────────────────────────────────────────
def test_a_doua_rulare_e_inofensiva(baza_proaspata, capsys):
    _imbatraneste(baza_proaspata)
    db_migrate.run_migrations()
    inainte = _aplicate(baza_proaspata)
    capsys.readouterr()

    db_migrate.run_migrations()  # nu trebuie sa arunce

    dupa = _aplicate(baza_proaspata)
    assert sorted(dupa) == sorted(inainte)
    assert len(dupa) == len(set(dupa)), "duplicate in schema_migrations"
    _fara_esecuri(capsys)


# ── 4. Datele vecine supravietuiesc rescrierii de tabela ────────────────────────
def test_datele_vecine_supravietuiesc(baza_proaspata):
    _imbatraneste(baza_proaspata)
    with baza_proaspata.begin() as conn:
        conn.execute(text(
            "INSERT INTO radar_settings (user_id, platform_olx_enabled, "
            "platform_vinted_enabled, platform_okazii_enabled, "
            "platform_facebook_enabled, platform_lajumate_enabled, "
            "platform_publi24_enabled, deal_scan_enabled, updated_at) "
            "VALUES (1, 1, 1, 1, 0, 0, 1, 1, CURRENT_TIMESTAMP)"))

    db_migrate.run_migrations()

    with baza_proaspata.connect() as conn:
        rand = conn.execute(text(
            "SELECT user_id, platform_lajumate_enabled, platform_publi24_enabled "
            "FROM radar_settings")).fetchall()
    assert rand == [(1, 0, 1)]


# ── 5. Modelul mort nu mai e in registru ────────────────────────────────────────
def test_radarpreset_nu_mai_exista():
    assert "RadarPreset" not in {m.class_.__name__ for m in Base.registry.mappers}
    assert "radar_presets" not in Base.metadata.tables
