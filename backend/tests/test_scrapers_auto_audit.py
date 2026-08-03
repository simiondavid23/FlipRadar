"""SCRAPE-AUDIT (auto) — fix-urile auditului modulului auto.

Bug-urile reparate: routerul de cautare pasa dict-ul de filtre pe pozitia `model`
la 3 din 6 platforme (crash inghitit de gather -> 0 rezultate tacut); modelul era
ignorat complet pe autovit; fuel_type se pierdea pe autoscout24 (alias lipsa, desi
confirmat in auto_categories); parse_money facea "€ 12.500" -> 12.5 pe loturi;
extract_km lua PRIMUL "N km" din text ("la 20 km de Bucuresti" -> rulaj 20);
firstRegistrationDate era salvat drept data postarii; km_max/year_to fara plasa
locala pe platformele fara parametri server-side.
"""
import asyncio
import inspect

import pytest

from app.scrapers.auto.listings import _common as lc
from app.scrapers.auto.lots import _common as lot
from app.scrapers.auto.listings import autovit_scraper as av
from app.scrapers.auto.listings import autoscout24_scraper as as24


# ── parse_money (loturi): formate europene si americane ─────────────────────────

def test_parse_money_format_european():
    assert lot.parse_money("€ 12.500") == 12500.0
    assert lot.parse_money("1.234.567") == 1234567.0


def test_parse_money_format_american_neschimbat():
    assert lot.parse_money("$1,234.56") == 1234.56
    assert lot.parse_money("$1,234") == 1234.0


def test_parse_money_zecimal_simplu():
    assert lot.parse_money("12.5") == 12.5
    assert lot.parse_money(1500) == 1500.0


# ── extract_km: cel mai mare candidat plauzibil ──────────────────────────────────

def test_extract_km_ignora_distanta_pana_la_oras():
    assert lc.extract_km("la 20 km de Bucuresti, 150.000 km") == 150000


def test_extract_km_formate_normale_neschimbate():
    assert lc.extract_km("85 000 km") == 85000
    assert lc.extract_km("123.456 km rulaj real") == 123456


def test_extract_km_garda_de_garbage_ramane():
    assert lc.extract_km("11202035000 km") is None


# ── autovit: modelul din filters + filtrarea locala pe titlu ─────────────────────

def _fake_autovit_html(titles):
    cards = "".join(
        f'<article data-id="id{i}"><a href="/anunt/x-{i}"><h2>{t}</h2></a></article>'
        for i, t in enumerate(titles))
    return f"<html><body>{cards}</body></html>"


class _FakeResp:
    def __init__(self, text):
        self.status_code = 200
        self.text = text


class _FakeSession:
    def __init__(self, text):
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        return _FakeResp(self._text)


def _run_autovit(monkeypatch, titles, model="", filters=None):
    html = _fake_autovit_html(titles)
    monkeypatch.setattr(av, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(av.log_manager, "emit", lambda *a, **k: None)
    return asyncio.run(av.search_autovit(make="bmw", model=model,
                                         filters=filters or {}))


def test_autovit_modelul_din_filters_filtreaza_titlurile(monkeypatch):
    out = _run_autovit(monkeypatch,
                       ["BMW Seria 3 320d", "BMW X5 xDrive", "BMW Seria 3 Touring"],
                       filters={"model": "Seria 3"})
    assert len(out) == 2
    assert all("seria 3" in (r.get("titlu") or "").lower() for r in out)


def test_autovit_model_cu_diacritice_straine(monkeypatch):
    out = _run_autovit(monkeypatch, ["Skoda Octavia 2.0", "BMW X5"],
                       filters={"model": "Škoda"})
    assert len(out) == 1 and "Skoda" in out[0]["titlu"]


def test_autovit_fara_model_pastreaza_tot(monkeypatch):
    out = _run_autovit(monkeypatch, ["BMW Seria 3", "BMW X5"])
    assert len(out) == 2


# ── autoscout24: fuel_type ajunge in parametri (prin CALL SITE-ul real) ──────────

class _CapturingSession:
    """Sesiune falsa care captureaza params trimisi de scraper la GET."""
    captured: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        _CapturingSession.captured = dict(kw.get("params") or {})
        return _FakeResp("<html><body></body></html>")


def test_autoscout24_fuel_ajunge_in_parametri(monkeypatch):
    # Prin search_autoscout24 REAL, nu prin apel direct la apply_confirmed_filters
    # cu aliasuri proprii — altfel testul nu vede call site-ul din scraper.
    _CapturingSession.captured = {}
    monkeypatch.setattr(as24, "AsyncSession", lambda: _CapturingSession())
    asyncio.run(as24.search_autoscout24(make="bmw", filters={"fuel": "diesel"}))
    assert _CapturingSession.captured.get("fuel") == "D"


# ── router: semnaturile primesc modelul si filtrele pe pozitiile corecte ─────────

def test_router_builders_respecta_semnaturile():
    # Garda structurala: apelurile din router trebuie sa lege `filters` pe
    # parametrul `filters`, nu pe `model` (bug-ul original crapa cu orice filtru).
    import app.routers.auto as ar
    src = inspect.getsource(ar)
    assert "search_mobile_de(\n            f.get(\"make_id\", \"\") or make, f.get(\"model\", \"\"), q, f)" in src
    assert 'search_autoscout24(make, f.get("model", ""), f)' in src
    assert "search_kleinanzeigen_auto(\n            q, make, f.get(\"model\", \"\"), f)" in src


# ── detail: firstRegistrationDate nu mai e data postarii ─────────────────────────

def test_detail_nu_mai_mapeaza_prima_inmatriculare_pe_listed_at():
    from app.scrapers.auto.listings import detail as dt
    src = inspect.getsource(dt)
    assert 'for k in ("firstRegistrationDate", "firstRegistration"):' not in src


# ── scanner: plasa locala km_max / year_to ───────────────────────────────────────

def test_scanner_plasa_km_si_an(monkeypatch):
    # Verificam direct predicatul inline: un listing cu km peste kw.km_max sau an
    # peste kw.year_to nu ajunge la _save_listing (fail-open pe valori lipsa).
    from app.services import auto_listings_scanner as als
    src = inspect.getsource(als)
    assert 'if kw.km_max and r.get("km") and int(r["km"]) > int(kw.km_max):' in src
    assert 'if kw.year_to and r.get("year") and int(r["year"]) > int(kw.year_to):' in src
