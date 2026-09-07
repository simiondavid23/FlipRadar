"""TZ-3 — suita nu mai depinde de fusul masinii, si nu mai exista doua ceasuri „locale".

Doua probleme, cu naturi diferite, au picat impreuna pe GitHub Actions (runner in UTC):

  1. DE MEDIU — sapte teste asertau ore ABSOLUTE („06:45 UTC -> 09:45"), deci presupuneau
     tacit un offset. Codul convertea corect; doar „local" insemna UTC acolo. Reparatia e
     in `tests/conftest.py`: fusul suitei se fixeaza la NIVEL DE MODUL, cu `setdefault`
     (un `TZ=UTC pytest ...` explicit trebuie sa castige — asa se ruleaza testele de mai
     jos ca sa DISCRIMINEZE).

  2. REALA — doua locuri citeau `now` cu fusul MASINII si scriau/converteau rezultatul in
     `FUS_ANUNTURI` (Bucuresti FIXAT). Pe laptopul din Romania cele doua coincid, deci
     bug-ul era invizibil; pe un server in UTC:
       * `_platform_scan_due` citea propria stampila cu 3 ore in VIITOR, deci `due` nu mai
         devenea True niciodata si scanarea se oprea tacut;
       * `_parse_card_date` dadea lui „Heute, 23:40" ziua URMATOARE.
     A treia, gasita la inventar: `facebook_scraper._naiv_local` scria `listed_at` pe
     ceasul masinii, in timp ce OLX/Storia/Kleinanzeigen il scriu in `FUS_ANUNTURI` —
     deci Facebook era singura platforma cu alt ceas in ACELASI camp.

CUM SE CITESC TESTELE DE AICI. Ele verifica CONSISTENTA (cele doua capete ale unei
conversii stau pe acelasi ceas), nu offsetul, deci trec sub ORICE fus. Pe o masina din
Romania trec si cu bug-ul reintrodus — acolo cele doua ceasuri sunt acelasi ceas. Proba
tare se da rulandu-le sub `TZ=UTC`:

    TZ=UTC pytest tests/test_tz_3.py

Cele TREI ceasuri ale proiectului, ca sa nu se mai amestece (vezi `utils/listing_dates`):
  * ceasul NOSTRU      — `acum_local()` scrie, `la_ora_sistemului()` citeste: fusul MASINII;
  * ceasul PIETEI      — `to_naive_bucuresti()` / `din_fus()`: `FUS_ANUNTURI`, Bucuresti FIXAT;
  * ceasul FACEBOOK    — `_acum()` din nucleu: UTC aware, cu `FUS_LOCAL` pentru forma orara.
"""
import ast
import io
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.listing_dates import (
    FUS_ANUNTURI,
    acum_local,
    din_fus,
    iso_to_naive_bucuresti,
    la_ora_sistemului,
)

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_BACKEND, "app")
_RADACINA = os.path.dirname(_BACKEND)


def _sursa(*cale) -> str:
    with io.open(os.path.join(*cale), encoding="utf-8") as f:
        return f.read()


# ── T1 — suita isi fixeaza singura fusul ────────────────────────────────────────

def test_t1_conftest_fixeaza_fusul_la_nivel_de_modul():
    """`os.environ.setdefault("TZ", ...)` trebuie sa fie o instructiune de MODUL.

    Intr-un fixture ar rula prea tarziu: unele module de test calculeaza constante de fus
    chiar la import, iar pe Linux `time.tzset()` trebuie chemat inainte ca ele sa citeasca
    ceasul. De asta garda e pe POZITIA din arbore, nu pe simpla prezenta a textului.
    """
    arbore = ast.parse(_sursa(_BACKEND, "tests", "conftest.py"))

    def _setdefault_pe_tz(radacini):
        """Apelurile `...setdefault("TZ", ...)` din `radacini`, FARA a intra in def/class."""
        gasite, coada = [], list(radacini)
        while coada:
            n = coada.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue        # aici incepe codul care ruleaza mai tarziu — nu ne uitam
            e_setdefault = (isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "setdefault")
            if e_setdefault and any(isinstance(a, ast.Constant) and a.value == "TZ"
                                    for a in n.args):
                gasite.append(n)
            coada.extend(ast.iter_child_nodes(n))
        return gasite

    # Cautarea PORNESTE de la corpul modulului si se opreste la prima `def`: un
    # setdefault ajuns intr-un fixture nu mai e vazut deloc, deci pica pe numar.
    apeluri = _setdefault_pe_tz(arbore.body)
    assert len(apeluri) == 1, (
        "exact un setdefault pe TZ, la NIVEL DE MODUL (intr-un fixture ruleaza prea tarziu)")
    assert apeluri[0].args[1].value == "Europe/Bucharest"

    # `tzset` exista doar pe Unix; pe Windows blocul trebuie sa fie no-op, nu AttributeError.
    sursa = _sursa(_BACKEND, "tests", "conftest.py")
    assert 'hasattr(time, "tzset")' in sursa, "tzset trebuie gardat pentru Windows"


def test_t1b_setdefault_nu_suprascrie_un_tz_explicit():
    """Semantica ceruta: `TZ=UTC pytest ...` CASTIGA fata de valoarea suitei.

    Fara asta, testele de consistenta de mai jos n-ar putea fi rulate sub alt fus, deci
    n-ar mai putea discrimina nimic — ar trece pe Bucuresti orice s-ar strica.
    """
    assert os.environ.get("TZ"), "conftest-ul trebuie sa lase TZ setat"
    # Reproducem semantica exacta pe o cheie de unica folosinta, ca sa nu atingem TZ-ul
    # procesului (schimbarea lui la mijlocul suitei n-ar avea efect oricum, dar ar minti).
    cheie = "TZ3_PROBA_SETDEFAULT"
    os.environ.pop(cheie, None)
    try:
        os.environ[cheie] = "UTC"                       # „explicit din shell"
        os.environ.setdefault(cheie, "Europe/Bucharest")  # blocul din conftest
        assert os.environ[cheie] == "UTC"
    finally:
        os.environ.pop(cheie, None)


def test_t1d_documentul_de_handover_spune_unde_ruleaza_ce():
    """Handover-ul TZ (docstring-ul din `utils/listing_dates.py`) trebuie sa poarte si
    runda asta: unde se fixeaza fusul in CI si care sunt fusurile fixe ramase.

    Aceeasi garda ca `test_tz_2.py::test_t2c` — o conventie explicata doar in commit-ul
    care a introdus-o nu ajunge la urmatorul care deschide fisierul.
    """
    doc = _sursa(_APP, "utils", "listing_dates.py")
    assert "TZ-3" in doc
    assert "TZ=Europe/Bucharest" in doc, "trebuie scris UNDE si CU CE ruleaza CI-ul"
    assert "tests/test_tz_3.py" in doc, "testele de consistenta trebuie citabile"
    for ceas in ("acum_local()", "la_ora_sistemului()", "to_naive_bucuresti()"):
        assert ceas in doc, ceas
    # TZ-3b: de ce s-a schimbat numele trebuie sa ramana citibil dupa ce nimeni nu-si mai
    # aminteste numele vechi — altfel redenumirea sterge tocmai explicatia bug-ului.
    assert "to_naive_local" in doc, "motivul redenumirii trebuie sa poarte numele vechi"
    assert "_CEAS_PIETEI_PERMIS" in doc, "a doua garda trebuie citabila din handover"


def test_t1c_ci_ruleaza_cu_acelasi_fus():
    """Workflow-ul poarta fusul EXPLICIT, ca sa se vada in log-ul rularii, nu doar in cod."""
    wf = _sursa(_RADACINA, ".github", "workflows", "ci.yml")
    assert "TZ: Europe/Bucharest" in wf


# ── T2 — un singur mecanism pentru „fusul local al sistemului" ─────────────────

def test_t2_la_ora_sistemului_e_perechea_de_citire_a_lui_acum_local():
    """Proprietatea, adevarata in ORICE fus: acelasi moment, acelasi ceas, aceeasi ora.

    Asta e contractul care lipsea. `acum_local()` SCRIE pe ceasul masinii; pana la TZ-3,
    citirea inapoi se facea pe alocuri cu `to_naive_bucuresti`, adica pe ceasul PIETEI.
    """
    acum_aware = datetime.now(timezone.utc)
    delta = la_ora_sistemului(acum_aware) - acum_local()
    assert abs(delta.total_seconds()) < 5, delta


def test_t2b_naivul_se_intoarce_neschimbat():
    """Contractul e simetric cu `to_naive_bucuresti`: un naiv e DEJA pe ceasul cerut."""
    naiv = datetime(2026, 7, 15, 14, 23, 45)
    assert la_ora_sistemului(naiv) is naiv


def test_t2c_degradare_curata():
    for rau in (None, "", "2026-07-15T14:23:45", 0, object(), True, [], {}):
        assert la_ora_sistemului(rau) is None, rau


def test_t2d_dus_intors_pastreaza_momentul():
    """Un aware oarecare -> naiv de sistem -> re-etichetat cu fusul masinii = acelasi moment."""
    aware = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)   # iarna, ca DST-ul sa conteze
    naiv = la_ora_sistemului(aware)
    assert naiv.astimezone().astimezone(timezone.utc) == aware


# Fiecare fus FIXAT care are voie sa ramana in `app/`, cu motivul. Un fus fix nu e prin
# sine o greseala — e o greseala cand valoarea e apoi comparata cu un ceas de alta specie.
_FUSURI_FIXE_PERMISE = {
    "app/utils/listing_dates.py":
        "mecanismele insele: FUS_ANUNTURI (ceasul pietei) + la_ora_sistemului (ceasul nostru)",
    "app/scrapers/facebook/planner.py":
        "exceptia B — forma orara a traficului catre Facebook, "
        "ancorata in piata (planner.py:51-52)",
    "app/main.py":
        "orarul joburilor (cron) e ancorat in piata romaneasca, nu in masina; vezi planner.py:47",
    "app/scrapers/auto/listings/kleinanzeigen_auto.py":
        "fusul SURSEI (Europe/Berlin) — intrarea in din_fus, care aterizeaza in FUS_ANUNTURI",
    "app/scrapers/auto/listings/detail.py":
        "acelasi fus al sursei, pe pagina de detaliu Kleinanzeigen",
    "app/utils/radar_scanner.py":
        "capatul de SCRIERE al stampilei de scanare; citirea o desface cu la_ora_sistemului",
    "app/scrapers/facebook_group_scraper.py":
        "TZ-3c — `_e_mai_veche_decat_rularea`: singurul drum invers din proiect, aduce "
        "stampila NOASTRA pe ceasul pietei ca sa o compare cu `posted_at`",
}


def _fusuri_fixe_din(cale):
    """(linie, descriere) pentru fiecare fus FIXAT din fisier — fara docstring-uri.

    Se citeste arborele, nu textul: jumatate din proiect VORBESTE in comentarii despre
    `.astimezone()` si despre Europe/Bucharest tocmai ca sa explice capcana asta.
    """
    arbore = ast.parse(_sursa(cale))
    docstringuri = set()
    for n in ast.walk(arbore):
        corp = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
           and corp and isinstance(corp[0], ast.Expr) \
           and isinstance(corp[0].value, ast.Constant) and isinstance(corp[0].value.value, str):
            docstringuri.add(id(corp[0].value))

    gasite = []
    for n in ast.walk(arbore):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
           and n.func.attr == "astimezone" and not n.args and not n.keywords:
            gasite.append((n.lineno, "astimezone() fara argument = fusul masinii"))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
           and id(n) not in docstringuri and "Europe/" in n.value:
            gasite.append((n.lineno, "fus scris de mana: " + n.value))
    return gasite


def _fisiere_app():
    for radacina, _, fisiere in os.walk(_APP):
        if "__pycache__" in radacina:
            continue
        for f in sorted(fisiere):
            if f.endswith(".py"):
                cale = os.path.join(radacina, f)
                yield cale, os.path.relpath(cale, _BACKEND).replace(os.sep, "/")


def test_t2e_niciun_fus_fix_in_afara_registrului():
    """Inventarul din TZ-3, EXECUTABIL: un al doilea „fus local" nu mai poate aparea tacit.

    Asta e garda care tine promisiunea rundei. Fara ea, inventarul ar fi fost o trecere
    manuala, buna o singura zi — exact felul in care s-a strecurat amestecul reparat aici.
    """
    intrusi = {}
    for cale, relativ in _fisiere_app():
        if relativ in _FUSURI_FIXE_PERMISE:
            continue
        gasite = _fusuri_fixe_din(cale)
        if gasite:
            intrusi[relativ] = gasite
    assert not intrusi, (
        "fus fixat in afara registrului _FUSURI_FIXE_PERMISE — clasifica-l si "
        f"trece-l in registru, sau muta-l pe helperul comun: {intrusi}")


@pytest.mark.parametrize("relativ,motiv", sorted(_FUSURI_FIXE_PERMISE.items()))
def test_t2f_fiecare_intrare_din_registru_e_reala(relativ, motiv):
    """Lista nu are voie sa putrezeasca: o scutire fara fus fix scuza altceva decat crede."""
    cale = os.path.join(_BACKEND, *relativ.split("/"))
    assert _fusuri_fixe_din(cale), f"{relativ}: scutire moarta ({motiv})"


# ── T2g — ceasul PIETEI, tinut pe caile de data ────────────────────────────────

# TZ-3b. `to_naive_bucuresti` / `iso_to_naive_bucuresti` fixeaza `Europe/Bucharest`, deci
# au voie DOAR acolo unde valoarea e o ora DECLARATA de o platforma (`listed_at`,
# `refreshed_at`, `posted_at`). Chemate pe o valoare scrisa cu `acum_local()`, muta ora in
# viitor pe orice masina care nu e in Romania — asa au aparut cele patru amestecuri
# reparate la TZ-3, pe cand functia se numea `to_naive_local` si suna a ceas de sistem.
#
# Registru SEPARAT de `_FUSURI_FIXE_PERMISE`, nu acelasi: listele au fisiere diferite,
# si tocmai diferenta e ce se pazeste aici. `radar_scanner.py` e in primul (are un
# `astimezone()` gol legitim, capatul de scriere al stampilei) si trebuie sa fie IN AFARA
# celui de-al doilea — un apel de ceasul pietei de acolo e exact regresia de prins.
_CEAS_PIETEI_PERMIS = {
    "app/utils/listing_dates.py": "definitia insasi",
    "app/routers/auto.py": "filtru pe listed_at, primit din query",
    "app/scrapers/auto/listings/autovit_scraper.py": "listed_at / refreshed_at (Autovit)",
    "app/scrapers/auto/listings/detail.py": "listed_at de pe pagina de detaliu",
    "app/scrapers/auto/listings/kleinanzeigen_auto.py": "ancora zilei germane (TZ-3)",
    "app/scrapers/auto/listings/olx_auto.py": "listed_at / refreshed_at (OLX Auto)",
    "app/scrapers/facebook_group_scraper.py": "posted_at, epoch declarat de Facebook",
    "app/scrapers/real_estate/olx_real_estate.py": "listed_at (OLX Imobiliare)",
    "app/services/radar/facebook_scraper.py": "_naiv_local — listed_at (Radar Facebook)",
    "app/services/radar/lajumate_scraper.py": "listed_at (LaJumate)",
    "app/services/radar/olx_scraper.py": "listed_at / refreshed_at (OLX Radar)",
    "app/services/real_estate_scanner.py": "_seed_from_raw + posturile FB: listed_at",
    # TZ-3c — scriitori mutati pe ceasul pietei in runda asta.
    "app/services/radar/vinted_scraper.py": "listed_at din timestamp-ul pozei (TZ-3c)",
    "app/services/radar/publi24_scraper.py": "ancora „azi\"/„ieri\" a listed_at (TZ-3c)",
    "app/scrapers/auto/listings/facebook_auto_scraper.py":
        "listed_at din `creation_time`, calea cu sesiune (TZ-3c)",
    "app/services/auto_lot_scanner.py": "auction_date, dupa stergerea duplicatului (TZ-3c)",
    "app/utils/radar_scanner.py": "DOAR `_too_old` — vezi _CEAS_PIETEI_DOAR_IN_FUNCTIILE",
}

_SIMBOLURI_CEAS_PIETEI = ("to_naive_bucuresti", "iso_to_naive_bucuresti", "acum_piata")

# TZ-3c — cateva module tin AMBELE ceasuri, deci scutirea nu mai poate fi pe fisier.
# `radar_scanner.py` e cazul-scoala: `_too_old` compara o valoare de PIATA si are nevoie
# de ceasul pietei, dar `_platform_scan_due` citeste propria stampila si trebuie sa ramana
# pe ceasul sistemului. Un singur rand de scutire pe fisier ar fi permis si a doua
# folosire — adica exact regresia pe care `test_t2i` o pazeste.
_CEAS_PIETEI_DOAR_IN_FUNCTIILE = {
    "app/utils/radar_scanner.py": {"_too_old"},
}


def _ceas_pietei_din(sursa: str, doar_in=None):
    """(linie, simbol) pentru fiecare FOLOSIRE a ceasului pietei — import sau apel.

    Pe arbore, nu pe text: `db_migrate.py` si `olx_state.py` pomenesc simbolurile in
    docstring-uri ca sa explice ce conventie urmeaza datele, si n-au ce cauta in registru.
    Proza nu produce `Name`/`ImportFrom`, deci se exclude singura — spre deosebire de
    detectorul de fusuri fixe de mai sus, unde a trebuit filtrata explicit.
    Ia si `import`-ul, nu doar apelul: un modul care aduce simbolul si abia apoi il pune
    la treaba ar trece altfel neobservat.
    """
    arbore = ast.parse(sursa)
    if doar_in:
        # Functiile permise se taie din arbore: ce ramane sunt folosirile NEPERMISE.
        for n in list(ast.walk(arbore)):
            for camp, valoare in list(ast.iter_fields(n)):
                if isinstance(valoare, list):
                    setattr(n, camp, [
                        c for c in valoare
                        if not (isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))
                                and c.name in doar_in)])
    gasite = []
    for n in ast.walk(arbore):
        if isinstance(n, ast.ImportFrom):
            # Cand fisierul are functii permise, IMPORTUL lor de modul e implicat: nu
            # exista alt fel de a-l aduce. Ce se pazeste sunt FOLOSIRILE, nu declaratia.
            if doar_in:
                continue
            for a in n.names:
                if a.name in _SIMBOLURI_CEAS_PIETEI:
                    gasite.append((n.lineno, a.name))
        elif isinstance(n, ast.Name) and n.id in _SIMBOLURI_CEAS_PIETEI:
            gasite.append((n.lineno, n.id))
        elif isinstance(n, ast.Attribute) and n.attr in _SIMBOLURI_CEAS_PIETEI:
            gasite.append((n.lineno, n.attr))
    return gasite


def test_t2g_ceasul_pietei_doar_pe_caile_de_data():
    """Simbolurile `Europe/Bucharest` nu au voie in afara registrului de mai sus."""
    intrusi = {}
    for cale, relativ in _fisiere_app():
        doar_in = _CEAS_PIETEI_DOAR_IN_FUNCTIILE.get(relativ)
        if relativ in _CEAS_PIETEI_PERMIS and not doar_in:
            continue
        gasite = _ceas_pietei_din(_sursa(cale), doar_in=doar_in)
        if gasite:
            intrusi[relativ] = gasite
    assert not intrusi, (
        "ceasul PIETEI folosit in afara cailor de data — daca valoarea e scrisa cu "
        "`acum_local()`, citeste-o cu `la_ora_sistemului`; daca e o ora declarata de "
        f"platforma, treci fisierul in _CEAS_PIETEI_PERMIS cu motiv: {intrusi}")


@pytest.mark.parametrize("relativ,motiv", sorted(_CEAS_PIETEI_PERMIS.items()))
def test_t2h_fiecare_cale_de_data_chiar_foloseste_ceasul_pietei(relativ, motiv):
    """Simetricul lui `test_t2f`: o intrare care nu mai foloseste simbolul scuza altceva."""
    cale = os.path.join(_BACKEND, *relativ.split("/"))
    assert _ceas_pietei_din(_sursa(cale)), f"{relativ}: scutire moarta ({motiv})"


def test_t2i_garda_prinde_un_apel_din_radar_scanner():
    """Sabotajul, AUTOMAT: `_platform_scan_due` nu are voie sa cheme ceasul pietei.

    Fara asta, `test_t2g` ar putea trece fiindca detectorul nu vede nimic nicaieri — o
    garda verde din vid. Sursa sintetica trece prin ACELASI detector si prin ACEEASI lista
    de functii permise ca fisierul real, deci proba nu depinde de repo.

    TZ-3c a facut testul mai ascutit, nu mai slab. Pana acum verifica doar ca
    `radar_scanner.py` lipseste din registru — o proprietate care a incetat sa fie
    adevarata cand `_too_old` a inceput sa masoare, pe drept, pe ceasul pietei. Acum
    verifica exact granita care conteaza: in ACELASI fisier, `_too_old` are voie si
    `_platform_scan_due` nu, fiindca prima compara o valoare de piata si a doua isi
    citeste propria stampila.
    """
    doar_in = _CEAS_PIETEI_DOAR_IN_FUNCTIILE["app/utils/radar_scanner.py"]
    assert doar_in == {"_too_old"}

    permis = """
from app.utils.listing_dates import acum_piata

def _too_old(listed_at, max_age_days, now=None):
    return (now or acum_piata()) - listed_at > max_age_days
"""
    assert not _ceas_pietei_din(permis, doar_in=doar_in),         "`_too_old` compara o valoare de PIATA — are voie"

    sabotaj = """
from app.utils.listing_dates import acum_piata, to_naive_bucuresti

def _too_old(listed_at, max_age_days, now=None):
    return (now or acum_piata()) - listed_at > max_age_days

def _platform_scan_due(kw, now):
    return now >= to_naive_bucuresti(kw.last_scan_at)
"""
    gasite = _ceas_pietei_din(sabotaj, doar_in=doar_in)
    assert [simbol for _, simbol in gasite] == ["to_naive_bucuresti"], gasite

    # Si chiar asa e azi: singura folosire reala din fisier e in `_too_old`.
    assert not _ceas_pietei_din(_sursa(_APP, "utils", "radar_scanner.py"),
                                doar_in=doar_in)


# ── T3 — stampila de scanare: scrisa si citita pe acelasi ceas ─────────────────

class _Kw:
    """Keyword minimal — `_platform_scan_due` citeste doar cele trei campuri."""

    def __init__(self, poll=5):
        self.platform_last_scan = None
        self.last_scan_at = None
        self.poll_interval_minutes = poll


def test_t3_stampila_proprie_devine_scadenta_la_interval():
    """Dus-intors prin JSON: `_mark_platform_scanned` scrie, `_platform_scan_due` citeste.

    Sub `TZ=UTC` si cu citirea pe ceasul PIETEI, stampila proprie (scrisa `+00:00`) se
    citea ca ora Bucurestiului, adica 3 ore in viitor — `due` ramanea False pentru
    totdeauna si platforma nu se mai scana niciodata, fara niciun mesaj in jurnal.
    """
    from app.utils.radar_scanner import _mark_platform_scanned, _platform_scan_due

    kw = _Kw(poll=5)
    start = acum_local()
    _mark_platform_scanned(kw, "vinted", now=start)

    assert _platform_scan_due(kw, "vinted", now=start) is False
    assert _platform_scan_due(kw, "vinted",
                              now=start + timedelta(minutes=4, seconds=59)) is False
    assert _platform_scan_due(kw, "vinted", now=start + timedelta(minutes=5)) is True


def test_t3b_stampila_nu_ajunge_niciodata_in_viitor():
    """Semnatura DIRECTA a bug-ului, fara sa treaca prin prag: `last` <= `now`."""
    import json

    from app.utils.radar_scanner import _mark_platform_scanned

    kw = _Kw()
    start = acum_local()
    _mark_platform_scanned(kw, "olx", now=start)
    ts = json.loads(kw.platform_last_scan)["olx"]

    citit = la_ora_sistemului(datetime.fromisoformat(ts))
    assert citit == start, (citit, start)


def test_t3c_stampilele_vechi_cu_offset_utc_raman_corecte():
    """Compatibilitate: inainte de TZ-2 stampilele se scriau `+00:00`, fara backfill.

    Un `+00:00` INSEAMNA UTC, deci trebuie adus pe ceasul masinii — nu reinterpretat ca
    ora Bucurestiului. Testul e scris cu momentul CURENT, nu cu o data fixa, tocmai ca
    diferenta dintre cele doua interpretari sa fie masurabila.
    """
    import json

    from app.utils.radar_scanner import _platform_scan_due

    acum_utc = datetime.now(timezone.utc)
    kw = _Kw(poll=5)
    kw.platform_last_scan = json.dumps({"okazii": acum_utc.isoformat()})   # forma veche

    assert _platform_scan_due(kw, "okazii", now=acum_local()) is False
    assert _platform_scan_due(
        kw, "okazii", now=acum_local() + timedelta(minutes=5, seconds=1)) is True


def test_t3d_imobiliare_citeste_stampila_pe_acelasi_ceas():
    """`_polling_due` (IM-4) avea aceeasi semnatura ca `_platform_scan_due`.

    `last_scan_at` e scris cu `acum_local()`; un rand vechi il poate purta AWARE. Citit pe
    ceasul PIETEI, pe un server in UTC ajungea in viitor si keyword-ul nu mai era scadent.
    """
    from app.services.real_estate_scanner import _polling_due

    class KwRE:
        polling_interval_minutes = 30

    kw = KwRE()
    kw.last_scan_at = datetime.now(timezone.utc)                # forma veche, AWARE
    assert _polling_due(kw, acum_local()) is False
    assert _polling_due(kw, acum_local() + timedelta(minutes=30, seconds=1)) is True

    kw.last_scan_at = acum_local()                              # forma curenta, naiva
    assert _polling_due(kw, acum_local()) is False
    assert _polling_due(kw, acum_local() + timedelta(minutes=30, seconds=1)) is True


# ── T4 — Kleinanzeigen: ancora si rezultatul, pe acelasi ceas ──────────────────

def _in_fus_anunturi(aware: datetime) -> datetime:
    return aware.astimezone(FUS_ANUNTURI).replace(tzinfo=None)


def test_t4_heute_la_miezul_noptii_ramane_ziua_berlinului():
    """00:30 la Bucuresti = 23:30 ZIUA PRECEDENTA la Berlin.

    `now` intra in ora ANUNTURILOR (acolo aterizeaza si iesirea, prin `din_fus`). Cand
    era citit cu fusul masinii, pe un runner UTC acelasi text primea ziua urmatoare.
    """
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    acum_ro = datetime(2026, 9, 7, 0, 30, 0)
    rezultat = ka._parse_card_date("Heute, 23:40", now=acum_ro)
    assert rezultat == _in_fus_anunturi(
        datetime(2026, 9, 6, 23, 40, tzinfo=ZoneInfo("Europe/Berlin")))


def test_t4b_acelasi_moment_scris_in_doua_forme_da_acelasi_raspuns():
    """`now` aware si `now` naiv-in-ora-anunturilor descriu ACELASI moment -> acelasi raspuns.

    Proprietate pura, fara ore hardcodate: trece in orice fus si cade daca vreunul dintre
    cele doua capete se muta pe alt ceas.
    """
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    aware = datetime(2026, 9, 6, 21, 30, tzinfo=timezone.utc)   # = 00:30 RO, 23:30 Berlin
    naiv_ro = _in_fus_anunturi(aware)

    assert (ka._parse_card_date("Heute, 23:40", now=aware)
            == ka._parse_card_date("Heute, 23:40", now=naiv_ro))


def test_t4c_gestern_urmeaza_aceeasi_regula():
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    acum_ro = datetime(2026, 9, 7, 0, 30, 0)      # 06.09 23:30 la Berlin
    assert ka._parse_card_date("Gestern, 09:05", now=acum_ro) == din_fus(
        datetime(2026, 9, 5, 9, 5), "Europe/Berlin")


def test_t4d_ancora_implicita_e_ceasul_pietei():
    """Fara `now`, functia nu are voie sa cada inapoi pe ceasul masinii."""
    from app.scrapers.auto.listings import kleinanzeigen_auto as ka

    berlin = datetime.now(ZoneInfo("Europe/Berlin"))
    rezultat = ka._parse_card_date(berlin.strftime("Heute, %H:%M"))
    asteptat = din_fus(berlin.replace(tzinfo=None, second=0, microsecond=0),
                       "Europe/Berlin")
    assert rezultat == asteptat


# ── T5 — `listed_at`: o singura ora pentru toate platformele ───────────────────

def test_t5_facebook_si_olx_dau_acelasi_naiv_pentru_acelasi_moment():
    """Doua anunturi postate in ACEEASI clipa trebuie sa arate aceeasi ora in feed.

    Pana la TZ-3, Facebook trecea prin `.astimezone()` gol (ceasul masinii) iar OLX prin
    `iso_to_naive_bucuresti` (ceasul pietei): pe un server in UTC, acelasi moment aparea cu
    trei ore diferenta, in functie de platforma.
    """
    from app.services.radar.facebook_scraper import _naiv_local

    moment = datetime(2026, 8, 1, 6, 45, 38, tzinfo=timezone.utc)
    assert _naiv_local(moment) == iso_to_naive_bucuresti(moment.isoformat())


def test_t5b_facebook_listed_at_e_in_ora_anunturilor():
    from app.services.radar.facebook_scraper import _naiv_local

    moment = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)      # iarna: RO = UTC+2
    assert _naiv_local(moment) == datetime(2026, 1, 15, 10, 0)


def test_t5c_lipsa_ramane_lipsa():
    from app.services.radar.facebook_scraper import _naiv_local

    assert _naiv_local(None) is None
