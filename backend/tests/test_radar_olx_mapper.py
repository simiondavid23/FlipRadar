"""RP-1 — mapperul OLX offers -> câmpuri (funcție pură, fixture anonimizat).
RP-7 — mapperul de rating vânzător + fluxul fetch_olx_seller_rating (curl mockuit)."""
import json
import os

from app.services.radar import olx_scraper
from app.services.radar.olx_scraper import (
    _map_olx_offer,
    _map_olx_rating,
    fetch_olx_seller_rating,
)

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


# ── RP-7 — rating vânzător ────────────────────────────────────────────────────

class _Resp:
    """Răspuns curl_cffi fals (doar status_code + .json())."""
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _fake_get(users_resp, rating_resp):
    """Întoarce un curl_requests.get fals care ramifică pe URL (users vs rating-cdn)."""
    def _get(url, **kwargs):
        if "/api/v1/users/" in url:
            return users_resp
        if "rating-cdn" in url and "eligibleClusters" in url:
            return rating_resp
        raise AssertionError(f"URL neașteptat în test: {url}")
    return _get


def test_map_rating_value_and_count():
    # forma reală RP-DIAG-2: scoreDetails.value=5.0 + scoreDetails.ratings.totalCount=1
    clusters = {"clusters": [{"name": "Seller", "scoreDetails": {
        "value": 5.0, "details": {"stars_5": 1},
        "ratings": {"totalCount": 1, "validCount": 1, "deletedCount": 0}}}]}
    assert _map_olx_rating(clusters) == {"seller_rating": 5.0, "seller_reviews": 1}


def test_map_rating_missing_structures():
    assert _map_olx_rating(None) == {}
    assert _map_olx_rating({}) == {}
    assert _map_olx_rating({"clusters": []}) == {}
    assert _map_olx_rating({"clusters": [None]}) == {}
    assert _map_olx_rating({"clusters": [{}]}) == {}
    assert _map_olx_rating({"clusters": [{"scoreDetails": None}]}) == {}
    assert _map_olx_rating({"clusters": [{"scoreDetails": {}}]}) == {}


def test_map_rating_no_reviews():
    # 0 recenzii: scoreDetails prezent cu ratings.totalCount=0 dar FĂRĂ value (nicio medie)
    # -> seller_reviews:0, fără seller_rating (nu inventăm 0 pentru medie).
    clusters = {"clusters": [{"scoreDetails": {"ratings": {"totalCount": 0}}}]}
    out = _map_olx_rating(clusters)
    assert out == {"seller_reviews": 0}
    assert "seller_rating" not in out


def test_fetch_seller_rating_ok(monkeypatch):
    users = _Resp(200, {"data": {"uuid": "60d8c57b-2b2a-41ce-946b-032675ee29b9"}})
    rating = _Resp(200, {"clusters": [{"scoreDetails": {
        "value": 5.0, "ratings": {"totalCount": 1}}}]})
    monkeypatch.setattr(olx_scraper.curl_requests, "get", _fake_get(users, rating))
    assert fetch_olx_seller_rating("196874128") == {"seller_rating": 5.0, "seller_reviews": 1}


def test_fetch_seller_rating_no_uuid(monkeypatch):
    users = _Resp(200, {"data": {"name": "Eduard"}})  # fără uuid
    monkeypatch.setattr(olx_scraper.curl_requests, "get", _fake_get(users, _Resp(200, {})))
    assert fetch_olx_seller_rating("1") == {}


def test_fetch_seller_rating_users_500(monkeypatch):
    monkeypatch.setattr(olx_scraper.curl_requests, "get", _fake_get(_Resp(500, {}), _Resp(200, {})))
    assert fetch_olx_seller_rating("1") == {}


def test_fetch_seller_rating_rating_500(monkeypatch):
    users = _Resp(200, {"data": {"uuid": "abc"}})
    monkeypatch.setattr(olx_scraper.curl_requests, "get", _fake_get(users, _Resp(500, {})))
    assert fetch_olx_seller_rating("1") == {}


def test_fetch_seller_rating_no_seller_id():
    assert fetch_olx_seller_rating(None) == {}
    assert fetch_olx_seller_rating("") == {}
