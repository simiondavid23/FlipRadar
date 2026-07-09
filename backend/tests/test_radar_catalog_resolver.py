"""RP-2 — resolver Vinted cu precedență: config > DB (vinted_catalogs) > hartă."""
from app.services.radar.vinted_scraper import _resolve_vinted_catalog_id
from app.models.vinted_catalog import VintedCatalog
from app.database import SessionLocal


def test_config_wins_over_everything():
    cid = _resolve_vinted_catalog_id(
        "Femei > Haine", "Rochii", db=None, marketplace_config={"vinted_catalog_id": 999},
    )
    assert cid == 999


def test_db_wins_over_map():
    db = SessionLocal()
    try:
        db.query(VintedCatalog).delete()
        db.add(VintedCatalog(id=77777, parent_id=None, title="Telefoane",
                             code="PHONES", path="Bărbați > Telefoane", depth=1))
        db.commit()
        cid = _resolve_vinted_catalog_id(
            "Bărbați > Telefoane", "Telefoane", db=db, marketplace_config=None,
        )
        assert cid == 77777
    finally:
        db.query(VintedCatalog).delete()
        db.commit()
        db.close()


def test_map_fallback_when_no_config_no_db():
    # Fără config și fără db -> harta hardcodată (int sau None, nu crapă).
    cid = _resolve_vinted_catalog_id("Femei > Haine", "Rochii", db=None, marketplace_config=None)
    assert cid is None or isinstance(cid, int)


def test_empty_db_falls_through_to_map():
    db = SessionLocal()
    try:
        db.query(VintedCatalog).delete()
        db.commit()
        # DB gol -> find întoarce None -> cade pe hartă (nu explodează).
        cid = _resolve_vinted_catalog_id("Femei > Haine", "Rochii", db=db, marketplace_config=None)
        assert cid is None or isinstance(cid, int)
    finally:
        db.close()
