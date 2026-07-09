"""RP-2 — parserul de arbore Vinted pe fixture-ul din Faza 0.

NOTĂ: fixture-ul (tests/fixtures/vinted_catalog_rsc.txt) e structural FIDEL evidenței
RP-DIAG-2 (câmp copii `catalogs`; nod {id, title, code, catalogs}), construit manual
fiindcă /catalog era blocat de DataDome pe IP-ul de datacenter la implementare.
"""
import os

from app.services.radar.vinted_catalog_service import _extract_catalog_roots, build_catalog_nodes

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "vinted_catalog_rsc.txt")


def _roots():
    with open(_FIX, encoding="utf-8") as f:
        return _extract_catalog_roots(f.read())


def test_extract_child_field_and_roots():
    roots, child_field = _roots()
    assert child_field == "catalogs"
    assert len(roots) == 3
    assert {r["title"] for r in roots} == {"Femei", "Bărbați", "Copii"}


def test_build_nodes_parent_path_depth():
    roots, child_field = _roots()
    nodes = build_catalog_nodes(roots, child_field)
    by_id = {n["id"]: n for n in nodes}
    assert len(nodes) == 9
    assert by_id[1904]["parent_id"] is None and by_id[1904]["depth"] == 0
    assert by_id[4]["parent_id"] == 1904
    assert by_id[4]["path"] == "Femei > Îmbrăcăminte" and by_id[4]["depth"] == 1
    assert by_id[10]["path"] == "Femei > Îmbrăcăminte > Rochii" and by_id[10]["depth"] == 2
    assert by_id[3662]["path"] == "Bărbați > Telefoane > iPhone" and by_id[3662]["parent_id"] == 3661


def test_nodes_dedup_and_code():
    roots, child_field = _roots()
    nodes = build_catalog_nodes(roots, child_field)
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids))  # fără duplicate
    assert {n["id"]: n["code"] for n in nodes}[3661] == "PHONES"


def test_build_nodes_skips_invalid_entries():
    # Flight poate presăra referințe ($..) / intrări incomplete -> sunt sărite.
    roots = [
        {"id": 1, "title": "OK", "catalogs": [{"title": "fără id"}, "$ref", {"id": 2, "title": "Copil"}]},
    ]
    nodes = build_catalog_nodes(roots, "catalogs")
    assert {n["id"] for n in nodes} == {1, 2}
