"""CONV-1 — `app/services/conversie.py` e regula UNICA, iar cei trei apelanti o apeleaza.

DE CE EXISTA: dupa FBS-11, FBS-12, CUR-1 si CUR-2, aceeasi regula de conversie traia in
patru copii. N-au divergat inca, dar fiecare runda de moneda le atingea pe toate — iar
una uitata insemna un modul care citeste 15 000 GBP ca 15 000 RON.

Ce apara fisierul:
  * matricea regulii (ce sursa de curs, pentru ce cod, si ce se intampla pe necunoscut);
  * PARITATEA: `pret_comparabil_ron`, `_in_ron` (Auto) si `_in_eur` (Imobiliare) dau exact
    ce da modulul. Fara testele astea, „au fost unificate" ar fi o afirmatie despre trecut;
    cu ele, e o proprietate verificata la fiecare rulare.
  * IZOLAREA: modulul nu importa scrapere/utils, deci poate fi importat de oriunde.

Diferentele REALE dintre apelanti se pastreaza prin argumente de politica, nu se
armonizeaza — sunt masurate explicit mai jos (text, valori <= 0, moneda lipsa).

Fara retea: `bnr_exchange` si `currency_service` sunt pinuite in fiecare test.
"""
import pytest

from app.services import conversie


# EUR/USD au ANUME alte valori decat cursurile pinuite (5.0 / 4.5): asa devine
# OBSERVABILA ordinea „adaptor inaintea catalogului". Cu valori egale, o inversare
# a ordinii ar trece neobservata prin toate testele.
_CATALOG = {"RON": 1.0, "EUR": 9.99, "USD": 8.88, "GBP": 6.0, "ZZZ": 0.0}


@pytest.fixture
def cursuri_pinuite(monkeypatch):
    """Adaptorul si catalogul, fara retea. `get_rate_strict` raspunde din acelasi
    dictionar, ca sa se poata compara calea „cu catalog" cu cea „fara catalog"."""
    from app.services import bnr_exchange, currency_service

    monkeypatch.setattr(bnr_exchange, "get_eur_ron", lambda: 5.0)
    monkeypatch.setattr(bnr_exchange, "get_usd_ron", lambda: 4.5)
    monkeypatch.setattr(currency_service, "get_rate_strict",
                        lambda cod: _CATALOG.get((cod or "").strip().upper()) or None)
    return _CATALOG


# ── 1. matricea regulii ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("valoare,moneda,kwargs,asteptat", [
    (100, "RON", {}, 100.0),
    (100, " ron ", {}, 100.0),                                   # normalizare
    (100, "EUR", {"eur_ron": 4.0}, 400.0),                       # cursul PASAT castiga
    (100, "EUR", {}, 500.0),                                     # fara curs pasat -> adaptor
    (100, "USD", {"usd_ron": 4.0}, 400.0),
    (100, "USD", {}, 450.0),
    (100, "GBP", {"cursuri": _CATALOG}, 600.0),                  # din catalog
    (100, "GBP", {}, 600.0),                                     # fara catalog -> get_rate_strict
    (100, "GBP", {"cursuri": {}}, None),                         # catalog GOL = doar EUR/USD
    (100, "XXX", {"cursuri": _CATALOG}, None),                   # in afara catalogului
    (100, "XXX", {}, None),
    (100, "ZZZ", {"cursuri": _CATALOG}, None),                   # curs 0 in catalog
    (0, "RON", {}, None),                                        # implicit: cere_pozitiv
    (-5, "RON", {}, None),
    ("abc", "RON", {}, None),
    (None, "RON", {}, None),
    ("100", "RON", {}, 100.0),                                   # implicit: accepta_text
    (100, None, {}, 100.0),                                      # implicit: moneda RON
])
def test_in_ron_matrice(cursuri_pinuite, valoare, moneda, kwargs, asteptat):
    rezultat = conversie.in_ron(valoare, moneda, **kwargs)
    if asteptat is None:
        assert rezultat is None
    else:
        assert rezultat == pytest.approx(asteptat)


def test_adaptorul_bate_catalogul_pe_eur_si_usd(cursuri_pinuite):
    """Ordinea conteaza si e cablata: EUR/USD se iau de la adaptor (sau din cursul PASAT),
    NU din catalog, chiar cand catalogul le contine. Asa raman consecvente cu restul
    scanului — `eur_ron` e valoarea pe care o folosesc si celelalte parti — si asa continua
    sa prinda pinurile din teste, care sunt pe adaptor."""
    assert conversie.in_ron(100, "EUR", cursuri=_CATALOG) == 500.0      # 5.0, nu 9.99
    assert conversie.in_ron(100, "USD", cursuri=_CATALOG) == 450.0      # 4.5, nu 8.88
    assert conversie.in_ron(100, "EUR", cursuri=_CATALOG, eur_ron=4.0) == 400.0


def test_in_ron_nu_intoarce_niciodata_unu_la_unu(cursuri_pinuite):
    """Regula centrala a lui CUR-1: „nu stiu moneda" NU inseamna „valoreaza cat un leu".
    Un anunt de 800 XXX tratat 1:1 ar trece drept 800 RON si ar primi un grad fals."""
    assert conversie.in_ron(800, "XXX") is None
    assert conversie.in_ron(800, "XXX") != 800.0


# ── argumentele de politica ────────────────────────────────────────────────────
def test_politicile_de_intrare_sunt_reale(cursuri_pinuite):
    """Cele trei diferente dintre apelanti, masurate explicit — CONV-1 n-a avut voie sa
    le armonizeze tacit, fiindca fiecare ar fi schimbat comportament in productie."""
    # accepta_text: scorarea parseaza "100"; portile de pret cer un numar adevarat.
    assert conversie.in_ron("100", "RON") == 100.0
    assert conversie.in_ron("100", "RON", accepta_text=False) is None
    # cere_pozitiv: scorarea refuza 0; portile il compara cu pragurile.
    assert conversie.in_ron(0, "RON") is None
    assert conversie.in_ron(0, "RON", cere_pozitiv=False) == 0.0
    # moneda_implicita: un anunt fara moneda e RON pe Auto, EUR pe Imobiliare, si
    # NECONVERTIBIL pe portile de pret.
    assert conversie.in_ron(100, None) == 100.0
    assert conversie.in_ron(100, None, moneda_implicita="") is None


# ── in_eur ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("valoare,moneda,asteptat", [
    (100, "EUR", 100.0),
    (500, "RON", 100.0),                     # / 5.0
    (100, "GBP", 120.0),                     # 600 RON / 5.0
    (100, "USD", 90.0),                      # 450 RON / 5.0
    (100, "XXX", None),
    (0, "EUR", None),
    ("abc", "EUR", None),
    (100, None, 100.0),                      # implicit EUR
])
def test_in_eur_matrice(cursuri_pinuite, valoare, moneda, asteptat):
    rezultat = conversie.in_eur(valoare, moneda, eur_ron=5.0, cursuri=_CATALOG)
    if asteptat is None:
        assert rezultat is None
    else:
        assert rezultat == pytest.approx(asteptat)


def test_in_eur_pe_eur_nu_cere_curs(cursuri_pinuite):
    """EUR e identitate: un apelant care are doar preturi in EUR nu trebuie sa aiba curs."""
    assert conversie.in_eur(100, "EUR", eur_ron=None) == 100.0
    assert conversie.in_eur(100, "RON", eur_ron=None) is None
    assert conversie.in_eur(100, "RON", eur_ron=0) is None


# ── 3. moneda_convertibila ──────────────────────────────────────────────────────
def test_moneda_convertibila(cursuri_pinuite):
    for cod in ("RON", "EUR", "USD", " usd "):
        assert conversie.moneda_convertibila(cod) is True
    assert conversie.moneda_convertibila("GBP") is True
    assert conversie.moneda_convertibila("GBP", cursuri=_CATALOG) is True
    assert conversie.moneda_convertibila("GBP", cursuri={}) is False
    assert conversie.moneda_convertibila("XXX") is False
    assert conversie.moneda_convertibila("ZZZ", cursuri=_CATALOG) is False   # curs 0


def test_moneda_convertibila_inghite_exceptia(monkeypatch):
    """D3: un lant de curs care ridica nu are voie sa arunce din portile de pret."""
    from app.services import currency_service

    def explodeaza(cod):
        raise RuntimeError("BNR indisponibil")

    monkeypatch.setattr(currency_service, "get_rate_strict", explodeaza)
    assert conversie.moneda_convertibila("GBP") is False
    assert conversie.moneda_convertibila("EUR") is True      # adaptorul nu e interogat


# ── 2. PARITATE — cei trei apelanti dau exact ce da modulul ─────────────────────
_MATRICE_PARITATE = [
    (100, "RON"), (100, "EUR"), (100, "USD"), (100, "GBP"), (100, "XXX"),
    (0, "RON"), (-5, "EUR"), ("100", "RON"), (None, "EUR"), (100, None), (100, ""),
]


@pytest.mark.parametrize("valoare,moneda", _MATRICE_PARITATE)
def test_paritate_base_scraper(cursuri_pinuite, valoare, moneda):
    """Portile de pret FB: text refuzat, 0 acceptat, moneda lipsa = neconvertibila."""
    from app.services.radar import base_scraper as bs

    assert bs.pret_comparabil_ron(valoare, moneda) == conversie.in_ron(
        valoare, moneda, accepta_text=False, cere_pozitiv=False, moneda_implicita="")


@pytest.mark.parametrize("valoare,moneda", _MATRICE_PARITATE)
@pytest.mark.parametrize("cursuri", [None, {}, _CATALOG])
def test_paritate_auto(monkeypatch, cursuri_pinuite, valoare, moneda, cursuri):
    """Auto pinuieste `get_eur_ron` pe PROPRIUL modul, deci wrapper-ul trebuie sa paseze
    cursul mai departe — altfel pinul n-ar mai prinde si suita ar atinge reteaua."""
    from app.services import auto_listings_scanner as als

    monkeypatch.setattr(als, "get_eur_ron", lambda: 5.0)
    cod = conversie.normalizeaza_moneda(moneda) or "RON"
    assert als._in_ron(valoare, moneda, cursuri) == conversie.in_ron(
        valoare, cod, cursuri=cursuri or {},
        eur_ron=5.0 if cod == "EUR" else None)


@pytest.mark.parametrize("valoare,moneda", _MATRICE_PARITATE)
@pytest.mark.parametrize("cursuri", [None, {}, _CATALOG])
def test_paritate_imobiliare(cursuri_pinuite, valoare, moneda, cursuri):
    from app.services.real_estate import scorer

    assert scorer._in_eur(valoare, moneda, 5.0, cursuri) == conversie.in_eur(
        valoare, moneda, eur_ron=5.0, cursuri=cursuri or {})


@pytest.mark.parametrize("valoare,moneda", _MATRICE_PARITATE)
def test_paritate_radar_scorare(cursuri_pinuite, monkeypatch, valoare, moneda):
    """`_price_to_ron` NU delegheaza (e pura + fail-open), dar REZULTATUL trebuie sa
    coincida pe cazurile convertibile; pe necunoscut intoarce pretul BRUT, nu None."""
    from app.utils import radar_scanner as rs

    monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
    rs._unknown_currency_warned.clear()

    # `cere_pozitiv=False`: ca `pret_comparabil_ron`, scorarea NU refuza valorile <= 0 —
    # garda pe pret negativ sta in `calculate_score` (SCRAPE-AUDIT), o treapta mai jos.
    obtinut = rs._price_to_ron(valoare, moneda, 5.0, 4.5, cursuri=_CATALOG)
    prin_modul = conversie.in_ron(valoare, moneda, cursuri=_CATALOG,
                                  eur_ron=5.0, usd_ron=4.5, cere_pozitiv=False)
    if prin_modul is not None:
        assert obtinut == pytest.approx(prin_modul)
    else:
        try:
            brut = float(valoare)
        except (TypeError, ValueError):
            brut = None
        assert obtinut == brut, "fail-open: pretul ramane neconvertit, cu WARN"


# ── 4. izolarea modulului ───────────────────────────────────────────────────────
def test_modulul_nu_importa_scrapere_sau_utils():
    """`conversie` trebuie sa poata fi importat de oriunde — inclusiv din `base_scraper`,
    pe care il importa scraperele. Un import la nivel de fisier catre `radar/`, `scrapers/`
    sau `utils/` ar inchide cercul. Toate importurile de curs sunt LOCALE, in functii."""
    import inspect

    sursa = inspect.getsource(conversie)
    # Doar liniile de IMPORT de la marginea din stanga (proza din docstring numeste
    # modulele apelante, si e in regula sa o faca).
    importuri = [l for l in sursa.splitlines()
                 if l.startswith("import ") or l.startswith("from ")]
    for linie in importuri:
        for interzis in ("app.services.radar", "app.scrapers", "app.utils",
                         "app.models", "app.database"):
            assert interzis not in linie, (
                f"import de nivel de modul catre {interzis} — risc de ciclu: {linie!r}")
    # Contra-proba: importurile de curs EXISTA, doar ca sunt locale.
    assert "from app.services import bnr_exchange" in sursa
    assert "from app.services import currency_service" in sursa
