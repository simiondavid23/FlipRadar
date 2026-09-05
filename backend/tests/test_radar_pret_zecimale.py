"""LJ-2 — cele trei `_parse_price` din Radar Piata citesc la fel zecimala.

DE CE EXISTA: SONDA-LJ4 (2026-09-05) a masurat aceleasi zece intrari pe cei trei
parseri si a gasit DOUA bug-uri distincte, ambele tacute (pretul nu crapa, doar iese
de 100 de ori prea mare, iar `_post_filter` arunca apoi anuntul):

  * okazii  — stergea punctul INAINTE de a trata virgula, deci "800.00" -> 80000
              (1 din 8 formate gresit; formatul RO iesea corect);
  * publi24 — pastra DOAR cifrele, deci ORICE zecimala se inmultea cu 100:
              "800.00" -> 80000, "1.300,50" -> 130050, "149,99" -> 14999,
              "2.500,00 Lei" -> 250000 (4 din 8).

lajumate era deja corect (LJ-1) si serveste aici drept referinta: regula lui e cea
copiata in celelalte doua — separatorul zecimal e `.` sau `,` urmat de EXACT 1-2 cifre
la finalul numarului, orice alt separator e de mii.
"""
import pytest

from app.services.radar.lajumate_scraper import _parse_price as lj_price
from app.services.radar.okazii_scraper import _parse_price as ok_price
from app.services.radar.publi24_scraper import _parse_price as p24_price


# lajumate ia moneda ca AL DOILEA argument (API-ul o trimite separat), okazii si
# publi24 o citesc din text. Valoarea se compara la fel pe toti trei.
_PARSERI = [
    pytest.param(ok_price, id="okazii"),
    pytest.param(p24_price, id="publi24"),
    pytest.param(lambda raw: lj_price(raw, None), id="lajumate"),
]

# Exact intrarile din sonda, cu valoarea evidenta pentru un om.
_CAZURI = [
    ("800.00", 800.0),          # zecimala cu punct — formatul API-ului LaJumate
    ("1.300", 1300.0),          # punct = separator de MII (trei cifre dupa el)
    ("1.300,50", 1300.5),       # mii cu punct + zecimale cu virgula (RO)
    ("1 300 lei", 1300.0),      # spatiu ca separator de mii + sufix de moneda
    ("1300", 1300.0),
    ("2.500,00 Lei", 2500.0),
    ("149,99", 149.99),         # zecimala cu virgula, fara mii
    ("12.345.678", 12345678.0),  # trei grupuri de mii, nicio zecimala
    (None, None),
    ("", None),
]


@pytest.mark.parametrize("parser", _PARSERI)
@pytest.mark.parametrize("brut,asteptat", _CAZURI)
def test_zecimala_e_separatorul_de_la_final(parser, brut, asteptat):
    assert parser(brut)[0] == asteptat


@pytest.mark.parametrize("parser", [_PARSERI[0], _PARSERI[1]])
@pytest.mark.parametrize("brut,moneda", [("350 EUR", "EUR"), ("1.200 Lei", "RON"),
                                         ("99,90 €", "EUR")])
def test_moneda_din_text(parser, brut, moneda):
    """Okazii si Publi24 deduc moneda din textul pretului — comportament nemodificat
    de LJ-2, tinut aici ca sa nu cada odata cu rescrierea numarului."""
    assert parser(brut)[1] == moneda


@pytest.mark.parametrize("valuta,moneda", [("euro", "EUR"), ("eur", "EUR"),
                                           ("€", "EUR"), ("lei", "RON"),
                                           (None, "RON")])
def test_moneda_lajumate_vine_din_argument(valuta, moneda):
    """La LaJumate moneda NU e in textul pretului: API-ul o trimite in campul ei
    (`currency`), iar raspunsul e mereu in lei. De aceea parserul lui are doua
    argumente, spre deosebire de surori."""
    assert lj_price("350", valuta)[1] == moneda
