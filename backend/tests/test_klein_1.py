"""KLEIN-1 — Kleinanzeigen Auto: data de pe card in `listed_at` + anul din "EZ MM/YYYY".

CE NU E AICI, si de ce: brief-ul pornea de la premisa ca scraperul mai cauta
`article.aditem` si intoarce [] in productie. Fals la HEAD — migrarea pe markup-ul nou
(`article[data-adid]`, JSON-LD per card) s-a facut deja la KA-1 (`b9f987e`), iar
scraperul curent intoarce 27/27 rezultate pe fixture-ul din 2026-09-06. Testele KA-1
(`test_auto_kleinanzeigen_markup.py`) pinuiesc mai departe acele ancore si nu se ating.

Ce lipsea cu adevarat si se repara aici, masurat pe fixture:
  * `listed_at` — 0 din 27 de carduri il aveau;
  * anul — `extract_year` pe textul cardului gresea pe 4 din 27, luand un an din
    descriere ("...bis Mai 2031") in locul primei inmatriculari.

Totul offline: fixture-ul `kleinanzeigen_auto_search.html` + HTML sintetic.
"""
import asyncio
import os
from datetime import datetime, timedelta

from app.scrapers.auto.listings import kleinanzeigen_auto as ka

_FIX = os.path.join(os.path.dirname(__file__), "fixtures",
                    "kleinanzeigen_auto_search.html")

# `now` fix pentru testele pure — o zi si o ora fara ambiguitate.
_ACUM = datetime(2026, 9, 6, 15, 0, 0)


def _html() -> str:
    with open(_FIX, encoding="utf-8") as f:
        return f.read()


class _Resp:
    def __init__(self, text, status=200):
        self.status_code = status
        self.text = text


class _Session:
    def __init__(self, text, status=200):
        self._text, self._status = text, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        return _Resp(self._text, self._status)


def _cauta(monkeypatch, html=None, status=200) -> list:
    monkeypatch.setattr(ka, "AsyncSession",
                        lambda: _Session(html if html is not None else _html(), status))
    return asyncio.run(ka.search_kleinanzeigen_auto(query="bmw", make="bmw"))


def _card(adid: str):
    """Un `article[data-adid]` din fixture, pentru testele pe functii pure."""
    from app.scrapers.auto.listings._common import safe_soup

    return safe_soup(_html()).select_one(f'article[data-adid="{adid}"]')


# ── T1 — forma rezultatelor pe fixture ───────────────────────────────────────────

def test_t1_toate_cardurile_cu_identitatea_lor(monkeypatch):
    from app.scrapers.auto.listings._common import safe_soup

    out = _cauta(monkeypatch)
    assert len(out) == 27
    assert all(r["platform"] == "kleinanzeigen_auto" for r in out)

    adids = [c["data-adid"] for c in safe_soup(_html()).select("article[data-adid]")]
    assert [r["external_id"] for r in out] == adids
    assert all(r["source_url"].startswith("https://www.kleinanzeigen.de/s-anzeige/")
               for r in out)


# ── T2 — primul card obisnuit: locatia si data nu se amesteca ───────────────────

def test_t2_card_obisnuit_locatie_si_data_separate(monkeypatch):
    inainte = datetime.now()
    out = _cauta(monkeypatch)
    dupa = datetime.now()
    r = next(x for x in out if x["external_id"] == "3505136877")

    # Locatia si data stau in acelasi container parinte si se lipesc la get_text()
    # fara spatiu ("59192 BergkamenHeute, 13:25") — nu au voie sa ajunga impreuna.
    assert "Bergkamen" in r["locatie"]
    assert "Heute" not in r["locatie"]

    assert r["listed_at"] is not None
    assert (r["listed_at"].hour, r["listed_at"].minute) == (13, 25)
    assert r["listed_at"].date() in (inainte.date(), dupa.date())   # "Heute" = azi
    assert r["listed_at"].tzinfo is None                            # conventia Auto
    assert r["refreshed_at"] is None   # cardul n-are informatie de repromovare


def test_t2b_data_cardului_cu_now_injectat():
    """Aceeasi valoare, dar cu ceasul fixat — fara dependenta de ziua rularii."""
    assert ka._data_din_card(_card("3505136877"), now=_ACUM) == datetime(2026, 9, 6, 13, 25)


# ── T3 — cardul TOP promovat ─────────────────────────────────────────────────────

def test_t3_card_top_pret_km_an_si_fara_data(monkeypatch):
    out = _cauta(monkeypatch)
    r = next(x for x in out if x["external_id"] == "3482469227")

    assert r["pret"] == 13999.0
    assert r["moneda"] == "EUR"
    assert r["km"] == 143100
    assert r["year"] == 2017          # din "EZ 03/2017"
    assert r["listed_at"] is None     # cardurile TOP n-au data pe card
    assert r["refreshed_at"] is None


def test_t3b_cardurile_top_raman_in_rezultate(monkeypatch):
    """Fara data, dar NU se sar — sunt anunturi reale, doar promovate."""
    out = _cauta(monkeypatch)
    assert {"3482469227", "3501444161"} <= {r["external_id"] for r in out}


# ── T4 — `_parse_card_date`, functie pura ────────────────────────────────────────

def test_t4_heute_gestern_si_data_plina():
    assert ka._parse_card_date("Heute, 13:25", now=_ACUM) == datetime(2026, 9, 6, 13, 25)
    assert ka._parse_card_date("Gestern, 09:05", now=_ACUM) == datetime(2026, 9, 5, 9, 5)
    # forma de pe pagina de detaliu: ziua, ora 00:00
    assert ka._parse_card_date("12.08.2026", now=_ACUM) == datetime(2026, 8, 12, 0, 0)


def test_t4b_gestern_traverseaza_luna():
    ref = datetime(2026, 9, 1, 10, 0, 0)
    assert ka._parse_card_date("Gestern, 23:59", now=ref) == datetime(2026, 8, 31, 23, 59)


def test_t4c_intrari_necitibile_dau_none_fara_exceptie():
    for brut in ("TOP", "", None, "   ", "Reserviert", "59192 Bergkamen",
                 "Heute, 99:99", "32.13.2026", "Heute"):
        rezultat = ka._parse_card_date(brut, now=_ACUM)
        if brut == "Heute":
            # ora lipsa -> 00:00, ca la ceilalti parseri de card din proiect
            assert rezultat == datetime(2026, 9, 6, 0, 0)
        else:
            assert rezultat is None, brut


def test_t4d_rezultatul_e_naiv_local():
    assert ka._parse_card_date("Heute, 13:25", now=_ACUM).tzinfo is None
    assert ka._parse_card_date("12.08.2026", now=_ACUM).tzinfo is None


# ── T5 — nu exista cale veche de parsare (fallback-ul din brief, DECLINAT) ───────

def test_t5_nu_mai_exista_markup_vechi_de_parsat():
    """Brief-ul cerea un fallback `_parse_cards_vechi` cu bucla `article.aditem` mutata
    VERBATIM. Nu exista de unde: KA-1 (`b9f987e`) a sters bucla veche odata cu migrarea,
    deci ar fi fost cod NOU scris pe un markup pe care niciun fixture nu-l mai contine
    si pe care site-ul nu-l mai serveste (`aditem` = 0 ocurente in captura din
    2026-09-06). Un fallback netestabil e exact ce interzice si brief-ul la T5.

    Garda de aici pinuieaza starea: daca cineva reintroduce o cale `aditem`, testul
    cade si decizia se rediscuta cu o masuratoare in fata.
    """
    import inspect

    assert "aditem" not in inspect.getsource(ka.search_kleinanzeigen_auto)
    assert _html().count("aditem") == 0
    assert len(__import__("bs4").BeautifulSoup(_html(), "html.parser")
               .select("article[data-adid]")) == 27


# ── T6 — acoperirea datei pe fixture ─────────────────────────────────────────────

def test_t6_25_din_27_au_data_exact_cele_doua_top_nu(monkeypatch):
    out = _cauta(monkeypatch)
    cu_data = [r["external_id"] for r in out if r["listed_at"] is not None]
    fara_data = [r["external_id"] for r in out if r["listed_at"] is None]

    assert len(cu_data) == 25
    assert fara_data == ["3482469227", "3501444161"]   # exact cardurile TOP
    assert all(r["refreshed_at"] is None for r in out)


# ── Anul: "EZ MM/YYYY" bate `extract_year` pe textul cardului ───────────────────

def test_anul_vine_din_ez_nu_din_descriere(monkeypatch):
    """Cele patru carduri pe care `extract_year(card_text)` le gresea, masurate pe fixture.

    Ex.: un Mazda cu "Garantie bis Mai 2031" in descriere primea year=2031, iar un
    Touran EZ 03/2011 primea 1996 dintr-un numar din text.
    """
    out = _cauta(monkeypatch)
    prin_id = {r["external_id"]: r for r in out}

    assert prin_id["3505136877"]["year"] == 2011    # nu 1996
    assert prin_id["3505136662"]["year"] == 2025    # nu 2031 ("bis Mai 2031")
    assert prin_id["3505136103"]["year"] == 1985    # nu 2003
    assert prin_id["3505136095"]["year"] == 2010    # nu 2026


def test_an_din_ez_e_pur():
    assert ka._an_din_ez("143.100 km EZ 03/2017") == 2017
    assert ka._an_din_ez("EZ 12/1985") == 1985
    assert ka._an_din_ez("fara eticheta") is None
    assert ka._an_din_ez("") is None
    assert ka._an_din_ez(None) is None
    assert ka._an_din_ez("EZ 03/9999") is None      # in afara intervalului plauzibil


def test_anul_cade_pe_extract_year_cand_lipseste_ez(monkeypatch):
    """Fara eticheta EZ, lantul vechi (titlu, apoi text) ramane rezerva."""
    html = ('<html><body><article data-adid="X1" data-href="/s-anzeige/bmw/X1">'
            '<h3><a href="/s-anzeige/bmw/X1">BMW 320d 2015 Facelift</a></h3>'
            '<p class="my-xsmall text-title3 font-strong text-secondary">5.000 €</p>'
            '<div class="flex items-center gap-xxsmall text-onSurfaceNonessential">'
            '<span>10115 Berlin</span></div>'
            "</article></body></html>")
    (item,) = _cauta(monkeypatch, html)
    assert item["year"] == 2015
    assert item["listed_at"] is None


# ── Selectorul de data nu depinde de ordinea containerelor ──────────────────────

def test_data_gasita_indiferent_de_ordinea_containerelor():
    """Locatia si data stau in doua `div.text-onSurfaceNonessential` fratesti; alegerea
    se face dupa ce se poate CITI ca data, nu dupa pozitie."""
    from app.scrapers.auto.listings._common import safe_soup

    inversat = safe_soup(
        '<article data-adid="X2">'
        '<div class="text-onSurfaceNonessential"><span>Gestern, 08:30</span></div>'
        '<div class="text-onSurfaceNonessential"><span>10115 Berlin</span></div>'
        "</article>").select_one("article")
    assert ka._data_din_card(inversat, now=_ACUM) == datetime(2026, 9, 5, 8, 30)

    doar_locatie = safe_soup(
        '<article data-adid="X3">'
        '<div class="text-onSurfaceNonessential"><span>10115 Berlin</span></div>'
        "</article>").select_one("article")
    assert ka._data_din_card(doar_locatie, now=_ACUM) is None


# ── Garda: fixture-ul n-are date de contact ─────────────────────────────────────

def test_fixture_fara_date_de_contact():
    import re

    html = _html()
    assert not re.search(r"\+49[\s\d/()-]{6,}", html)          # telefoane germane
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", html)  # adrese de e-mail


_ = timedelta   # folosit implicit prin _parse_card_date; import pastrat explicit
