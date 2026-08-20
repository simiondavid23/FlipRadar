"""R1 (audit FB) — parserul de pret al scraperului Facebook din Radar Piata.

Bug: ramura de FALLBACK pe `formatted_amount` (folosita cand `listing_price.amount`
lipseste) facea un replace orb `.replace(".", "").replace(",", ".")`. Pe formatul EN
cu virgula de mii — frecvent pe Marketplace — dadea valori de 1000x mai mici, TACUT
si in gama care trece de filtrele de pret: "RON1,500" -> 1.5, "€1,234.56" -> 1.23.

Fix: app/utils/number_format.parse_number (aceeasi regula deja dovedita pe Imobiliare
in facebook_real_estate._parse_price / extractor._clean_number). Ramura prioritara
(listing_price.amount) e NEATINSA si are precedenta.

Modulul Auto beneficiaza automat: facebook_auto_scraper importa _parse_price de aici.
Parserul nu avea niciun test unitar pana acum (doar calea de re-auth era acoperita).
"""
import pytest

from app.services.radar.facebook_scraper import _parse_price
from app.utils.number_format import parse_number


def _obj(formatted=None, amount=None) -> dict:
    """Forma minima a cardului Marketplace citita de _parse_price."""
    lp: dict = {}
    if formatted is not None:
        lp["formatted_amount"] = formatted
    if amount is not None:
        lp["amount"] = amount
    return {"listing_price": lp}


# ── fallback pe formatted_amount ─────────────────────────────────────────────────

def test_fallback_en_virgula_de_mii():
    # TINTA fixului: inainte iesea 1.5 (de 1000x mai mic), si trecea de filtre.
    assert _parse_price(_obj("RON1,500")) == (1500.0, "RON")


def test_fallback_en_cu_zecimale():
    assert _parse_price(_obj("€1,234.56")) == (1234.56, "EUR")


def test_fallback_format_ro():
    assert _parse_price(_obj("12.500 RON")) == (12500.0, "RON")


# ── FBS-12: eticheta de moneda spune adevarul ────────────────────────────────────
# Tabelul e NORMATIV: exact formele masurate la FBS-11, cand „800 GBP" si „800 CHF"
# ieseau amandoua „RON" si erau comparate cu praguri RON.
_ETICHETE = [
    ("RON800", "RON", "marcaj explicit, lipit de cifra"),
    ("RON1,500", "RON", "aceeasi forma, cu virgula de mii"),
    ("€800", "EUR", "simbol cunoscut"),
    ("$800", "USD", "simbol cunoscut"),
    ("800 USD", "USD", "cod alfabetic"),
    ("USD800", "USD", "cod lipit de cifra — `\\b` l-ar fi ratat"),
    ("800 GBP", "GBP", "REGRESIA FBS-11: iesea RON"),
    ("800 CHF", "CHF", "REGRESIA FBS-11: iesea RON"),
    ("1.500 lei", "RON", "codul `lei` e singurul tradus, catre RON"),
    ("800 ron", "RON", "insensibil la caz"),
    ("Pret: 800 RON", "RON", "cuvintele din jur nu produc coduri false"),
    ("800", "RON", "cifre goale: nicio informatie de moneda -> implicit"),
    ("", "RON", "formatted_amount gol -> implicit"),
]


@pytest.mark.parametrize("formatted,moneda,de_ce", _ETICHETE)
def test_eticheta_de_moneda_pe_calea_de_sesiune(formatted, moneda, de_ce):
    assert _parse_price(_obj(formatted, amount="800"))[1] == moneda, de_ce


@pytest.mark.parametrize("formatted,moneda,de_ce", _ETICHETE)
def test_paritate_de_moneda_intre_cele_doua_parsere(formatted, moneda, de_ce):
    """Nucleul si calea de sesiune sunt copii una alteia (nucleul nu are voie sa depinda
    de `app.services.radar`), deci regula e scrisa de doua ori. Testul asta face
    divergenta VIZIBILA in loc s-o presupuna imposibila — la FBS-11 s-a masurat ca cele
    doua vocabulare coincid, iar proprietatea trebuie sa se pastreze."""
    from app.scrapers.facebook.parse import parse_price

    obj = _obj(formatted, amount="800")
    assert parse_price(obj)[1] == _parse_price(obj)[1] == moneda, de_ce


def test_fallback_usd():
    assert _parse_price(_obj("$800")) == (800.0, "USD")


def test_fallback_zecimal_simplu_cu_virgula():
    # "99,90" NU e grup de 3 -> virgula zecimala (format RO), nu separator de mii.
    assert _parse_price(_obj("€99,90")) == (99.9, "EUR")


# ── precedenta: amount bate formatted_amount ─────────────────────────────────────

def test_amount_are_precedenta_peste_formatted():
    # REGRESIE: ramura prioritara ramane neatinsa de fix.
    assert _parse_price(_obj("RON1,500", amount="11500.00")) == (11500.0, "RON")


def test_amount_invalid_cade_pe_formatted():
    # amount neconvertibil -> fallback-ul preia (si el, acum, corect).
    assert _parse_price(_obj("RON1,500", amount="n/a")) == (1500.0, "RON")


# ── lipsa de pret: comportament pinuit, nu schimbat ──────────────────────────────

def test_fara_pret_da_none_si_moneda_default():
    assert _parse_price({}) == (None, "RON")
    assert _parse_price(_obj("")) == (None, "RON")


def test_formatted_fara_cifre_da_none_dar_pastreaza_moneda():
    assert _parse_price(_obj("Gratis €")) == (None, "EUR")


# ── helper-ul partajat, direct ───────────────────────────────────────────────────

def test_parse_number_mii_vs_zecimale():
    assert parse_number("1,500") == 1500.0        # EN: grup de 3 = mii
    assert parse_number("99,90") == 99.9          # nu e grup de 3 = zecimal
    assert parse_number("1,234.56") == 1234.56    # ambele: ultimul e zecimalul
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("12.500") == 12500.0      # RO: punct de mii
    assert parse_number("24.99") == 24.99         # nu e grup de 3 = zecimal
    assert parse_number("1.500.000") == 1500000.0
    assert parse_number("800") == 800.0


def test_parse_number_intrari_invalide():
    assert parse_number(None) is None
    assert parse_number("") is None
    assert parse_number("La cerere") is None
    assert parse_number(",.") is None
