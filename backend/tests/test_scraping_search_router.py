"""SEARCH-1b — cele doua rute generice de cautare.

`search_service.search` si `.sources` se monkeypatcheaza IN `app.routers.scraping`,
deci testele nu ating nici reteaua, nici registrul: aici se verifica STRATUL DE
RUTARE (auth, validare, traducerea lui ValueError, aplicarea filtrului per-kind),
nu mecanismele — alea au test_search_service.py.
"""
import pytest

from app.routers import scraping as R


def _raspuns(kind, results, status="ok"):
    return {
        "source": "x.ro", "label": "X", "kind": kind, "status": status,
        "reason": None, "results": list(results), "count": len(results),
        "truncated": False, "more_url": None,
    }


# Doua produse, dintre care UNUL nu contine termenul cautat: `filter_by_relevance`
# il taie pe al doilea, deci diferenta filtrat/nefiltrat e vizibila in `count`.
_RELEVANT = {"name": "Placa video RTX 5070", "price": 3499.0, "sku": None, "ean": None}
_IRELEVANT = {"name": "Cafetiera Philips", "price": 199.0, "sku": None, "ean": None}


def test_sources_intoarce_lista(auth_client, monkeypatch):
    monkeypatch.setattr(R.search_service, "sources",
                        lambda: [{"domain": "a.ro", "label": "A"}])
    r = auth_client.get("/api/scraping/sources")
    assert r.status_code == 200
    assert r.json() == {"sources": [{"domain": "a.ro", "label": "A"}]}


def test_search_domeniu_necunoscut_da_404(auth_client, monkeypatch):
    def crapa(domain, query, max_results):
        raise ValueError(f"Magazin necunoscut: {domain}")

    monkeypatch.setattr(R.search_service, "search", crapa)
    r = auth_client.get("/api/scraping/search",
                        params={"domain": "nu-exista.ro", "q": "x"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Magazin necunoscut: nu-exista.ro"


def test_filtrul_se_aplica_pe_custom(auth_client, monkeypatch):
    monkeypatch.setattr(R.search_service, "search",
                        lambda d, q, m: _raspuns("custom", [_RELEVANT, _IRELEVANT]))
    r = auth_client.get("/api/scraping/search",
                        params={"domain": "altex.ro", "q": "rtx 5070",
                                "search_type": "name"})
    assert r.status_code == 200
    date = r.json()
    assert date["count"] == 1, "produsul irelevant trebuia taiat pe calea custom"
    assert date["results"][0]["name"] == "Placa video RTX 5070"


def test_filtrul_NU_se_aplica_pe_generic(auth_client, monkeypatch):
    """Controlul ca filtrul e PER-KIND, cu acelasi payload ca testul de mai sus.

    Pe mecanismele generice motorul magazinului a potrivit deja termenul, iar
    titlurile pot omite brandul cautat — masurat la SEARCH-0, bergfreunde raspunde la
    „salomon" cu „Xa Pro V8 Winter CSWP Junior Winter boots". Filtrul ar fi taiat
    acolo 72 din 72 de rezultate corecte.
    """
    monkeypatch.setattr(R.search_service, "search",
                        lambda d, q, m: _raspuns("shopify", [_RELEVANT, _IRELEVANT]))
    r = auth_client.get("/api/scraping/search",
                        params={"domain": "redgoblin.ro", "q": "rtx 5070",
                                "search_type": "name"})
    assert r.status_code == 200
    assert r.json()["count"] == 2, "pe generic nu se filtreaza nimic"


def test_filtrul_custom_care_goleste_da_empty(auth_client, monkeypatch):
    """`filter_by_relevance` reintroduce o sentinela `message` cand nu ramane nimic
    relevant. Nu are voie sa iasa din API ca produs — devine `status: empty`."""
    monkeypatch.setattr(R.search_service, "search",
                        lambda d, q, m: _raspuns("custom", [_IRELEVANT]))
    r = auth_client.get("/api/scraping/search",
                        params={"domain": "altex.ro", "q": "rtx 5070",
                                "search_type": "name"})
    assert r.status_code == 200
    date = r.json()
    assert date["status"] == "empty"
    assert date["results"] == [] and date["count"] == 0


def test_rutele_cer_login(client, monkeypatch):
    monkeypatch.setattr(R.search_service, "sources", lambda: [])
    monkeypatch.setattr(R.search_service, "search",
                        lambda d, q, m: _raspuns("shopify", []))
    assert client.get("/api/scraping/sources").status_code == 401
    assert client.get("/api/scraping/search",
                      params={"domain": "a.ro", "q": "x"}).status_code == 401


@pytest.mark.parametrize("params", [
    {"domain": "a.ro"},                 # q lipseste
    {"q": "x"},                         # domain lipseste
])
def test_parametrii_obligatorii(auth_client, monkeypatch, params):
    monkeypatch.setattr(R.search_service, "search",
                        lambda d, q, m: _raspuns("shopify", []))
    assert auth_client.get("/api/scraping/search", params=params).status_code == 422
