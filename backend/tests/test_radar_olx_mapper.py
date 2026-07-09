"""RP-1 — mapperul OLX offers -> câmpuri (funcție pură, fixture anonimizat)."""
import json
import os

from app.services.radar.olx_scraper import _map_olx_offer

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "olx_offer.json")


def _data() -> dict:
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)["data"]


def test_seller_fields():
    out = _map_olx_offer(_data())
    assert out["seller_name"] == "Test Seller"
    assert out["seller_id"] == "280047905"
    assert out["olx_member_since"] == 2019


def test_listed_at_is_naive_local():
    out = _map_olx_offer(_data())
    assert out["listed_at"].tzinfo is None  # convertit la naiv local (conventia listed_at)


def test_description_html_stripped():
    out = _map_olx_offer(_data())
    assert "<p>" not in out["description"]
    assert "stare foarte buna" in out["description"]


def test_empty_or_none_input():
    assert _map_olx_offer({}) == {}
    assert _map_olx_offer(None) == {}
