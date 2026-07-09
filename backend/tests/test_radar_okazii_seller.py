"""RP-1 — parserul de vânzător/rating Okazii (fragment .info-seller real, §6)."""
import os

from bs4 import BeautifulSoup

from app.services.radar.okazii_scraper import _extract_okazii_seller

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "okazii_info_seller.html")


def _soup() -> BeautifulSoup:
    with open(_FIX, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def test_seller_name_from_profile_title():
    s = _extract_okazii_seller(_soup())
    assert s["seller_name"] == "Service Boutique SRL"
    assert s["seller_id"] == "gsmboutique"


def test_rating_percent_to_0_5_and_reviews():
    s = _extract_okazii_seller(_soup())
    assert s["seller_rating"] == 4.8          # 96% / 20
    assert s["seller_reviews"] == 6382


def test_seller_type():
    s = _extract_okazii_seller(_soup())
    assert s["okazii_seller_type"].lower() == "companie"
