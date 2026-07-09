"""RP-2-probe — parserul de arbore pe FIXTURE REAL Vinted (arbore live, IP nou 2026-07-10).

Fixture-ul (tests/fixtures/vinted_catalog_roots_real.json) e extras din /catalog LIVE:
primele 2 rădăcini (Femei, Bărbați) cu subarborii compleți, restul rădăcinilor cu copiii
goliți. NU modifică testele/fixture-ul sintetic existente (test_radar_catalog_parser.py).
"""
import json
import os

from app.services.radar.vinted_catalog_service import build_catalog_nodes
from app.services.radar.exclusion_engine import normalize

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "vinted_catalog_roots_real.json")
_TARGETS = {"femei", "barbati", "copii", "casa", "electronice"}


def _data():
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _nodes():
    d = _data()
    return build_catalog_nodes(d["roots"], d["child_field"])


def test_real_fixture_at_least_100_nodes():
    assert len(_nodes()) >= 100


def test_real_fixture_target_roots():
    root_titles = [normalize(r["title"]) for r in _data()["roots"]]
    hits = {t for t in _TARGETS if any(t in rt for rt in root_titles)}
    assert len(hits) >= 2, f"rădăcini-țintă găsite: {hits}"


def test_real_fixture_has_depth2_paths():
    nodes = _nodes()
    assert any(n["depth"] >= 2 for n in nodes)
    # o cale reală de exemplu, cu părinte corect
    deep = [n for n in nodes if n["depth"] >= 2]
    assert all(n["parent_id"] is not None for n in deep)
