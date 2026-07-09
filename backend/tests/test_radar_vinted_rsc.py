"""RP-1 — extractorul RSC Vinted (pagina HTML, format React Flight __next_f).

Ruleaza pe fixture-ul salvat de sonda Fazei 0 (tests/fixtures/vinted_item_rsc.txt),
fara retea. Ingheata structura confirmata in S1.
"""
import os

from app.services.radar.vinted_scraper import _extract_item_rsc

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "vinted_item_rsc.txt")


def _rsc() -> str:
    with open(_FIX, encoding="utf-8") as f:
        return f.read()


def test_feedback_count_reputation_and_name():
    out = _extract_item_rsc(_rsc())
    assert out["seller_name"] == "karolo9696"
    assert out["seller_reviews"] == 48                 # feedback_count
    assert out["seller_rating"] == 5.0                 # feedback_reputation (1) × 5


def test_seller_badges():
    out = _extract_item_rsc(_rsc())
    assert "ACTIVE_LISTER" in out["seller_badges"]
    assert "SPEEDY_SHIPPING" in out["seller_badges"]


def test_item_attributes_ro_pairs():
    out = _extract_item_rsc(_rsc())
    attrs = out["attributes"]
    assert attrs.get("Brand") == "ETUI"
    assert attrs.get("Stare") == "Nou fără etichetă"
    assert attrs.get("Culoare") == "Alb"


def test_gallery_and_description():
    out = _extract_item_rsc(_rsc())
    assert len(out["images"]) >= 1
    assert all(u.startswith("http") for u in out["images"])
    assert "iPhone 12" in (out["description"] or "")
