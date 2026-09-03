"""KA-1 — `_resolve_make` e case-insensitive.

Complementar lui `tests/test_mobile_de_make_resolve.py` (AA-6), care acopera aliasele si
endpoint-ul: aici se testeaza DOAR regresia din KA-1. Treapta finala a lookup-ului era
`.get(make.title())`, care rezolva "volkswagen" (cheia e "Volkswagen") dar NU si "bmw":
`.title()` da "Bmw", iar cheia din dictionar e "BMW". Masurat pe 2026-09-03,
`_resolve_make("bmw")` intorcea "", deci `makeModelVariant1.makeId` nu se seta niciodata
si cautarea mergea pe TOATE marcile — tacut, fiindca scraperul doar loga un INFO.

"BMW" e azi singura cheie non-title-case din `MOBILE_DE_MAKE_IDS`, dar testul e scris
pe proprietate (orice cheie, orice grafie), nu pe cazul particular.
"""
import pytest

from app.scrapers.auto.listings.mobile_de_scraper import (
    MOBILE_DE_MAKE_IDS, _resolve_make,
)


@pytest.mark.parametrize("grafie", ["bmw", "BMW", "Bmw", "bMw", "  BmW  "])
def test_bmw_se_rezolva_indiferent_de_grafie(grafie):
    assert _resolve_make(grafie) == MOBILE_DE_MAKE_IDS["BMW"]
    assert _resolve_make(grafie) != ""


def test_orice_cheie_se_rezolva_in_orice_grafie():
    """Proprietatea, nu cazul: fiecare marca mapata trebuie sa se rezolve scrisa cu
    minuscule si cu majuscule, altfel bug-ul revine la urmatoarea cheie adaugata."""
    for cheie, id_ in MOBILE_DE_MAKE_IDS.items():
        assert _resolve_make(cheie.lower()) == id_, cheie
        assert _resolve_make(cheie.upper()) == id_, cheie


def test_necunoscutul_ramane_gol():
    assert _resolve_make("marca-inexistenta") == ""
    assert _resolve_make("") == ""
    assert _resolve_make(None) == ""


def test_id_numeric_nu_trece_prin_resolve():
    """Contractul e ca `search_mobile_de` sare peste `_resolve_make` cand make_id e deja
    numeric (`if make_id and not make_id.isdigit()`). Functia in sine NU cunoaste
    id-uri — un "12" nu e o marca mapata, deci "". Comportament neschimbat de KA-1."""
    assert _resolve_make("12") == ""
