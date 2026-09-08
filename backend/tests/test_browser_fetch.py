"""BR-1 — harness-ul de browser ca a treia cale de fetch.

ZERO patchright real aici: sesiunea de browser e monkeypatch-uita peste tot, iar
testele acopera exact ce e logica proprie a harness-ului si a dispecerului —
alegerea caii de fetch si intervalul minim per domeniu. Randarea insasi e
raspunderea sondelor live (G4/G4b), nu a suitei.
"""
import os

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


# ── GUARD-1 — detectorul de blocare vede si <title>, si statusul HTTP ─────────
#
# Runda JSON-0 a trecut DOUA ziduri prin `_detecteaza_blocare`, si amandoua au
# intors `None` — adica productia le-ar fi citit ca pe continut real. Fixture-urile
# de mai jos sunt reduse din dump-urile ei (`dumps_json0/<domeniu>/home.html`).

class _PaginaFalsa:
    """Cat din `page` foloseste detectorul: doar `inner_text("body")`.

    Textul se da explicit, fiindca exact divergenta dintre el si `<title>` e
    fenomenul masurat pe sivasdescalzo.
    """

    def __init__(self, text_body=""):
        self._text = text_body

    def inner_text(self, _selector):
        return self._text


def _fixture_browser(nume: str) -> str:
    cale = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "browser", f"{nume}.html")
    with open(cale, encoding="utf-8") as f:
        return f.read()


def test_blocare_marker_doar_in_title():
    """sivasdescalzo — markerul e in <title>, iar corpul nu-l poarta.

    Masurat pe HTML-ul capturat: `'just a moment' in inner_text("body")` e False,
    `in <title>` e True. Garda de dinainte cauta DOAR in corp, deci intorcea `None`
    pe un 403 cu challenge Cloudflare.

    Corpul fixture-ului e un subset verbatim FARA markere (v. antetul lui): asa
    testul dovedeste ca ramura de titlu e cea care prinde, nu cea de corp.
    """
    html = _fixture_browser("sivasdescalzo.com_403")
    pagina = _PaginaFalsa("Verification successful. Waiting for "
                          "www.sivasdescalzo.com to respond")

    motiv = bf._detecteaza_blocare(pagina, html)

    assert motiv is not None, "un interstitiu Cloudflare nu are voie sa treaca"
    assert "marker in title" in motiv
    assert "just a moment" in motiv
    # Si fara status: titlul singur ajunge.
    assert bf._detecteaza_blocare(pagina, html, None) == motiv


def test_blocare_status_403_cu_titlu_real():
    """bstn — 403 cu pagina de asteptare de marca: titlu REAL, zero ancore.

    2.641 de octeti, `<title>BSTN Store</title>`, niciun marker nici in corp nici in
    titlu. Regula de shell cere TOATE trei conditiile (corp mic, fara ancore, titlu
    gol), deci titlul nevid o dezamorseaza — si asta e corect, nu un defect: fara
    conditia de titlu, orice pagina legitima mica fara ancore ar deveni fals pozitiv,
    iar un magazin sanatos ar iesi tacit din feed.

    Ce prinde cazul e STATUSUL. A doua jumatate a testului pinuieste tocmai ca
    regula de shell N-A FOST relaxata: pe acelasi HTML, cu 200, detectorul tace.
    """
    html = _fixture_browser("bstn.com_403")
    pagina = _PaginaFalsa("REQUEST NOT ALLOWED")

    assert bf._detecteaza_blocare(pagina, html, 403) == "status 403"
    # Statusul primeaza si e verificat PRIMUL: nu depinde de cum arata pagina.
    for cod in (401, 429, 503):
        assert bf._detecteaza_blocare(pagina, html, cod) == f"status {cod}"

    # Acelasi corp, status bun -> shell-ul NU se aprinde, fiindca titlul e nevid.
    assert bf._detecteaza_blocare(pagina, html, 200) is None
    assert bf._detecteaza_blocare(pagina, html) is None


def test_blocare_pagina_reala_ramane_none():
    """O pagina de produs normala nu devine fals pozitiv, cu sau fara status.

    A doua asertie e garda de COMPATIBILITATE: apelantii care nu cunosc `status`
    (sondele din `scripts/diagnostics`) cheama detectorul cu doua argumente, si
    trebuie sa primeasca exact comportamentul de dinainte.
    """
    corp = "<p>Descriere de produs. </p>" * 900          # > 15.000 de octeti
    html = (f"<html><head><title>Ruj mat 03 | Magazin</title></head>"
            f"<body><a href='/cos'>Cos</a>{corp}</body></html>")
    assert len(html) > bf._PRAG_SHELL_OCTETI
    pagina = _PaginaFalsa("Ruj mat 03 Adauga in cos Livrare in 24h")

    assert bf._detecteaza_blocare(pagina, html, 200) is None
    assert bf._detecteaza_blocare(pagina, html, None) is None
    assert bf._detecteaza_blocare(pagina, html) is None
    # Dar un 403 pe ACELASI continut ramane blocaj: statusul primeaza.
    assert bf._detecteaza_blocare(pagina, html, 403) == "status 403"
