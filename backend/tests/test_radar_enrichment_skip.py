"""RP-3 — enrichment de detaliu DOAR pentru anunturi noi (skip pe external_id vazut).

Teste pure: fara retea, fara DB. Stub pe fetch_*_listing_details (inregistreaza URL-urile)
si pe time.sleep (numara apelurile) in fiecare modul. Testam direct _enrich_results
(Okazii/Publi24) si _enrich_details (LaJumate) — nu search_*, ca sa nu atingem reteaua.
"""
from app.services.radar import okazii_scraper, lajumate_scraper, publi24_scraper


def _items(prefix):
    return [
        {"external_id": f"{prefix}_{i}", "url": f"u{i}", "images": [], "description": None,
         "seller_name": None, "seller_id": None, "seller_rating": None, "seller_reviews": None,
         "listed_at": None, "extra_attributes": None}
        for i in (1, 2, 3)
    ]


def _patch(monkeypatch, module, fetch_name, extra=None):
    """Stub fetch + sleep in `module`. Returneaza (fetched_urls, sleeps)."""
    fetched_urls = []
    sleeps = []

    def _stub(url):
        fetched_urls.append(url)
        d = {"description": "desc-test", "images": ["img-test"]}
        if extra:
            d.update(extra)
        return d

    monkeypatch.setattr(module, fetch_name, _stub)
    monkeypatch.setattr(module.time, "sleep", lambda s: sleeps.append(s))
    return fetched_urls, sleeps


# ── Okazii ──────────────────────────────────────────────────────────────────────
def test_okazii_skip_partial(monkeypatch):
    items = _items("okazii")
    urls, sleeps = _patch(monkeypatch, okazii_scraper, "fetch_okazii_listing_details")
    assert okazii_scraper._enrich_results(items, {"okazii_1", "okazii_3"}) == (1, 2)
    assert urls == ["u2"]
    assert items[1]["description"] == "desc-test" and items[1]["images"] == ["img-test"]
    assert items[0]["description"] is None and items[2]["description"] is None
    assert sleeps == []


def test_okazii_no_skip(monkeypatch):
    items = _items("okazii")
    urls, sleeps = _patch(monkeypatch, okazii_scraper, "fetch_okazii_listing_details")
    assert okazii_scraper._enrich_results(items, None) == (3, 0)
    assert urls == ["u1", "u2", "u3"]
    assert len(sleeps) == 2


def test_okazii_all_skipped(monkeypatch):
    items = _items("okazii")
    urls, sleeps = _patch(monkeypatch, okazii_scraper, "fetch_okazii_listing_details")
    assert okazii_scraper._enrich_results(items, {"okazii_1", "okazii_2", "okazii_3"}) == (0, 3)
    assert urls == [] and sleeps == []


def test_okazii_seller_propagation(monkeypatch):
    items = _items("okazii")
    extra = {"seller_name": "X", "seller_rating": 4.5, "seller_reviews": 10, "okazii_seller_type": "magazin"}
    _patch(monkeypatch, okazii_scraper, "fetch_okazii_listing_details", extra=extra)
    okazii_scraper._enrich_results(items, {"okazii_1", "okazii_3"})  # doar item 2 imbogatit
    it = items[1]
    assert it["seller_name"] == "X"
    assert it["seller_rating"] == 4.5
    assert it["seller_reviews"] == 10
    assert it["extra_attributes"]["okazii_seller_type"] == "magazin"
    # itemele sarite raman fara vanzator
    assert items[0]["seller_name"] is None and items[2]["seller_name"] is None


# ── Publi24 ─────────────────────────────────────────────────────────────────────
def test_publi24_skip_partial(monkeypatch):
    items = _items("publi24")
    urls, sleeps = _patch(monkeypatch, publi24_scraper, "fetch_publi24_listing_details")
    assert publi24_scraper._enrich_results(items, {"publi24_1", "publi24_3"}) == (1, 2)
    assert urls == ["u2"]
    assert items[1]["description"] == "desc-test" and items[1]["images"] == ["img-test"]
    assert items[0]["description"] is None and items[2]["description"] is None
    assert sleeps == []


def test_publi24_no_skip(monkeypatch):
    items = _items("publi24")
    urls, sleeps = _patch(monkeypatch, publi24_scraper, "fetch_publi24_listing_details")
    assert publi24_scraper._enrich_results(items, None) == (3, 0)
    assert urls == ["u1", "u2", "u3"]
    assert len(sleeps) == 2


# ── LaJumate (prin _enrich_details) ─────────────────────────────────────────────
def test_lajumate_skip_partial(monkeypatch):
    items = _items("lajumate")
    urls, sleeps = _patch(monkeypatch, lajumate_scraper, "fetch_lajumate_listing_details")
    assert lajumate_scraper._enrich_details(items, {"lajumate_1", "lajumate_3"}) == (1, 2)
    assert urls == ["u2"]
    assert items[1]["description"] == "desc-test" and items[1]["images"] == ["img-test"]
    assert items[0]["description"] is None and items[2]["description"] is None
    assert sleeps == []


def test_lajumate_no_skip(monkeypatch):
    items = _items("lajumate")
    urls, sleeps = _patch(monkeypatch, lajumate_scraper, "fetch_lajumate_listing_details")
    assert lajumate_scraper._enrich_details(items, None) == (3, 0)
    assert urls == ["u1", "u2", "u3"]
    assert len(sleeps) == 2
