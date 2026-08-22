"""VAL D runda 4a — extractoare de listare pe STARE (nu pe selectori CSS).

Familia „listare-din-stare" (masurata la extractia R4 + sonda LST-4): magazine
la care datele de produs ale unei LISTARI nu stau in DOM, ci intr-un payload
structurat — ld+json, `__NEXT_DATA__`, RSC, sau un array JS. Selectorii
`card`/`link`/`title`/`price_text` n-au ce descrie acolo.

Primul domeniu intrat: toolnation.nl (`toolnation_ldjson`). Fixture-urile sunt
DECUPATE din dump-uri reale — p1 din `scripts/diagnostics/dumps_g2f/` (sonda
G2F-1/G2F-2) si p2 din `dumps_lst4/` (sonda LST-4) — si pastreaza TOATE cele 7
blocuri ld+json ale paginii, nu doar pe cel cu produsele: alegerea blocului
corect e ea insasi invarianta pe care testele o pinuiesc.
"""
import os

import pytest

from app.services.listing_scanner import extrage_carduri
from app.services.listing_state_extractors import (
    LISTING_STATE_EXTRACTORS, ldjson_product_list,
)
from app.services.shop_registry import listing_descriptor

FIXTURI = os.path.join(os.path.dirname(__file__), "fixtures", "listing")


def _fixture(nume: str) -> str:
    with open(os.path.join(FIXTURI, f"{nume}_cards.html"), encoding="utf-8") as f:
        return f.read()


# ── registrul de extractoare ────────────────────────────────────────────────
def test_registrul_expune_extractorul_toolnation():
    """Registrul e un dict {nume -> functie}, iar `state_extractor` din descriptor
    e o CHEIE in el. Un nume necunoscut trebuie sa cada tare, nu sa iasa gol."""
    assert "toolnation_ldjson" in LISTING_STATE_EXTRACTORS
    assert callable(LISTING_STATE_EXTRACTORS["toolnation_ldjson"])


def test_nume_necunoscut_de_extractor_cade_tare():
    """Un `state_extractor` gresit scris nu trebuie sa dea o listare GOALA — aia
    ar arata ca „magazinul n-are reduceri azi" si ar inchide tacit toate dealurile.
    """
    descriptor = {"state_extractor": "nu_exista", "currency": "EUR"}
    with pytest.raises(KeyError):
        extrage_carduri(_fixture("toolnation.nl"), descriptor, "toolnation.nl")


# ── helperul de selectie a blocului ─────────────────────────────────────────
def test_ldjson_product_list_alege_blocul_lista_nu_primul():
    """Pagina are 7 blocuri ld+json; doar UNUL e o lista de `Product`. Primul bloc
    e `WebSite`, iar intre ele mai sunt `HardwareStore`, doua `BreadcrumbList` si
    `Organization`. Helperul trebuie sa-l gaseasca pe cel corect — nu primul bloc,
    nu concatenarea tuturor."""
    fixture = _fixture("toolnation.nl")
    assert fixture.count("application/ld+json") == 7

    produse = ldjson_product_list(fixture)

    assert produse is not None
    assert len(produse) == 24
    assert {p["@type"] for p in produse} == {"Product"}


def test_ldjson_product_list_intoarce_none_cand_nu_exista_lista():
    """Fara bloc-lista, helperul intoarce None si extractorul iese cu lista goala —
    e cazul unei pagini de final de paginare, nu o eroare."""
    assert ldjson_product_list("<html><head></head><body></body></html>") is None
    assert ldjson_product_list(
        '<script type="application/ld+json">{"@type":"WebSite"}</script>') is None


# ── toolnation, pe fixture-ul REAL p1 ───────────────────────────────────────
def test_toolnation_p1_24_carduri_normalizate():
    """Contractul de card e IDENTIC cu cel al caii CSS — aceleasi 6 chei — fiindca
    restul scannerului (memoria R2, `_evalueaza`, `Deal`) nu stie si nu trebuie sa
    stie din ce sursa a venit cardul."""
    carduri = extrage_carduri(_fixture("toolnation.nl"),
                              listing_descriptor("toolnation.nl"), "toolnation.nl")

    assert len(carduri) == 24
    assert all(set(c) == {"url", "external_id", "handle", "title", "price",
                          "compare_at"} for c in carduri)

    primul = carduri[0]
    assert primul["title"] == "E-00016 Schroefbitset 31-delig 25mm"
    assert primul["price"] == 20.93
    assert isinstance(primul["price"], float)
    assert primul["url"] == ("https://www.toolnation.nl/"
                             "makita-accessoires-e-00016-schroefbitset-31-delig-25mm.html")
    assert primul["external_id"].startswith("lst:")
    assert primul["handle"].startswith("/makita-accessoires-")


def test_toolnation_nu_are_referinta_taiata_deci_doar_R2():
    """Masurat pe AMBELE pagini: zero chei de tip `highPrice`/`listPrice`/`was` in
    ld+json. `compare_at` e None pe 24/24, deci R1 nu poate porni niciodata pe
    domeniul asta si dealurile vin exclusiv din minimul istoric (R2) — acelasi
    regim ca buzzsneakers. Asertia e EXPLICITA ca sa nu para o scapare."""
    for pagina in ("toolnation.nl", "toolnation.nl_p2"):
        carduri = extrage_carduri(_fixture(pagina),
                                  listing_descriptor("toolnation.nl"), "toolnation.nl")
        assert all(c["compare_at"] is None for c in carduri), pagina


def test_toolnation_moneda_vine_din_descriptor_nu_din_stare():
    """`priceCurrency: EUR` exista pe 24/24 in stare, dar moneda dealului o pune
    scannerul din `descriptor["currency"]` — la fel ca pe calea CSS. Testul leaga
    cele doua, ca o divergenta sa se vada."""
    descriptor = listing_descriptor("toolnation.nl")
    assert descriptor["currency"] == "EUR"

    produse = ldjson_product_list(_fixture("toolnation.nl"))
    monede = {o["priceCurrency"] for p in produse for o in p["offers"]}
    assert monede == {"EUR"}


def test_toolnation_p2_disjunct_de_p1():
    """LST-4: `?p=2` da tot 24 de produse, cu aceleasi chei, si ZERO suprapunere cu
    p1 — starea chiar traieste pe paginare, nu re-randeaza prima pagina."""
    p1 = extrage_carduri(_fixture("toolnation.nl"),
                         listing_descriptor("toolnation.nl"), "toolnation.nl")
    p2 = extrage_carduri(_fixture("toolnation.nl_p2"),
                         listing_descriptor("toolnation.nl"), "toolnation.nl")

    assert len(p2) == 24
    assert not ({c["url"] for c in p1} & {c["url"] for c in p2})
    assert not ({c["external_id"] for c in p1} & {c["external_id"] for c in p2})


def test_toolnation_descrierea_partajata_nu_ajunge_titlu():
    """Capcana masurata: `description` e IDENTIC pe toate cele 24 de produse — e
    text de categorie („Sale % bij Toolnation..."), nu descriere de produs. Titlul
    vine din `name`, care e distinct pe 24/24."""
    produse = ldjson_product_list(_fixture("toolnation.nl"))
    assert len({p["description"] for p in produse}) == 1
    assert len({p["name"] for p in produse}) == 24

    carduri = extrage_carduri(_fixture("toolnation.nl"),
                              listing_descriptor("toolnation.nl"), "toolnation.nl")
    assert len({c["title"] for c in carduri}) == 24
    assert not any("Ontdek alle producten" in c["title"] for c in carduri)


def test_toolnation_descriptorul_nu_declara_stoc():
    """`availability` e `InStock` pe 24/24 pe AMBELE pagini masurate — nu se poate
    deosebi de o constanta de sablon (capcana dovedita pe vivre, unde PDP-urile
    emiteau `OutOfStock` pe produse pe care listarea le dadea in stoc). Cat timp e
    nedecis, stocul NU se citeste: 24/24 e la fel de compatibil cu „tot catalogul e
    in stoc" ca si cu „campul e decorativ"."""
    descriptor = listing_descriptor("toolnation.nl")
    assert "stock_attr" not in descriptor
    assert "stock_field" not in descriptor

    produse = ldjson_product_list(_fixture("toolnation.nl"))
    disponibilitati = {o["availability"] for p in produse for o in p["offers"]}
    assert disponibilitati == {"https://schema.org/InStock"}
