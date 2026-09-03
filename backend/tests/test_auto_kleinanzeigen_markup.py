"""KA-1 — kleinanzeigen_auto pe markup-ul nou (atribute + JSON-LD, nu clase).

DE CE EXISTA: intre 13 aug si 2 sep 2026 site-ul a inlocuit clasele semantice cu clase
Tailwind generate. Scraperul selecta pe `article.aditem` si pe `.aditem-main--*`, deci a
inceput sa intoarca 0 — TACUT: pagina raspunde 200, ~1 MB, fara niciun marker de blocaj,
asa ca nici auditul nu-l putea deosebi de „n-are rezultate". Testele de aici cableaza
ancorele care NU sunt clase: `data-adid`, `data-href` si JSON-LD-ul din card.

Fixture-ul e decupat din masuratoarea reala (SONDA-AUTO, 2026-09-03): 3 carduri verbatim
cu JSON-LD-ul lor + un `article` FARA `data-adid` drept control negativ.
Fara retea: `AsyncSession` e inlocuit cu un dublu care intoarce fixture-ul.
"""
import asyncio
import json
import os
import re

import pytest
from bs4 import BeautifulSoup

from app.scrapers.auto.listings import kleinanzeigen_auto as ka

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kleinanzeigen",
                        "search_bmw.html")


def _html() -> str:
    with open(_FIXTURE, encoding="utf-8") as f:
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


def _cauta(monkeypatch, html, status=200):
    monkeypatch.setattr(ka, "AsyncSession", lambda: _Session(html, status))
    return asyncio.run(ka.search_kleinanzeigen_auto(query="bmw", make="bmw"))


def _primul_card_ld():
    """(data-adid, JSON-LD) al primului card din fixture — sursa de adevar a testelor."""
    card = BeautifulSoup(_html(), "html.parser").select("article[data-adid]")[0]
    ld = json.loads(card.find("script", attrs={"type": "application/ld+json"}).string)
    return card, ld


# ── 1: cardurile se gasesc, controlul e ignorat ──────────────────────────────────
def test_parseaza_exact_cardurile_cu_data_adid(monkeypatch):
    out = _cauta(monkeypatch, _html())
    # fixture-ul are 3 `article[data-adid]` + 1 `article` fara atribut (control)
    assert len(out) == 3
    assert all(r["platform"] == "kleinanzeigen_auto" for r in out)
    assert not any("fara-adid" in (r.get("source_url") or "") for r in out)


# ── 2: campurile primului card, contra fixture-ului real ─────────────────────────
def test_campurile_primului_card(monkeypatch):
    card, ld = _primul_card_ld()
    out = _cauta(monkeypatch, _html())
    r = out[0]

    assert r["external_id"] == card["data-adid"]
    assert r["source_url"] == ka._BASE + card["data-href"]
    assert r["source_url"].startswith(ka._BASE + "/s-anzeige/")
    # Titlul vine din JSON-LD, unde cheia e `title` (ImageObject), nu `name`.
    assert r["titlu"] == ld["title"]
    assert r["titlu"]
    assert r["moneda"] == "EUR"
    # Pretul NU e in JSON-LD (ImageObject n-are offers) — vine din DOM.
    assert "price" not in ld and "offers" not in ld
    assert isinstance(r["pret"], float) and r["pret"] > 0


def test_pretul_e_cel_cerut_nu_cel_taiat_si_nu_din_descriere(monkeypatch):
    """Doua capcane reale, ambele masurate in fixture:
    - descrierea unui card contine "39.033,61€ Netto", desi pretul cerut e 46.450 €;
    - alt card are DOUA preturi (cerut + taiat), iar cel cerut e primul in DOM.
    """
    out = _cauta(monkeypatch, _html())
    preturi = [r["pret"] for r in out]
    assert preturi[0] == 46450.0        # nu 39033.61 (momeala din descriere)
    assert preturi[1] == 9000.0         # nu 9500.0 (pretul taiat)
    assert all(p is not None for p in preturi)


def test_locatia_si_thumbnail_ul(monkeypatch):
    out = _cauta(monkeypatch, _html())
    # "PLZ Oras" dintr-o frunza, nu dintr-o clasa
    assert re.match(r"^\d{5}\s+\S", out[0]["locatie"])
    assert out[0]["thumbnail_url"]


# ── 3: fallback-ul pe text cand JSON-LD-ul lipseste ──────────────────────────────
def test_fara_json_ld_titlul_si_pretul_vin_din_dom(monkeypatch):
    soup = BeautifulSoup(_html(), "html.parser")
    for sc in soup.select('article[data-adid] script[type="application/ld+json"]'):
        sc.decompose()
    out = _cauta(monkeypatch, str(soup))

    assert len(out) == 3
    assert out[0]["pret"] == 46450.0        # pretul n-a depins niciodata de JSON-LD
    assert out[0]["titlu"]
    # Titlul de rezerva e cea mai LUNGA ancora /s-anzeige/, nu prima: prima e insigna
    # cu numarul de poze ("20"), care ar fi trecut de garda `if not titlu`.
    assert not out[0]["titlu"].isdigit()
    assert len(out[0]["titlu"]) > 10


# ── 4: markup fara data-adid = semnal in stdout, nu tacere ───────────────────────
def test_markup_fara_data_adid_semnaleaza(monkeypatch, capsys):
    out = _cauta(monkeypatch, "<html><body>nimic</body></html>")
    assert out == []
    assert "markup fara data-adid" in capsys.readouterr().out


# ── 5: non-200 ramane [] (comportament existent) ─────────────────────────────────
def test_non_200_intoarce_gol(monkeypatch):
    assert _cauta(monkeypatch, _html(), status=503) == []


# ── garda: fixture-ul n-are date de contact ──────────────────────────────────────
def test_fixture_fara_date_de_contact():
    html = _html()
    # singurele `@` permise sunt cheile schema.org
    assert set(re.findall(r"@\w+", html)) <= {"@context", "@type"}
    assert not re.search(r"\b(tel|phone|e-?mail)\b", html, re.I)
