"""MDE-1 — parserul mobile.de pe DOM-ul randat de browser (masurat 2026-09-03).

DE CE EXISTA: `_parse_mobilede_html` lua titlul din `img.alt`, cu fallback pe
`aria-labelledby`. Pe DOM-ul de azi `alt` e sirul GOL pe toate cardurile si
`aria-labelledby` nu mai exista, deci garda `if not titlu: continue` arunca fiecare card.
SONDA-MDE-B a masurat efectul: pagina buna (1,36 MB, 24 de carduri, zero markeri
anti-bot, rezultate vizibile in 3,6 s) producea ZERO anunturi — si niciun semnal.

Testele AA-4 (`tests/test_mobile_de_parser.py`) descriu DOM-ul din IULIE si raman
neatinse: fallback-urile vechi traiesc mai departe. Aici e descris DOM-ul de ACUM,
pe un fixture decupat din masuratoarea reala.
"""
import os

import pytest

from app.scrapers.auto.listings._common import parse_price
from app.scrapers.auto.listings.mobile_de_scraper import _parse_mobilede_html

_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures")
_MDE = os.path.join(_FIXTURI, "mobile_de", "search_bmw_browser.html")
_AKAMAI = os.path.join(_FIXTURI, "akamai_interstitial.html")


def _citeste(cale: str) -> str:
    with open(cale, encoding="utf-8") as f:
        return f.read()


def _pagina(*carduri: str) -> str:
    return "<html><body><main>" + "".join(carduri) + "</main></body></html>"


# ── 1: fixture-ul real ───────────────────────────────────────────────────────────
def test_fixture_real_toate_campurile():
    r = _parse_mobilede_html(_citeste(_MDE))
    # 3 `article` cu ancora de detalii + 1 control fara ancora (articol redactional)
    assert len(r) == 3

    c = r[0]
    assert c["platform"] == "mobile_de"
    assert c["external_id"] == "458588302"
    assert c["titlu"] == "BMW X4 xDrive 20iA 184PS M-Paket R-Cam Xenon Navi"
    assert c["pret"] == 27999.0
    assert c["moneda"] == "EUR"
    assert c["year"] == 2017                 # din "EZ 01/2017"
    assert c["km"] == 81833                  # din "81.833 km"
    assert c["locatie"] == "14513 Teltow"    # din seller-info, FARA numele dealerului
    assert c["source_url"].startswith("https://suchen.mobile.de")
    assert "id=458588302" in c["source_url"]
    assert c["thumbnail_url"]


def test_fixture_real_locatia_nu_pastreaza_dealerul():
    """`seller-info` contine „Autohaus Klann GmbH DE-14513 Teltow 4 Sterne ( 172 )";
    salvam DOAR codul postal + localitatea."""
    r = _parse_mobilede_html(_citeste(_MDE))
    assert [x["locatie"] for x in r] == [
        "14513 Teltow", "68309 Mannheim", "91126 Schwabach/Wolkersdorf",
    ]
    for x in r:
        assert "GmbH" not in x["locatie"] and "Sterne" not in x["locatie"]


# ── 2: fallback-ul vechi traieste ────────────────────────────────────────────────
def test_fara_data_testid_title_cade_pe_alt():
    card = ('<a href="/fahrzeuge/details.html?id=555">'
            '<img alt="BMW 320d Touring" src="https://img.classistatic.de/x.jpg">'
            '<span data-testid="price-label">11.000 €</span>'
            '<div>EZ 06/2015 • 150.000 km</div></a>')
    r = _parse_mobilede_html(_pagina(card))
    assert len(r) == 1
    assert r[0]["titlu"] == "BMW 320d Touring"
    assert r[0]["pret"] == 11000.0


def test_data_testid_title_are_prioritate_fata_de_alt():
    """Cand exista amandoua, castiga `-title`: `alt` e trunchiat pe DOM-ul real."""
    card = ('<a href="/fahrzeuge/details.html?id=556">'
            '<img alt="BMW" src="https://img.classistatic.de/x.jpg">'
            '<span data-testid="base-result-listing-9-title">BMW 530e xDrive Touring</span>'
            '<span data-testid="price-label">30.000 €</span></a>')
    r = _parse_mobilede_html(_pagina(card))
    assert r[0]["titlu"] == "BMW 530e xDrive Touring"


# ── 3: cardurile fara titlu — sarite, dar SEMNALATE ──────────────────────────────
_FARA_TITLU = ('<a href="/fahrzeuge/details.html?id=%s">'
               '<img alt="" src="https://img.classistatic.de/x.jpg">'
               '<span data-testid="price-label">9.000 €</span></a>')


def test_toate_fara_titlu_semnaleaza(capsys):
    r = _parse_mobilede_html(_pagina(_FARA_TITLU % "801", _FARA_TITLU % "802"))
    assert r == []
    assert "2 carduri fara titlu" in capsys.readouterr().out


def test_semnalul_nu_apare_cand_macar_unul_se_parseaza(capsys):
    bun = ('<a href="/fahrzeuge/details.html?id=803">'
           '<span data-testid="x-title">BMW 116i</span>'
           '<span data-testid="price-label">8.000 €</span></a>')
    r = _parse_mobilede_html(_pagina(_FARA_TITLU % "804", bun))
    assert len(r) == 1
    assert "carduri fara titlu" not in capsys.readouterr().out


# ── 4: contractul lui parse_price pe formatul german ─────────────────────────────
@pytest.mark.parametrize("text,asteptat", [
    ("27.999 €", 27999.0),
    ("27.999 €", 27999.0),      # NBSP, cum vine din DOM-ul real
    ("99.980 € ¹", 99980.0),    # nota de subsol lipita de pret
])
def test_parse_price_pe_formatul_german(text, asteptat):
    assert parse_price(text) == asteptat


# ── 5: pagina de provocare Akamai nu produce anunturi ────────────────────────────
def test_pagina_akamai_da_lista_goala():
    assert _parse_mobilede_html(_citeste(_AKAMAI)) == []


# ── garda: fixture-ul n-are date de contact ──────────────────────────────────────
def test_fixture_fara_telefoane_sau_emailuri():
    import re
    html = _citeste(_MDE)
    assert not re.search(r"[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)
    assert not re.search(r"\+49[\d /-]{6,}", html)
    assert not re.search(r"\btel:", html, re.I)
