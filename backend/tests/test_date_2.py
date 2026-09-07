"""DATE-2 — extractoare pentru `listed_at` / `refreshed_at`: OLX (Radar, Imobiliare,
Auto), Storia si Autovit.

DATE-1 a instalat coloanele si regula; runda asta le ALIMENTEAZA la scan, din date
structurate deja prezente in HTML-ul pe care scraperele il descarca oricum. Regula,
neschimbata: data etichetata ca actualizare merge in `refreshed_at` si niciodata in
`listed_at`; data de publicare merge in `listed_at`.

Totul offline: fixture-uri capturate pe 2026-09-06 + HTML sintetic. Zero retea.
"""
import asyncio
import json
import os
from datetime import datetime

# OLX-STATE-1: helperii de data au plecat in `utils/listing_dates`; parserul de state
# a ramas in `utils/olx_state`. Doar importurile s-au re-tintit, nicio asertie.
from app.utils.listing_dates import iso_to_naive_bucuresti, normalize_iso
from app.utils.olx_state import extract_olx_ad_meta, extract_olx_state

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(nume: str) -> str:
    with open(os.path.join(_FIX, nume), encoding="utf-8") as f:
        return f.read()


# ── dubluri de retea (acelasi tipar ca test_scrapers_auto_audit) ─────────────────

class _FakeResp:
    def __init__(self, text, status=200):
        self.status_code = status
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


def _state_html(ads: list, extra_body: str = "") -> str:
    """HTML mic cu `__PRERENDERED_STATE__` in forma REALA: string JSON escapat.

    `json.dumps(json.dumps(obj))` produce exact literalul pe care il emite OLX
    (ghilimele + escape-uri interne), deci trece prin acelasi dublu-decode.
    """
    stare = {"listing": {"listing": {"ads": ads}}}
    return (f"<html><body>{extra_body}"
            f"<script>window.__PRERENDERED_STATE__ = {json.dumps(json.dumps(stare))};</script>"
            f"</body></html>")


def _ad(token: str, created=None, refreshed=None, cat="1165") -> dict:
    ad = {"url": f"https://www.olx.ro/d/oferta/ceva-ID{token}.html",
          "category": {"id": cat}}
    if created:
        ad["createdTime"] = created
    if refreshed:
        ad["lastRefreshTime"] = refreshed
    return ad


# ── T1 — parserul comun pe fixture-ul real ───────────────────────────────────────

def test_t1_meta_pe_fixture_radar():
    meta = extract_olx_ad_meta(_fixture("olx_listing_state.html"))
    assert len(meta) == 52
    primul = meta["kTxu0"]
    assert primul["created"] == "2026-09-02T12:54:54+03:00"
    assert primul["refreshed"] == "2026-09-05T14:28:06+03:00"
    assert primul["category_id"] is not None


def test_t1b_meta_pe_fixture_imobiliare():
    meta = extract_olx_ad_meta(_fixture("olx_re_listing_state.html"))
    assert len(meta) == 51
    primul = meta["kGsBz"]
    # Exact eroarea pe care o inchide DATE-2: publicat in iunie, repromovat in septembrie.
    assert primul["created"].startswith("2026-06-19")
    assert primul["refreshed"].startswith("2026-09-03")


def test_t1c_pushup_time_e_ignorat():
    """`pushupTime` nu apare in contract: masurat, unde exista e egal cu
    `lastRefreshTime`, iar `lastRefreshTime` e prezent pe 100% din ad-uri."""
    html = _state_html([dict(_ad("A1", created="2026-01-01T00:00:00+02:00",
                                 refreshed="2026-02-02T00:00:00+02:00"),
                             pushupTime="2026-03-03T00:00:00+02:00")])
    m = extract_olx_ad_meta(html)["A1"]
    assert m["refreshed"] == "2026-02-02T00:00:00+02:00"
    # OLX-STATE-1: contractul a crescut cu `numeric_id` si `photos` (o singura parsare
    # per pagina). Asertia isi pastreaza intentia: nimic derivat din `pushupTime`.
    assert set(m) == {"category_id", "created", "refreshed", "numeric_id", "photos"}
    assert "pushup" not in " ".join(m).lower()


# ── T2 — degradare curata ────────────────────────────────────────────────────────

def test_t2_fara_state_sau_json_stricat():
    assert extract_olx_ad_meta("<html><body>nimic</body></html>") == {}
    assert extract_olx_ad_meta("") == {}
    assert extract_olx_ad_meta(None) == {}
    assert extract_olx_state("<html></html>") is None
    # state prezent, dar continutul nu e JSON valid -> {} fara exceptie
    stricat = '<script>window.__PRERENDERED_STATE__ = "{nu-i json";</script>'
    assert extract_olx_ad_meta(stricat) == {}
    # state valid, dar forma neasteptata (ads nu e lista de dict-uri)
    assert extract_olx_ad_meta(_state_html(["sir", 42, None])) == {}


def test_t2b_ad_fara_date_ramane_cu_none():
    m = extract_olx_ad_meta(_state_html([_ad("B1")]))["B1"]
    assert m["created"] is None and m["refreshed"] is None
    assert m["category_id"] == "1165"


# ── T3 — Radar OLX: meta bate cardul, cardul ramane fallback ─────────────────────

_CARD_RADAR = """
  <div data-cy="l-card">
    <a href="/d/oferta/telefon-ID{token}.html"><h4>iPhone {token}</h4></a>
    <p data-testid="ad-price">1 200 lei</p>
    <p data-testid="location-date">Cluj-Napoca - {data}</p>
    <img src="https://ireland.apollo.olxcdn.com/v1/files/x.jpg;s=200x200" />
  </div>
"""


def _cauta_radar(monkeypatch, carduri: str, ads: list) -> list:
    from app.services.radar import olx_scraper as olx

    html = _state_html(ads, extra_body=carduri)
    monkeypatch.setattr(olx.curl_requests, "get", lambda url, **kw: _FakeResp(html))
    monkeypatch.setattr(olx, "get_proxy_config", lambda: None)
    monkeypatch.setattr(olx.time, "sleep", lambda s: None)
    return olx.search_olx("iphone", 5000)


def test_t3_radar_meta_bate_textul_cardului(monkeypatch):
    # Cardul spune „Reactualizat azi"; state-ul spune publicat in iunie, bumpat in septembrie.
    carduri = _CARD_RADAR.format(token="AAA", data="Reactualizat azi la 14:20")
    ads = [_ad("AAA", created="2026-06-19T12:08:33+03:00",
               refreshed="2026-09-03T21:08:21+03:00", cat="948")]
    (item,) = _cauta_radar(monkeypatch, carduri, ads)

    assert item["listed_at"] == datetime(2026, 6, 19, 12, 8, 33)
    assert item["refreshed_at"] == datetime(2026, 9, 3, 21, 8, 21)
    assert item["listed_at"].tzinfo is None and item["refreshed_at"].tzinfo is None
    assert item["olx_category"] == "948"   # categoria vine din ACEEASI parsare


def test_t3b_radar_fallback_pe_card_cand_id_lipseste_din_meta(monkeypatch):
    # ID-ul cardului (BBB) NU e in state -> ramane regula DATE-1 pe textul cardului.
    carduri = _CARD_RADAR.format(token="BBB", data="Reactualizat azi la 14:20")
    ads = [_ad("ALTUL", created="2026-06-19T12:08:33+03:00")]
    (item,) = _cauta_radar(monkeypatch, carduri, ads)

    assert item["listed_at"] is None
    assert item["refreshed_at"] is not None
    assert (item["refreshed_at"].hour, item["refreshed_at"].minute) == (14, 20)


def test_t3c_radar_fallback_fara_eticheta_ramane_listed_at(monkeypatch):
    carduri = _CARD_RADAR.format(token="CCC", data="Azi la 08:05")
    (item,) = _cauta_radar(monkeypatch, carduri, [])
    assert item["refreshed_at"] is None
    assert item["listed_at"] is not None and item["listed_at"].hour == 8


# ── T4 — Imobiliare OLX pe fixture-ul real ───────────────────────────────────────

def _cauta_re(monkeypatch, html: str) -> list:
    from app.scrapers.real_estate import olx_real_estate as re_olx

    monkeypatch.setattr(re_olx, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(re_olx.log_manager, "emit", lambda *a, **k: None)
    # enrichment-ul on-demand ar iesi la retea: il taiem, DATE-2 nu-l atinge.
    monkeypatch.setattr(re_olx, "_fetch_offer_details", lambda nid: {})
    monkeypatch.setattr(re_olx.time, "sleep", lambda s: None)
    return asyncio.run(re_olx.search_olx_real_estate({}))


def test_t4_imobiliare_pe_fixture(monkeypatch):
    """Primul anunt propriu OLX de pe pagina (`kTodo`) primeste ambele date.

    NU `kGsBz`, desi acela e primul ad din state: cardul lui trimite la
    `storia.ro/...-IDHE6J`, deci anuntul intra in feed sub `storia-HE6J` (OLX-IMO-1).
    """
    rezultate = _cauta_re(monkeypatch, _fixture("olx_re_listing_state.html"))
    prin_id = {r["external_id"]: r for r in rezultate if r.get("external_id")}
    primul = prin_id["kTodo"]

    assert primul["listed_at"] == "2026-09-01T16:03:08+03:00"
    assert primul["refreshed_at"] == "2026-09-01T16:17:52+03:00"
    # Conventia Imobiliare: STRING ISO pe care scannerul il trece prin fromisoformat.
    assert isinstance(primul["listed_at"], str)
    assert datetime.fromisoformat(primul["listed_at"]).year == 2026
    assert datetime.fromisoformat(primul["refreshed_at"]).month == 9


def test_t4b_imobiliare_kgsbz_are_ambele_date_in_state():
    """Anuntul din brief traieste in state cu ambele date, sub tokenul OLX (`kGsBz`).

    Cardul lui trimite insa la `storia.ro/...-IDHE6J`, deci in feed intra sub
    `storia-HE6J`; puntea dintre cele doua identificatoare e id-ul numeric al cardului
    (OLX-IMO-1, `test_olx_imo_1.py`). Aici pinuim doar ca datele SUNT in state.
    """
    meta = extract_olx_ad_meta(_fixture("olx_re_listing_state.html"))
    assert meta["kGsBz"]["created"].startswith("2026-06-19")
    assert meta["kGsBz"]["refreshed"].startswith("2026-09-03")


def test_t4c_imobiliare_acoperire_pe_anunturile_identificabile(monkeypatch):
    """Toate anunturile primesc ambele date — de la OLX-IMO-1, TOATE au si external_id.

    Inainte de OLX-IMO-1 acoperirea era 26 din 51 de carduri: cele 25 de anunturi Storia
    incrucisate n-aveau cheie, deci nici date. Acum feed-ul e 50/50 (MAX_RESULTS taie al
    51-lea card), din care 24 incrucisate.
    """
    rezultate = _cauta_re(monkeypatch, _fixture("olx_re_listing_state.html"))
    assert len(rezultate) == 50   # MAX_RESULTS taie la 50 din cele 51 de carduri
    identificabile = [r for r in rezultate if r.get("external_id")]
    assert len(identificabile) == 50
    assert sum(1 for r in identificabile
               if r["external_id"].startswith("storia-")) == 24
    assert [r["external_id"] for r in identificabile if not r.get("listed_at")] == []
    assert [r["external_id"] for r in identificabile if not r.get("refreshed_at")] == []


# ── T5 — testul pinuit INTORS: pe fallback, „Reactualizat" nu mai e listed_at ────

def test_t5_imobiliare_reactualizat_pe_card_merge_in_refreshed_at(monkeypatch):
    """Intoarcerea lui `test_olx_re_reactualizat_azi_are_data` la nivel de CARD.

    Parserul pur `_parse_olx_date` citeste mai departe data de sub prefix (contractul
    lui nu se schimba); ce se schimba e COLOANA in care ajunge rezultatul.
    """
    card = """
      <div data-cy="l-card">
        <a href="/d/oferta/apartament-IDzzz9.html"><h4>Apartament 2 camere</h4></a>
        <p data-testid="ad-price">85 000 €</p>
        <p data-testid="location-date">Cluj-Napoca - Reactualizat azi la 14:30</p>
        <img src="https://x/y.jpg" />
      </div>
    """
    # State FARA anuntul nostru -> se aplica fallback-ul pe textul cardului.
    (item,) = _cauta_re(monkeypatch, _state_html([], extra_body=card))

    assert item["listed_at"] is None, "o reactualizare NU are voie in listed_at"
    assert item["refreshed_at"] is not None
    reactualizat = datetime.fromisoformat(item["refreshed_at"])
    assert (reactualizat.hour, reactualizat.minute) == (14, 30)


def test_t5b_imobiliare_fallback_fara_eticheta_ramane_listed_at(monkeypatch):
    card = """
      <div data-cy="l-card">
        <a href="/d/oferta/apartament-IDzzz8.html"><h4>Apartament 3 camere</h4></a>
        <p data-testid="ad-price">95 000 €</p>
        <p data-testid="location-date">Brasov - Azi la 09:10</p>
        <img src="https://x/y.jpg" />
      </div>
    """
    (item,) = _cauta_re(monkeypatch, _state_html([], extra_body=card))
    assert item["refreshed_at"] is None
    assert datetime.fromisoformat(item["listed_at"]).hour == 9


# ── T6 — OLX Auto: naiv local din meta ───────────────────────────────────────────

def test_t6_olx_auto_din_meta(monkeypatch):
    from app.scrapers.auto.listings import olx_auto

    card = """
      <div data-cy="l-card">
        <a href="/d/oferta/bmw-seria-3-IDauto1.html"><h4>BMW Seria 3 2015</h4></a>
        <p data-testid="ad-price">7 500 €</p>
        <p data-testid="location-date">Cluj - Azi la 10:00</p>
        <img src="https://x/y.jpg;s=200x200" />
      </div>
    """
    ads = [_ad("auto1", created="2026-08-24T09:08:09+03:00",
               refreshed="2026-09-06T09:07:45+03:00", cat="1")]
    html = _state_html(ads, extra_body=card)

    monkeypatch.setattr(olx_auto, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(olx_auto.log_manager, "emit", lambda *a, **k: None)
    (item,) = asyncio.run(olx_auto.search_olx_auto("bmw"))

    assert item["listed_at"] == datetime(2026, 8, 24, 9, 8, 9)
    assert item["refreshed_at"] == datetime(2026, 9, 6, 9, 7, 45)
    assert item["listed_at"].tzinfo is None and item["refreshed_at"].tzinfo is None


def test_t6b_olx_auto_fara_meta_ramane_none(monkeypatch):
    from app.scrapers.auto.listings import olx_auto

    card = """
      <div data-cy="l-card">
        <a href="/d/oferta/audi-IDauto2.html"><h4>Audi A4 2016</h4></a>
        <p data-testid="ad-price">9 000 €</p>
        <img src="https://x/y.jpg" />
      </div>
    """
    monkeypatch.setattr(olx_auto, "AsyncSession",
                        lambda: _FakeSession(f"<html><body>{card}</body></html>"))
    monkeypatch.setattr(olx_auto.log_manager, "emit", lambda *a, **k: None)
    (item,) = asyncio.run(olx_auto.search_olx_auto("audi"))
    assert item["listed_at"] is None and item["refreshed_at"] is None


# ── T7 / T8 — Storia ─────────────────────────────────────────────────────────────

def _storia_items(html: str) -> list:
    from app.scrapers.real_estate.storia_scraper import _find_items
    import re as _re

    m = _re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
    gasite: list = []
    _find_items(json.loads(m.group(1)), gasite)
    return gasite


def test_t7_storia_pe_fixture():
    from app.scrapers.real_estate.storia_scraper import _parse_item

    items = _storia_items(_fixture("storia_search_nextdata.html"))
    assert len(items) == 37
    prin_id = {str(i.get("id")): i for i in items}
    out = _parse_item(prin_id["10502931"], "vanzare", "apartament")

    assert out["listed_at"] == "2026-08-01T06:45:38+00:00"   # `Z` normalizat
    assert out["refreshed_at"] == "2026-09-06T14:20:32+03:00"
    # Fondul rundei: publicarea NU e ziua bump-ului.
    assert "2026-09-06" not in out["listed_at"]


def test_t7b_storia_toate_anunturile_au_listed_at():
    from app.scrapers.real_estate.storia_scraper import _parse_item

    items = _storia_items(_fixture("storia_search_nextdata.html"))
    iesiri = [_parse_item(i, "vanzare", "apartament") for i in items]
    assert all(o["listed_at"] for o in iesiri)
    # `dateCreated` acopera cele doua anunturi fara `pushedUpAt`.
    assert all(o["refreshed_at"] for o in iesiri)


def test_t8_storia_fallback_doar_pentru_refreshed_at():
    from app.scrapers.real_estate.storia_scraper import _parse_item

    baza = {"id": 1, "title": "Apartament"}
    # fara pushedUpAt -> refreshed_at cade pe dateCreated
    out = _parse_item({**baza, "createdAtFirst": "2026-08-01T06:45:38Z",
                       "dateCreated": "2026-09-06 14:20:32"}, "vanzare", "apartament")
    assert out["listed_at"] == "2026-08-01T06:45:38+00:00"
    assert out["refreshed_at"] == "2026-09-06 14:20:32"

    # fara createdAtFirst -> listed_at ramane None, NU cade pe dateCreated
    out = _parse_item({**baza, "dateCreated": "2026-09-06 14:20:32",
                       "pushedUpAt": "2026-09-06T14:20:32+03:00"}, "vanzare", "apartament")
    assert out["listed_at"] is None
    assert out["refreshed_at"] == "2026-09-06T14:20:32+03:00"


# ── T9 / T10 — Autovit ───────────────────────────────────────────────────────────

def test_t9_extract_autovit_dates_pe_fixture():
    from app.scrapers.auto.listings._common import safe_soup
    from app.scrapers.auto.listings.autovit_scraper import _extract_autovit_dates

    date_map = _extract_autovit_dates(safe_soup(_fixture("autovit_search_nextdata.html")))
    assert len(date_map) == 32
    assert date_map["7060865537"] == ("2026-08-24T09:08:09Z", "2026-09-06T09:07:45Z")


def test_t9b_extract_autovit_dates_degradare_curata():
    from app.scrapers.auto.listings._common import safe_soup
    from app.scrapers.auto.listings.autovit_scraper import _extract_autovit_dates

    assert _extract_autovit_dates(safe_soup("<html></html>")) == {}
    # `data` care nu e JSON valid: se sare intrarea, nu se opreste tot
    stricat = ('<html><script id="__NEXT_DATA__" type="application/json">'
               + json.dumps({"props": {"pageProps": {"urqlState": {
                   "a": {"data": "{nu-i json"},
                   "b": {"data": json.dumps({"edges": [
                       {"node": {"id": "9", "createdAt": "2026-01-01T00:00:00Z"},
                        "vas": {"bumpDate": None}}]})},
               }}}}) + "</script></html>")
    assert _extract_autovit_dates(safe_soup(stricat)) == {
        "9": ("2026-01-01T00:00:00Z", None)}


def _autovit_html(ids: list, urql_ids: list) -> str:
    """Carduri in ordinea `ids`, iar datele in `urql_ids` — ordine DIFERITA inadins,
    ca alinierea pe pozitie sa dea alt raspuns decat alinierea pe `data-id`."""
    carduri = "".join(
        f'<article data-id="{i}"><a href="/anunt/{i}.html"><h2>Masina {i}</h2></a></article>'
        for i in ids)
    edges = [{"node": {"id": i, "createdAt": f"2026-0{n + 1}-01T00:00:00Z"},
              "vas": {"bumpDate": f"2026-0{n + 1}-15T00:00:00Z"}}
             for n, i in enumerate(urql_ids)]
    nxt = json.dumps({"props": {"pageProps": {"urqlState": {
        "cheie": {"data": json.dumps({"advertSearch": {"edges": edges}})}}}}})
    return (f'<html><body>{carduri}'
            f'<script id="__NEXT_DATA__" type="application/json">{nxt}</script>'
            f"</body></html>")


def test_t10_autovit_alinierea_e_pe_data_id_nu_pe_pozitie(monkeypatch):
    from app.scrapers.auto.listings import autovit_scraper as av

    # Cardurile: [X1, X2, X3]. Datele in urqlState: [X3, X2, X1] — inversate.
    # Pe pozitie, X1 ar primi datele lui X3 (luna 01 vs luna 03).
    html = _autovit_html(["X1", "X2", "X3"], ["X3", "X2", "X1"])
    monkeypatch.setattr(av, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(av.log_manager, "emit", lambda *a, **k: None)
    rezultate = asyncio.run(av.search_autovit(make="bmw"))

    prin_id = {r["external_id"]: r for r in rezultate}
    # X1 e ULTIMUL in urqlState (luna 03) desi e PRIMUL card -> proba ca nu e pozitional.
    assert prin_id["X1"]["listed_at"] == iso_to_naive_bucuresti("2026-03-01T00:00:00Z")
    assert prin_id["X1"]["refreshed_at"] == iso_to_naive_bucuresti("2026-03-15T00:00:00Z")
    assert prin_id["X3"]["listed_at"] == iso_to_naive_bucuresti("2026-01-01T00:00:00Z")
    for r in rezultate:
        assert r["listed_at"].tzinfo is None and r["refreshed_at"].tzinfo is None


def test_t10b_autovit_card_fara_corespondent_ramane_none(monkeypatch):
    from app.scrapers.auto.listings import autovit_scraper as av

    html = _autovit_html(["X1", "NECUNOSCUT"], ["X1"])
    monkeypatch.setattr(av, "AsyncSession", lambda: _FakeSession(html))
    monkeypatch.setattr(av.log_manager, "emit", lambda *a, **k: None)
    prin_id = {r["external_id"]: r for r in asyncio.run(av.search_autovit(make="bmw"))}

    assert prin_id["NECUNOSCUT"]["listed_at"] is None
    assert prin_id["NECUNOSCUT"]["refreshed_at"] is None
    assert prin_id["X1"]["listed_at"] is not None


# ── T11 — helperii de data ───────────────────────────────────────────────────────

def test_t11_acelasi_moment_scris_in_doua_fusuri_da_acelasi_naiv_local():
    a = iso_to_naive_bucuresti("2026-08-01T06:45:38Z")
    b = iso_to_naive_bucuresti("2026-08-01T09:45:38+03:00")
    assert a == b
    assert a.tzinfo is None


def test_t11b_iso_to_naive_bucuresti_degradare():
    assert iso_to_naive_bucuresti(None) is None
    assert iso_to_naive_bucuresti("") is None
    assert iso_to_naive_bucuresti("maine") is None
    # input deja naiv: se intoarce neschimbat (e local prin conventie)
    assert iso_to_naive_bucuresti("2026-08-01T06:45:38") == datetime(2026, 8, 1, 6, 45, 38)


def test_t11c_normalize_iso():
    assert normalize_iso("2026-08-01T06:45:38Z") == "2026-08-01T06:45:38+00:00"
    assert normalize_iso("2026-08-01T06:45:38+03:00") == "2026-08-01T06:45:38+03:00"
    assert normalize_iso("2026-09-06 14:20:32") == "2026-09-06 14:20:32"
    assert normalize_iso(None) is None and normalize_iso("   ") is None
