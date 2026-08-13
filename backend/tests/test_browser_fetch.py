"""BR-1 — harness-ul de browser ca a treia cale de fetch.

ZERO patchright real aici: sesiunea de browser e monkeypatch-uita peste tot, iar
testele acopera exact ce e logica proprie a harness-ului si a dispecerului —
alegerea caii de fetch si intervalul minim per domeniu. Randarea insasi e
raspunderea sondelor live (G4/G4b), nu a suitei.
"""
import pytest

from app.services import browser_fetch as bf
from app.services import product_page_extractor as ppe
from app.services.product_page_extractor import ProductExtractionError


PAGINA = """<html><head>
  <script type="application/ld+json">
    {"@type": "Product", "name": "Ruj mat 03",
     "offers": {"@type": "Offer", "price": "89.90", "priceCurrency": "RON",
                "availability": "https://schema.org/InStock"}}
  </script>
</head><body><h1>Ruj mat 03</h1></body></html>"""


def test_dispecerizare_browser(monkeypatch):
    """Domeniile `method: "browser"` trec prin harness; restul catalogului nu-l atinge.

    Rezultatul harness-ului intra in ACELASI parse_product_html, deci apelantii nu
    vad nicio diferenta fata de o pagina luata cu curl.
    """
    apeluri = []

    def fals_fetch(url, domain, valideaza=None):
        apeluri.append((url, domain))
        # Dispecerul trebuie sa dea un callback de validare, altfel poll-ul din
        # harness n-ar avea cum sa stie ca pagina e gata.
        assert valideaza is not None, "dispecerul trebuie sa trimita validarea"
        valideaza(PAGINA)
        return PAGINA

    monkeypatch.setattr(bf, "fetch_browser_html", fals_fetch)

    res = ppe.extract_product("https://makeup.ro/product/181283/")

    assert apeluri == [("https://makeup.ro/product/181283/", "makeup.ro")]
    assert res["price"] == 89.90
    assert res["currency"] == "RON"
    assert res["name"] == "Ruj mat 03"
    assert res["method"] == "jsonld"      # calea de FETCH difera, parsarea nu

    # Control negativ: un domeniu jsonld obisnuit nu ajunge la harness. Poarta de
    # fetch e mock-uita ca sa nu iasa nimic pe retea daca dispecerizarea greseste.
    def fara_retea(*args, **kwargs):
        raise AssertionError("nu se face fetch HTTP in acest test")

    monkeypatch.setattr("app.services.scraper_service._fetch_shop_url_guarded", fara_retea)
    with pytest.raises(AssertionError):
        ppe.extract_product("https://www.emag.ro/laptop/pd/XYZ/")
    assert len(apeluri) == 1, "domeniul non-browser a intrat totusi in harness"


def test_interval_minim_per_domeniu(monkeypatch):
    """Sub `min_fetch_interval_s` nu se lanseaza browser DELOC, iar dispecerul
    traduce refuzul in fetch_failed — refresh-ul pastreaza atunci pretul anterior.
    Domeniile fara interval configurat raman neafectate."""
    lansari = []

    def fals_sesiune(url, domain, headed, valideaza):
        lansari.append(domain)
        return PAGINA

    monkeypatch.setattr(bf, "_sesiune", fals_sesiune)
    monkeypatch.setattr(bf, "_ULTIMA_VIZITA", {})

    URL_S = "https://www.sephora.ro/produs-p123.html"
    assert bf.fetch_browser_html(URL_S, "sephora.ro") is PAGINA
    assert lansari == ["sephora.ro"]

    # Al doilea apel, imediat: refuzat fara sa se atinga sesiunea.
    with pytest.raises(bf.BrowserFetchTooSoon):
        bf.fetch_browser_html(URL_S, "sephora.ro")
    assert lansari == ["sephora.ro"], "s-a lansat browser sub intervalul minim"

    # Acelasi refuz, vazut prin dispecer: fetch_failed, nu challenge.
    with pytest.raises(ProductExtractionError) as exc:
        ppe._extract_via_browser(URL_S)
    assert exc.value.reason == "fetch_failed"

    # Domeniu fara interval configurat: apeluri consecutive, toate servite.
    URL_M = "https://makeup.ro/product/181283/"
    bf.fetch_browser_html(URL_M, "makeup.ro")
    bf.fetch_browser_html(URL_M, "makeup.ro")
    assert lansari == ["sephora.ro", "makeup.ro", "makeup.ro"]
