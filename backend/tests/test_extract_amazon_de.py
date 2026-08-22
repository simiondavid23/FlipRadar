"""AMZ-1 C2 — extractorul custom pentru amazon.de (axa L).

De ce custom si nu fluxul generic: pe cele 9 PDP-uri masurate la AMZ-0 exista ZERO
blocuri `application/ld+json`. Nu „unele n-au" — niciunul.

Fixture-urile sunt fragmente MINIMALE scrise de mana (nu dump-uri), fiecare
reproducand exact fenomenele masurate la AMZ-0 si nimic altceva:
  * primul `.a-offscreen` din `.priceToPay` e un span GOL;
  * literalul „null" ca pret taiat (2/9 pagini);
  * `basisPrice` EGAL cu pretul platit desi `savingsPercentage` anunta −7%;
  * buy box servit de „Amazon Retourenkauf" (oferta second pe o pagina normala);
  * `link[rel=canonical]` care sare pe ALT ASIN (3/9 pagini).

Tiparul e cel de la intersport/powerup (PASUL 0.7): fixture-uri in fisiere, citite
printr-un helper, cu poarta de fetch inlocuita de `fetch_mock`.
"""
import os

import pytest

from app.services import product_page_extractor as ppe
from app.services.product_page_extractor import ProductExtractionError

_FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "amazon_de")

URL_LEGO = "https://www.amazon.de/dp/B00PY3EYQO"
URL_BOSCH = "https://www.amazon.de/dp/B015WGDX6E"
URL_FLORI = "https://www.amazon.de/dp/B0FNWKCDLS"


def _fixture(nume: str) -> str:
    with open(os.path.join(_FIXTURI, nume), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def fetch_mock(monkeypatch):
    """Poarta de fetch inlocuita cu o coada de pagini; numara apelurile si URL-urile."""
    from app.services import scraper_service

    monkeypatch.setattr(ppe.time, "sleep", lambda *_a, **_kw: None)

    def _install(*pagini):
        state = {"calls": 0, "urls": []}

        def _fake(url, **_kwargs):
            state["urls"].append(url)
            index = min(state["calls"], len(pagini) - 1)
            state["calls"] += 1

            class _R:
                status_code = 200
                text = pagini[index]
                headers = {}
            return _R()

        monkeypatch.setattr(scraper_service, "_fetch_shop_url_guarded", _fake)
        return state

    return _install


# ── parserul de pret, direct ───────────────────────────────────────────────────
#
# Cele doua formate MASURATE difera prin ROLUL punctului: in germana e separator de
# mii („1.234,56 €"), in engleza e zecimal („€1,234.56"). Exact aici sta riscul —
# un parser care le confunda citeste 1.234,56 ca 1.23, adica de o mie de ori mai
# putin, si nimic din pagina nu tradeaza greseala.
#
# Testul e DIRECT pe parser, nu doar prin extractor, fiindca niciun fixture n-avea
# pret peste 1000: ramura de separator de mii era netestata, iar un sabotaj care
# inverseaza cele doua separatoare trecea neobservat.
@pytest.mark.parametrize("text,asteptat", [
    # germana: punct = mii, virgula = zecimal
    ("1.234,56 €", 1234.56),
    ("12.345,00 €", 12345.0),
    ("35,56 €", 35.56),
    # engleza: virgula = mii, punct = zecimal (€ in FATA, masurat live la AMZ-1)
    ("€1,234.56", 1234.56),
    ("€12,345.00", 12345.0),
    ("€35.56", 35.56),
    # AMBIGUE prin constructie: fara doua zecimale nu se poate decide daca
    # separatorul e de mii sau zecimal. Refuzam, nu ghicim.
    ("1.234", None),
    ("1,234", None),
    # sabloane si gunoi: None, NU exceptie — apelantul decide ce inseamna lipsa
    ("null", None),
    ("", None),
    ("  ", None),
    (None, None),
    (12.5, None),
])
def test_parserul_de_pret_pe_ambele_formate(text, asteptat):
    assert ppe._amz_parse_pret(text) == asteptat


def test_pret_de_patru_cifre_prin_extractorul_complet(fetch_mock):
    """Aceeasi ramura, dar pe calea completa: fixture cu pret DE de 4 cifre."""
    fetch_mock(_fixture("pdp_mii.html"))

    data = ppe.extract_product("https://www.amazon.de/dp/B0FP2S1MNB")

    assert data["price"] == 1234.56
    assert data["reference_price"] == 1499.0
    assert data["currency"] == "EUR"


# ── identitate: ASIN-ul din URL ────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://www.amazon.de/dp/B00PY3EYQO",
    "https://www.amazon.de/-/en/dp/B00PY3EYQO",
    "https://www.amazon.de/gp/product/B00PY3EYQO",
    "https://www.amazon.de/gp/aw/d/B00PY3EYQO",
    "https://www.amazon.de/dp/B00PY3EYQO?ref=sr_1_3&th=1",
    "https://www.amazon.de/LEGO-Classic-Box/dp/B00PY3EYQO/ref=sr_1_3",
])
def test_asin_recunoscut_din_toate_formele_de_url(fetch_mock, url):
    state = fetch_mock(_fixture("pdp_nou.html"))

    data = ppe.extract_product(url)

    assert data["price"] == 35.56
    # Indiferent de forma lipita, se cere si se stocheaza FORMA CANONICA pe ASIN.
    assert state["urls"] == ["https://www.amazon.de/dp/B00PY3EYQO"]
    assert data["canonical_url"] == "https://www.amazon.de/dp/B00PY3EYQO"


def test_url_fara_asin_e_no_product_data(fetch_mock):
    fetch_mock(_fixture("pdp_nou.html"))

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product("https://www.amazon.de/s?k=lego")

    assert exc.value.reason == "no_product_data"


def test_canonicalul_paginii_e_IGNORAT_pentru_identitate(fetch_mock):
    """Fixture-ul are `canonical` catre B07J3MHDFC (parintele de varianta), masurat
    la AMZ-0 pe 3 din 9 pagini. Daca l-am urma, doua produse distincte ar colapsa."""
    fetch_mock(_fixture("pdp_nou.html"))

    data = ppe.extract_product(URL_LEGO)

    assert "B07J3MHDFC" not in data["canonical_url"]
    assert data["canonical_url"] == "https://www.amazon.de/dp/B00PY3EYQO"


def test_asin_servit_diferit_opreste_extractia(fetch_mock, monkeypatch):
    """Pagina a servit alta varianta decat cea ceruta: v1 nu rezolva variante, deci
    esueaza curat in loc sa urmareasca tacut alt produs. WARN cu ambele valori."""
    # Patch pe SINGLETON, nu pe modulul extractorului: acolo importul e local (in
    # corpul functiei), deci `ppe.log_manager` nu exista. Obiectul e acelasi.
    from app.services.log_manager import log_manager

    warn = []
    monkeypatch.setattr(log_manager, "emit",
                        lambda m, n, msg: warn.append(str(msg)) if n == "WARN" else None)
    fetch_mock(_fixture("pdp_alt_asin.html"))

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product("https://www.amazon.de/dp/B0CYTFB73V")

    assert exc.value.reason == "no_product_data"
    assert any("B0CYTFB73V" in m and "B0DQQY6R34" in m for m in warn), \
        "WARN-ul trebuie sa poarte AMBELE ASIN-uri"


# ── pret: prima potrivire NEVIDA ───────────────────────────────────────────────
def test_pretul_sare_peste_primul_a_offscreen_GOL(fetch_mock):
    """Sub `.priceToPay` primul `.a-offscreen` e un span de spatiu (masurat pe PS5
    B08H93ZRK9). Cu `select_one`, tot lantul de selectori ar cadea in gol."""
    fetch_mock(_fixture("pdp_nou.html"))

    data = ppe.extract_product(URL_LEGO)

    assert data["price"] == 35.56
    assert data["currency"] == "EUR"
    assert data["method"] == "amazon_de_custom"
    assert data["domain"] == "amazon.de"
    assert data["is_aggregate"] is False


def test_fara_pret_citibil_e_no_product_data(fetch_mock):
    fetch_mock(_fixture("pdp_fara_pret.html"))

    with pytest.raises(ProductExtractionError) as exc:
        ppe.extract_product("https://www.amazon.de/dp/B0CLTBHXWQ")

    assert exc.value.reason == "no_product_data"


# ── referinta taiata ───────────────────────────────────────────────────────────
def test_referinta_mai_mare_decat_pretul_e_pastrata(fetch_mock):
    fetch_mock(_fixture("pdp_nou.html"))

    data = ppe.extract_product(URL_LEGO)

    assert data["reference_price"] == 50.83


def test_referinta_egala_cu_pretul_e_respinsa(fetch_mock):
    """`basisPrice` == pret desi `.savingsPercentage` anunta −7% (masurat pe
    B015WGDX6E). O referinta egala ar produce o „reducere" de 0%."""
    fetch_mock(_fixture("pdp_second.html"))

    data = ppe.extract_product(URL_BOSCH)

    assert data["price"] == 118.92
    assert data["reference_price"] is None


def test_referinta_null_e_respinsa(fetch_mock):
    """Literalul „null" e SABLON, nu valoare — 2 din 9 PDP-uri masurate."""
    fetch_mock(_fixture("pdp_null.html"))

    data = ppe.extract_product(URL_FLORI)

    assert data["price"] == 20.32
    assert data["reference_price"] is None


# ── disponibilitate, pe cele trei ramuri ───────────────────────────────────────
@pytest.mark.parametrize("fisier,url,asteptat", [
    ("pdp_nou.html", URL_LEGO, True),        # „Auf Lager"
    ("pdp_second.html", URL_BOSCH, True),    # „Nur noch 3 auf Lager"
    ("pdp_epuizat.html", "https://www.amazon.de/dp/B0CLTBHXWQ", False),
    ("pdp_null.html", URL_FLORI, None),      # text nerecunoscut -> necunoscut
])
def test_disponibilitate(fetch_mock, fisier, url, asteptat):
    fetch_mock(_fixture(fisier))

    assert ppe.extract_product(url)["in_stock"] is asteptat


# ── vanzator si conditie ───────────────────────────────────────────────────────
def test_retourenkauf_da_conditie_used(fetch_mock):
    """Buy box-ul poate fi o oferta second pe o pagina care arata ca una noua."""
    fetch_mock(_fixture("pdp_second.html"))

    data = ppe.extract_product(URL_BOSCH)

    assert data["condition"] == "used"
    assert "Retourenkauf" in data["seller"]


def test_vanzator_3p_cunoscut_da_conditie_new(fetch_mock):
    fetch_mock(_fixture("pdp_null.html"))

    data = ppe.extract_product(URL_FLORI)

    assert data["condition"] == "new"
    assert data["seller"] == "Soyee EU"


def test_vanzatorul_literal_null_NU_devine_conditie_new(fetch_mock):
    """Garda pe „null" e observabila DOAR pe campurile de text.

    Pe calea de pret ea e redundanta — parserul strict respinge „null" oricum — si
    exact de aceea sabotajul „accepta null" nu picase niciun test pana la cazul asta.
    Pe un camp de TEXT insa, „null" ar fi luat drept vanzator real si ar produce
    `condition="new"` pentru un vanzator care nu exista.
    """
    fetch_mock(_fixture("pdp_null_vanzator.html"))

    data = ppe.extract_product(URL_FLORI)

    assert data["price"] == 10.0
    assert data["seller"] is None
    assert data["condition"] is None


def test_fara_vanzator_conditia_ramane_necunoscuta(fetch_mock):
    """`None` e o lipsa ONESTA: fara vanzator nu putem sti daca oferta e noua."""
    fetch_mock(_fixture("pdp_nou.html"))

    data = ppe.extract_product(URL_LEGO)

    assert data["seller"] is None
    assert data["condition"] is None


# ── imagine ────────────────────────────────────────────────────────────────────
def test_imaginea_prefera_data_old_hires(fetch_mock):
    fetch_mock(_fixture("pdp_nou.html"))

    assert ppe.extract_product(URL_LEGO)["image_url"].endswith("hires.jpg")


# ── cablarea ───────────────────────────────────────────────────────────────────
def test_domeniul_merge_pe_extractorul_custom():
    assert ppe.CUSTOM_EXTRACTORS["amazon.de"] is ppe._extract_amazon_de
    assert ppe._custom_extractor_for(URL_LEGO) is ppe._extract_amazon_de
    assert ppe._custom_extractor_for("https://amazon.de/dp/X") is ppe._extract_amazon_de


def test_registrul_e_cablat_pe_sesiune_si_markeri():
    from app.services import scraper_service as ss
    from app.services.shop_registry import url_identity_of

    assert ss.jar_pentru(URL_LEGO) == "amazon_de"
    assert "glow" in ss.bootstrap_pentru(URL_LEGO)
    assert ss.markeri_blocaj("amazon.de") == (
        "validatecaptcha", "api-services-support@amazon.com")
    assert ss._MIN_FETCH_INTERVALE.get("amazon.de") == 10
    # NU `exact`: acela ar pastra `?ref=...` din URL-ul lipit si ar sparge dedup-ul
    # pe ASIN. Identitatea vine din `canonical_url`-ul intors de extractor.
    assert url_identity_of("amazon.de") is None


def test_linkurile_scurte_raman_nesuportate():
    """`amzn.eu` / `amzn.to` nu sunt in allow-list — v1 nu le rezolva."""
    from app.services import scraper_service as ss

    assert ss._is_allowed_shop_url("https://www.amazon.de/dp/B00PY3EYQO") is True
    assert ss._is_allowed_shop_url("https://amzn.eu/d/abc") is False
    assert ss._is_allowed_shop_url("https://amzn.to/abc") is False


def test_genericul_NU_poate_citi_pagina(fetch_mock):
    """Justificarea extractorului custom, pe fixture: zero ld+json/microdata/OG.

    Daca amazon.de capata candva date structurate, testul cade si intrebarea „mai
    avem nevoie de cod bespoke?" se pune singura — tiparul elefant/powerup.
    """
    with pytest.raises(ProductExtractionError) as exc:
        ppe.parse_product_html(_fixture("pdp_nou.html"), URL_LEGO)

    assert exc.value.reason == "no_product_data"
