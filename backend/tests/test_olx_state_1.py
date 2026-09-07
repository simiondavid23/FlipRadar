"""OLX-STATE-1 — o singura parsare de `__PRERENDERED_STATE__` per pagina.

Runda e REFACTORIZARE: cele trei copii locale ale aceleiasi parsari
(`_extract_olx_numeric_ids` la Radar, `_extract_numeric_ids` la Imobiliare,
`_photos_map_from_state` la Auto) au disparut, iar ce citeau vine din
`extract_olx_ad_meta`. Ca sa se vada ca NIMIC observabil nu s-a schimbat, testele de
paritate compara iesirea de azi cu `fixtures/olx_meta_expected.json` — oracol generat
din cele trei functii VECHI, inainte de orice modificare, si nemairegenerat.

Al doilea obiectiv: `iso_to_naive_bucuresti` / `normalize_iso` s-au mutat in
`utils/listing_dates.py` (le foloseau Autovit, Storia si AutoScout24, module fara nicio
legatura cu OLX). Fara re-export de compatibilitate — T5 pinuieste si absenta lor.
"""
import asyncio
import json
import os
from datetime import datetime

from app.scrapers.auto.listings import olx_auto as auto
from app.scrapers.auto.listings.olx_auto import _olx_upgrade_thumb
from app.scrapers.real_estate import olx_real_estate as re_olx
from app.services.radar import olx_scraper as radar
from app.utils import listing_dates, olx_state
from app.utils.olx_state import extract_olx_ad_meta

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
_ORACOL = os.path.join(_FIX, "olx_meta_expected.json")

_FIX_RADAR = "olx_listing_state.html"
_FIX_RE = "olx_re_listing_state.html"

# Valorile pinuite de test_date_2.py::test_t1_meta_pe_fixture_radar. Repetate aici ca
# T3 sa pice daca trecerea unica prin `ads[]` strica ceva din contractul vechi.
_DATE2_T1 = {"token": "kTxu0",
             "created": "2026-09-02T12:54:54+03:00",
             "refreshed": "2026-09-05T14:28:06+03:00"}


def _fixture(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


def _oracol() -> dict:
    with open(_ORACOL, encoding="utf-8") as f:
        return json.load(f)


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text


class _Session:
    def __init__(self, text):
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _Resp(self._text)


# ── T1 — paritate numeric_id ─────────────────────────────────────────────────────

def test_t1_numeric_id_identic_cu_cele_doua_functii_vechi():
    """Radar si Imobiliare aveau implementari identice; meta le inlocuieste pe amandoua.

    Forma canonica difera intr-un singur punct, documentat: meta pastreaza cheia cu
    valoarea None cand ad-ul n-are `id`, in timp ce functiile vechi omiteau intrarea.
    Comparatia filtreaza None-urile, deci compara exact ce vedea call site-ul.
    """
    oracol = _oracol()
    for nume in (_FIX_RADAR, _FIX_RE):
        meta = extract_olx_ad_meta(_fixture(nume))
        obtinut = {k: v["numeric_id"] for k, v in meta.items()
                   if v["numeric_id"] is not None}
        assert obtinut == oracol[nume]["radar_numeric_ids"], nume
        assert obtinut == oracol[nume]["re_numeric_ids"], nume
        # cheie cu cheie, ca esecul sa spuna CARE ad difera
        for token, nid in oracol[nume]["radar_numeric_ids"].items():
            assert meta[token]["numeric_id"] == nid, (nume, token)


def test_t1b_oracolul_chiar_are_continut():
    """Garda pe oracol: un fisier gol ar face T1/T2 sa treaca degeaba."""
    oracol = _oracol()
    assert set(oracol) == {_FIX_RADAR, _FIX_RE}
    assert len(oracol[_FIX_RADAR]["radar_numeric_ids"]) == 52
    assert len(oracol[_FIX_RE]["radar_numeric_ids"]) == 51


# ── T2 — paritate photos ─────────────────────────────────────────────────────────

def test_t2_photos_identice_cu_photos_map_from_state():
    """`_photos_map_from_state` dadea PRIMA poza, ridicata la ;s=1000x1000.

    Meta da lista BRUTA; ridicarea a ramas in `olx_auto._olx_upgrade_thumb`. Compunerea
    celor doua trebuie sa dea exact ce dadea functia veche — aceleasi chei, aceleasi
    URL-uri, aceeasi prima poza (deci si aceeasi ordine in lista).
    """
    oracol = _oracol()
    for nume in (_FIX_RADAR, _FIX_RE):
        meta = extract_olx_ad_meta(_fixture(nume))
        obtinut = {k: _olx_upgrade_thumb(v["photos"][0])
                   for k, v in meta.items() if v["photos"]}
        assert obtinut == oracol[nume]["auto_photos"], nume


def test_t2b_ordinea_pozelor_e_cea_din_state():
    """Prima poza din lista e cea pe care o alegea functia veche — nu o alta."""
    meta = extract_olx_ad_meta(_fixture(_FIX_RADAR))
    asteptat = _oracol()[_FIX_RADAR]["auto_photos"]
    token = next(iter(asteptat))
    poze = meta[token]["photos"]
    assert poze and _olx_upgrade_thumb(poze[0]) == asteptat[token]
    assert all(isinstance(p, str) for p in poze)


# ── T3 — contractul DATE-2 e neatins de trecerea unica ──────────────────────────

def test_t3_categoria_si_datele_raman_ce_erau_la_date_2():
    meta = extract_olx_ad_meta(_fixture(_FIX_RADAR))
    ad = meta[_DATE2_T1["token"]]
    assert ad["created"] == _DATE2_T1["created"]
    assert ad["refreshed"] == _DATE2_T1["refreshed"]
    assert ad["category_id"] is not None
    assert len(meta) == 52


def test_t3b_meta_are_exact_cele_cinci_chei():
    meta = extract_olx_ad_meta(_fixture(_FIX_RADAR))
    for ad in meta.values():
        assert set(ad) == {"category_id", "created", "refreshed",
                           "numeric_id", "photos"}


# ── T4 — o SINGURA parsare per pagina, pe toate trei modulele ───────────────────

def _contor(monkeypatch):
    """Numara apelurile de `extract_olx_state` (singura poarta de intrare in state)."""
    apeluri = []
    original = olx_state.extract_olx_state

    def numarat(html):
        apeluri.append(1)
        return original(html)

    monkeypatch.setattr(olx_state, "extract_olx_state", numarat)
    return apeluri


def test_t4_radar_parseaza_state_ul_o_singura_data(monkeypatch):
    apeluri = _contor(monkeypatch)
    monkeypatch.setattr(radar.curl_requests, "get",
                        lambda url, **kw: _Resp(_fixture(_FIX_RADAR)))
    monkeypatch.setattr(radar, "get_proxy_config", lambda: None)
    monkeypatch.setattr(radar.time, "sleep", lambda s: None)

    rezultate = radar.search_olx("iphone", 100000)
    assert len(apeluri) == 1
    # si tot ce depindea de a doua parsare e in continuare acolo
    assert rezultate and all(r.get("olx_numeric_id") is not None for r in rezultate)


def test_t4b_auto_parseaza_state_ul_o_singura_data(monkeypatch):
    apeluri = _contor(monkeypatch)
    monkeypatch.setattr(auto, "AsyncSession", lambda: _Session(_fixture(_FIX_RADAR)))
    monkeypatch.setattr(auto.log_manager, "emit", lambda *a, **k: None)

    rezultate = asyncio.run(auto.search_olx_auto("bmw"))
    assert len(apeluri) == 1
    assert rezultate and sum(1 for r in rezultate if r.get("thumbnail_url")) >= 25


def test_t4c_imobiliare_parseaza_state_ul_o_singura_data(monkeypatch):
    apeluri = _contor(monkeypatch)
    monkeypatch.setattr(re_olx, "AsyncSession", lambda: _Session(_fixture(_FIX_RE)))
    monkeypatch.setattr(re_olx.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(re_olx.time, "sleep", lambda s: None)
    ceruti = []
    monkeypatch.setattr(re_olx, "_fetch_offer_details",
                        lambda nid: ceruti.append(nid) or {})

    rezultate = asyncio.run(re_olx.search_olx_real_estate({}))
    assert len(apeluri) == 1
    assert rezultate
    # enrichment-ul cere id-uri numerice reale, deci `numeric_id` a ajuns pana acolo
    assert ceruti and all(isinstance(n, int) for n in ceruti)


# ── T5 — helperii de data au plecat in listing_dates ────────────────────────────

def test_t5_helperii_sunt_in_listing_dates_si_nu_mai_sunt_in_olx_state():
    assert hasattr(listing_dates, "iso_to_naive_bucuresti")
    assert hasattr(listing_dates, "normalize_iso")
    # fara re-export de compatibilitate: un import vechi trebuie sa pice zgomotos
    assert not hasattr(olx_state, "iso_to_naive_bucuresti")
    assert not hasattr(olx_state, "normalize_iso")


def test_t5b_comportamentul_helperilor_e_neschimbat():
    """Mutare VERBATIM — aceleasi asertii ca la DATE-2 (T11), pe noul modul."""
    a = listing_dates.iso_to_naive_bucuresti("2026-08-01T06:45:38Z")
    b = listing_dates.iso_to_naive_bucuresti("2026-08-01T09:45:38+03:00")
    assert a == b and a.tzinfo is None
    assert listing_dates.iso_to_naive_bucuresti("2026-08-01T06:45:38") == datetime(
        2026, 8, 1, 6, 45, 38)
    assert listing_dates.iso_to_naive_bucuresti(None) is None
    assert listing_dates.normalize_iso("2026-08-01T06:45:38Z") == "2026-08-01T06:45:38+00:00"
    assert listing_dates.normalize_iso("2026-09-06 14:20:32") == "2026-09-06 14:20:32"
    assert listing_dates.normalize_iso(None) is None


def test_t5c_olx_state_nu_mai_importa_datetime():
    """Modulul a ramas strict un parser de state — fara dependente de data.

    Se verifica INSTRUCTIUNILE de import, nu textul brut: docstring-ul mentioneaza
    `listing_dates` ca sa spuna unde au plecat helperii, si e in regula.
    """
    import ast
    import inspect

    importate = set()
    for nod in ast.walk(ast.parse(inspect.getsource(olx_state))):
        if isinstance(nod, ast.Import):
            importate.update(a.name for a in nod.names)
        elif isinstance(nod, ast.ImportFrom):
            importate.add(nod.module or "")
    assert importate == {"json", "re", "typing"}, importate


# ── T6 — degradare curata pe forme incomplete ──────────────────────────────────

def _state_html(ads: list) -> str:
    """`__PRERENDERED_STATE__` in forma reala: literal JSON dublu-encodat."""
    interior = json.dumps({"listing": {"listing": {"ads": ads}}})
    return (f"<html><body><script>window.__PRERENDERED_STATE__ = "
            f"{json.dumps(interior)};</script></body></html>")


def _ad(token: str, **extra) -> dict:
    return {"url": f"https://www.olx.ro/d/oferta/ceva-ID{token}.html", **extra}


def test_t6_fara_state():
    assert extract_olx_ad_meta("<html><body>nimic</body></html>") == {}
    assert extract_olx_ad_meta("") == {}
    assert extract_olx_ad_meta(None) == {}
    assert extract_olx_ad_meta(
        '<script>window.__PRERENDERED_STATE__ = "{nu-i json";</script>') == {}


def test_t6b_ad_fara_photos_da_lista_goala():
    """Trei forme care la `_photos_map_from_state` sareau ad-ul; acum dau []."""
    meta = extract_olx_ad_meta(_state_html([
        _ad("A1"),                                   # fara cheia photos
        _ad("A2", photos=[]),                        # lista goala
        _ad("A3", photos="nu-i lista"),              # tip gresit
        _ad("A4", photos=[123, "https://x/y.jpg"]),  # intrare non-str filtrata
    ]))
    assert meta["A1"]["photos"] == []
    assert meta["A2"]["photos"] == []
    assert meta["A3"]["photos"] == []
    assert meta["A4"]["photos"] == ["https://x/y.jpg"]


def test_t6c_ad_fara_id_da_numeric_id_none():
    meta = extract_olx_ad_meta(_state_html([_ad("B1"), _ad("B2", id=42)]))
    assert meta["B1"]["numeric_id"] is None
    assert meta["B2"]["numeric_id"] == 42


def test_t6d_ad_fara_id_nu_ajunge_la_enrichment(monkeypatch):
    """Consecinta la call site: `numeric_id: None` se sare, ca inainte cand cheia lipsea."""
    monkeypatch.setattr(re_olx, "AsyncSession", lambda: _Session(_state_html([
        {"url": "https://www.olx.ro/d/oferta/fara-id-IDzz1.html"},
    ]) + '<div data-cy="l-card"><a href="/d/oferta/fara-id-IDzz1.html">'
        '<h4>Apartament</h4></a><p data-testid="ad-price">85 000 €</p></div>'))
    monkeypatch.setattr(re_olx.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(re_olx.time, "sleep", lambda s: None)
    ceruti = []
    monkeypatch.setattr(re_olx, "_fetch_offer_details",
                        lambda nid: ceruti.append(nid) or {})

    asyncio.run(re_olx.search_olx_real_estate({}))
    assert ceruti == []


# ── Garda: cele trei copii locale chiar au disparut ────────────────────────────

def test_copiile_locale_de_parsare_nu_mai_exista():
    assert not hasattr(radar, "_extract_olx_numeric_ids")
    assert not hasattr(auto, "_photos_map_from_state")
    assert not hasattr(re_olx, "_extract_numeric_ids")


def test_regexul_de_state_e_intr_un_singur_loc():
    """Regexul de state exista intr-un SINGUR loc: utils/olx_state.py.

    Se cauta fragmentul de regex, nu numele cheii: cele trei module vorbesc in
    continuare despre `__PRERENDERED_STATE__` in comentarii, si asta e in regula —
    ce nu mai au voie e sa-l parseze ele.
    """
    import inspect

    fragment = r"__PRERENDERED_STATE__\s*=\s*("
    assert fragment in inspect.getsource(olx_state)
    for modul in (radar, auto, re_olx):
        assert fragment not in inspect.getsource(modul), modul.__name__
