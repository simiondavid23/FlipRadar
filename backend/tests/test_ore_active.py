"""FB-7a — fereastra orara consolidata in `app.utils.ore_active`.

Regula traia in CINCI locuri (canonicul din radar_scanner, cate o copie in scanerele de
imobiliare/auto/loturi, plus executorul Facebook care delega lenes SI mai purta o copie
ca rezerva). Cinci implementari care trebuie sa spuna acelasi lucru pot diverge tacit.

Fisierul are doua jumatati:
  * unitatile helperului, cu CEASUL INJECTAT — niciun test pe ceasul real. Lectia
    FB-FRANA-1: doua teste de buget au trecut ziua si au picat dupa ora 22, ascunzand
    un bug real 14 ore pe zi;
  * paritatea de delegare: pentru fiecare din cele cinci nume pastrate, dovada ca
    raspunsul chiar vine prin helper, nu dintr-o reimplementare ramasa pe loc.
"""
from datetime import datetime

import pytest

from app.utils.ore_active import in_ore_active


class _KW:
    """Keyword minimal. Modelele reale (Radar/Auto/AutoLot/Imobiliare) au campurile
    astea; helperul le citeste prin `getattr`, deci forma asta e de ajuns."""

    def __init__(self, start, end):
        self.active_hours_start = start
        self.active_hours_end = end


def _la(ora: int) -> datetime:
    """Un moment NAIV LOCAL la ora data — aceeasi conventie ca `datetime.now()` din cod."""
    return datetime(2026, 8, 21, ora, 30, 0)


# ── margini absente: mereu activ ─────────────────────────────────────────────
@pytest.mark.parametrize("start,end", [(None, None), (8, None), (None, 8)])
@pytest.mark.parametrize("ora", [0, 7, 8, 12, 23])
def test_marginile_absente_inseamna_mereu_activ(start, end, ora):
    """O fereastra neconfigurata NU inseamna o fereastra goala — inclusiv cand doar UNA
    dintre margini lipseste."""
    assert in_ore_active(_KW(start, end), acum=_la(ora)) is True


def test_keyword_fara_campurile_de_ore_e_mereu_activ():
    """Citirea prin `getattr` — rezerva din executor facea deja asa, aici e regula."""
    assert in_ore_active(object(), acum=_la(3)) is True


# ── interval normal: start INCLUSIV, end EXCLUSIV ────────────────────────────
# Granitele sunt fixate EXPLICIT: ele sunt jumatatea de semantica pe care o refactorizare
# viitoare o poate schimba fara sa observe nimeni.
@pytest.mark.parametrize("ora,asteptat,de_ce", [
    (7, False, "inainte de start"),
    (8, True, "START e INCLUSIV"),
    (9, True, "in interval"),
    (19, True, "ultima ora din interval"),
    (20, False, "END e EXCLUSIV"),
    (21, False, "dupa end"),
])
def test_interval_normal_8_20(ora, asteptat, de_ce):
    assert in_ore_active(_KW(8, 20), acum=_la(ora)) is asteptat, de_ce


def test_interval_degenerat_start_egal_end_nu_e_activ_niciodata():
    """`s == e` intra pe ramura normala (`s <= e`), deci `s <= h < e` e mereu fals.
    Comportament pastrat identic din canonic — fixat aici ca sa nu se schimbe tacit."""
    assert not any(in_ore_active(_KW(8, 8), acum=_la(h)) for h in range(24))


# ── interval peste miezul noptii ─────────────────────────────────────────────
# Exemplul din docstring-ul canonicului: start=22, end=6 -> activ 22:00-05:59.
@pytest.mark.parametrize("ora,asteptat,de_ce", [
    (21, False, "inainte de start"),
    (22, True, "START e INCLUSIV, si aici"),
    (23, True, "inainte de miezul noptii"),
    (0, True, "dupa miezul noptii"),
    (3, True, "in mijlocul ferestrei de noapte"),
    (5, True, "ultima ora activa"),
    (6, False, "END e EXCLUSIV, si aici"),
    (12, False, "in plina zi"),
])
def test_interval_overnight_22_6(ora, asteptat, de_ce):
    assert in_ore_active(_KW(22, 6), acum=_la(ora)) is asteptat, de_ce


@pytest.mark.parametrize("ora,asteptat", [(22, False), (23, True), (0, True), (1, False)])
def test_overnight_ingust_23_1(ora, asteptat):
    assert in_ore_active(_KW(23, 1), acum=_la(ora)) is asteptat


# ── ceasul implicit ──────────────────────────────────────────────────────────
def test_ceasul_implicit_functioneaza():
    """Fara `acum`, helperul citeste `datetime.now()`. Testul e TOLERANT deliberat: nu
    aserteaza pe o ora concreta, fiindca exact asta ar face suita dependenta de cand e
    rulata. Verifica doar ca drumul implicit exista si e coerent cu ora reala."""
    ora_reala = datetime.now().hour
    fereastra_care_include = _KW(ora_reala, (ora_reala + 1) % 24)

    assert in_ore_active(_KW(None, None)) is True
    assert in_ore_active(fereastra_care_include) is True


def test_ceasul_injectat_chiar_e_folosit():
    """Contra-proba pentru cusatura de ceas: acelasi keyword da raspunsuri diferite la
    ore diferite. Fara asta, un `acum` ignorat ar trece neobservat."""
    kw = _KW(8, 20)

    assert in_ore_active(kw, acum=_la(12)) is True
    assert in_ore_active(kw, acum=_la(2)) is False


# ══════════════════════════════════════════════════════════════════════════════
# Paritatea de delegare: cele cinci nume pastrate chiar trec prin helper
# ══════════════════════════════════════════════════════════════════════════════
# Cele cinci module fac `from app.utils.ore_active import in_ore_active`, deci NUMELE e
# legat la import. Patch-ul se pune pe modulul CONSUMATOR, nu pe sursa — altfel n-ar fi
# vazut. Daca vreun delegat ar fi ramas cu o reimplementare pe loc, sentinela de mai jos
# n-ar ajunge la el si testul ar pica.
def _situri():
    from app.scrapers.facebook import executor
    from app.services import auto_listings_scanner, auto_lot_scanner, real_estate_scanner
    from app.utils import radar_scanner
    return [
        (radar_scanner, "_is_within_active_hours"),
        (real_estate_scanner, "_within_hours"),
        (auto_listings_scanner, "_within_hours"),
        (auto_lot_scanner, "_within_hours"),
        (executor, "_in_ore_active"),
    ]


@pytest.mark.parametrize("i", range(5))
def test_delegatul_trece_prin_helper(monkeypatch, i):
    modul, nume = _situri()[i]
    primite = []

    def sentinela(kw, acum=None):
        primite.append(kw)
        return "SENTINELA"

    monkeypatch.setattr(modul, "in_ore_active", sentinela)
    kw = _KW(8, 20)

    rezultat = getattr(modul, nume)(kw)

    assert rezultat == "SENTINELA", \
        f"{modul.__name__}.{nume} nu trece prin helper — a mai ramas o reimplementare"
    assert primite == [kw], "keyword-ul se paseaza mai departe neatins"


@pytest.mark.parametrize("i", range(5))
def test_delegatul_da_acelasi_raspuns_ca_helperul(i):
    """Paritate pe raspuns, nu doar pe drum: pe ceasul REAL (acelasi pentru amandoi),
    delegatul si helperul trebuie sa coincida pe fiecare forma de fereastra."""
    modul, nume = _situri()[i]
    fn = getattr(modul, nume)

    for start, end in [(None, None), (8, None), (0, 23), (8, 20), (22, 6), (23, 1)]:
        kw = _KW(start, end)
        assert fn(kw) == in_ore_active(kw), f"{modul.__name__}.{nume} pe ({start}, {end})"


def test_executorul_nu_mai_trage_radar_scanner_dupa_el():
    """Comentariul vechi din executor justifica importul lenes prin faptul ca
    `radar_scanner` e „un modul greu care importa la randul lui scraperele". Helperul nou
    e stdlib-only, deci motivul a disparut — iar testul asta il tine disparut."""
    import subprocess
    import sys

    cod = ("import sys;"
           "import app.scrapers.facebook.executor;"
           "print('app.utils.radar_scanner' in sys.modules)")
    iesire = subprocess.run([sys.executable, "-c", cod], capture_output=True, text=True)

    assert iesire.returncode == 0, iesire.stderr
    assert iesire.stdout.strip() == "False", \
        "executorul a inceput iar sa traga radar_scanner la import"
