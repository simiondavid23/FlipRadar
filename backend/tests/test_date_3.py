"""DATE-3 — ultimele surse de data: AutoScout24 (on-demand), Vinted (la scan), Okazii.

Incheie seria DATE-1 (coloanele) / DATE-2 (OLX, Storia, Autovit) / KLEIN-1 (Kleinanzeigen):
  * AutoScout24 — listarea NU are nicio cheie de data (masurat: 20 de anunturi), deci
    `listed_at` vine DOAR din detaliul on-demand, prin
    `props.pageProps.listingDetails.createdTimestampWithOffset`, citit pe CALE EXACTA.
  * Vinted — `photo.high_resolution.timestamp` e momentul incarcarii anuntului; extras
    intr-o functie pura testabila care accepta si dict, si obiect cu atribute.
  * Okazii — platforma nu publica data; `listed_at` ramane None (fapt documentat).

Totul offline: fixture-uri anonimizate + HTML/JSON sintetic. Zero retea.
"""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.scrapers.auto.listings import detail as dt
from app.services.radar import vinted_scraper as vs

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")
_FIX_AS24 = os.path.join(_FIX, "autoscout24_detail.html")
_FIX_VINTED = os.path.join(_FIX, "vinted_catalog.json")

# Valoarea reala din fixture-ul AS24 (`createdTimestampWithOffset`).
_AS24_ISO = "2026-09-03T17:52:33.801Z"
# Timestamp-ul pozei principale din primul item al catalogului Vinted.
_VINTED_TS = 1788699920


def _as24_html() -> str:
    with open(_FIX_AS24, encoding="utf-8") as f:
        return f.read()


def _catalog() -> dict:
    with open(_FIX_VINTED, encoding="utf-8") as f:
        return json.load(f)


def _naiv_local_din_utc(iso: str) -> datetime:
    """Referinta calculata independent de cod: UTC aware -> naiv, ora Bucurestiului.

    HOTFIX CI — inainte folosea `.astimezone()` fara argument, adica fusul MASINII.
    Cum si implementarea facea la fel, testul trecea oriunde: cele doua greseli se
    anulau. Acum implementarea converteste explicit la Europe/Bucharest, deci si
    referinta trebuie sa fie acolo — altfel testul ar fi picat pe runner-ul UTC.
    """
    return (datetime.fromisoformat(iso.replace("Z", "+00:00"))
            .astimezone(ZoneInfo("Europe/Bucharest")).replace(tzinfo=None))


def _as24_detail(monkeypatch, html: str) -> dict:
    monkeypatch.setattr(dt, "_fetch", lambda url, referer: html)
    return dt.fetch_autoscout24_detail("https://www.autoscout24.ro/oferte/exemplu")


def _next_data_html(payload: dict) -> str:
    return ('<html><body><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload) + "</script></body></html>")


# ── T1 — AS24 pe fixture: data corecta, restul extractiei intact ─────────────────

def test_t1_as24_detaliu_pe_fixture(monkeypatch):
    out = _as24_detail(monkeypatch, _as24_html())

    assert out["listed_at"] == _naiv_local_din_utc(_AS24_ISO)
    assert out["listed_at"].tzinfo is None          # conventia Auto: naiv local
    assert out["listed_at"].date().isoformat() in ("2026-09-03", "2026-09-04")

    # Regresie pe restul extractiei: cele trei campuri existente raman populate.
    assert out["images"] and all(u.startswith("http") for u in out["images"])
    assert out["description"] and len(out["description"]) > 100
    assert out["seller_name"] == "Regge Autogroep"


def test_t1b_as24_nu_emite_refreshed_at(monkeypatch):
    """AS24 n-are date de repromovare — cheia nu se inventeaza."""
    out = _as24_detail(monkeypatch, _as24_html())
    assert out.get("refreshed_at") is None
    assert set(out) == {"images", "description", "seller_name", "listed_at"}


# ── T2 — calea EXACTA, nu cautare recursiva dupa cheie ──────────────────────────

def test_t2_cheia_din_alt_bloc_nu_e_luata(monkeypatch):
    """`createdTimestampWithOffset` in afara lui `listingDetails` NU trebuie citit.

    Pinuieste calea exacta: o cautare recursiva dupa nume de cheie (ca `_first_str`,
    folosit pentru imagini/descriere/seller) ar prinde aici valoarea din `translations`.
    """
    html = _next_data_html({"props": {"pageProps": {
        "listingDetails": {"id": "abc", "vehicle": {}},
        "translations": {"createdTimestampWithOffset": "2020-01-01T00:00:00.000Z"},
    }}})
    assert _as24_detail(monkeypatch, html)["listed_at"] is None


def test_t2b_calea_exacta_citeste_din_listing_details(monkeypatch):
    """Controlul pozitiv al lui T2: aceeasi cheie, dar la locul ei, SE citeste."""
    html = _next_data_html({"props": {"pageProps": {
        "listingDetails": {"createdTimestampWithOffset": "2026-01-15T08:30:00.000Z"},
        "translations": {"createdTimestampWithOffset": "2020-01-01T00:00:00.000Z"},
    }}})
    out = _as24_detail(monkeypatch, html)
    assert out["listed_at"] == _naiv_local_din_utc("2026-01-15T08:30:00.000Z")


def test_t2c_structuri_lipsa_sau_stricate_dau_none(monkeypatch):
    for payload in ({}, {"props": {}}, {"props": {"pageProps": {}}},
                    {"props": {"pageProps": {"listingDetails": None}}},
                    {"props": {"pageProps": {"listingDetails": "nu-i dict"}}},
                    {"props": {"pageProps": {"listingDetails": {
                        "createdTimestampWithOffset": "maine"}}}}):
        assert _as24_detail(monkeypatch, _next_data_html(payload))["listed_at"] is None


# ── T3 — SCRAPE-1b ramane valabil: prima inmatriculare NU e data postarii ───────

def test_t3_first_registration_nu_devine_listed_at(monkeypatch):
    html = _next_data_html({"props": {"pageProps": {"listingDetails": {
        "vehicle": {"firstRegistrationDateRaw": "2008-06-01",
                    "firstRegistrationDate": "06/2008"},
        "seller": {"dealer": {"customerSince": 2026}},
    }}}})
    assert _as24_detail(monkeypatch, html)["listed_at"] is None


def test_t3b_pe_fixture_data_nu_e_cea_de_inmatriculare(monkeypatch):
    """Fixture-ul are AMBELE: EZ 2008-06-01 si postarea 2026-09-03. Se ia a doua."""
    assert "firstRegistrationDateRaw" in _as24_html()
    out = _as24_detail(monkeypatch, _as24_html())
    assert out["listed_at"].year == 2026


# ── T4 — `_listed_at_din_poza`, functie pura ────────────────────────────────────

def test_t4_pe_dict_din_fixture():
    photo = _catalog()["items"][0]["photo"]
    assert photo["high_resolution"]["timestamp"] == _VINTED_TS
    rezultat = vs._listed_at_din_poza(photo)
    assert rezultat == datetime.fromtimestamp(_VINTED_TS)
    assert rezultat.tzinfo is None


def test_t4b_pe_obiect_cu_atribute():
    """Modelul tipizat al libariei `vinted_scraper` da acelasi rezultat ca dict-ul."""
    obiect = SimpleNamespace(high_resolution=SimpleNamespace(timestamp=_VINTED_TS))
    assert vs._listed_at_din_poza(obiect) == vs._listed_at_din_poza(
        {"high_resolution": {"timestamp": _VINTED_TS}})


def test_t4c_degradare_curata_fara_exceptie():
    for intrare in (None, {}, {"high_resolution": None}, {"high_resolution": {}},
                    {"high_resolution": {"timestamp": None}},
                    {"high_resolution": {"timestamp": 0}},
                    {"high_resolution": {"timestamp": "acum"}},
                    {"high_resolution": "nu-i dict"},
                    SimpleNamespace(), SimpleNamespace(high_resolution=None)):
        assert vs._listed_at_din_poza(intrare) is None, intrare


def test_t4d_timestamp_ca_string_de_cifre_merge():
    assert (vs._listed_at_din_poza({"high_resolution": {"timestamp": str(_VINTED_TS)}})
            == datetime.fromtimestamp(_VINTED_TS))


# ── T5 — bucla de scan Vinted duce data pana in rezultat ────────────────────────

def _wrapper_fals(monkeypatch, payload: dict):
    monkeypatch.setattr(vs, "_get_wrapper",
                        lambda: SimpleNamespace(search=lambda params: payload))
    monkeypatch.setattr(vs.log_manager, "emit", lambda *a, **k: None)


def test_t5_scan_vinted_pe_catalogul_din_fixture(monkeypatch):
    _wrapper_fals(monkeypatch, _catalog())
    out = vs._search_vinted_library("rochie", None, None, None, [], [])

    assert out, "fixture-ul trebuie sa produca rezultate"
    assert all(r["listed_at"] is not None for r in out)
    assert all(r["listed_at"].tzinfo is None for r in out)
    assert out[0]["listed_at"] == datetime.fromtimestamp(_VINTED_TS)
    # `refreshed_at` nu se emite la Vinted: poza nu spune nimic despre repromovare.
    assert all(r.get("refreshed_at") is None for r in out)


def test_t5b_item_fara_timestamp_ramane_fara_data(monkeypatch):
    _wrapper_fals(monkeypatch, {"items": [{
        "id": 42, "title": "Rochie test", "price": {"amount": "50", "currency_code": "RON"},
        "url": "https://www.vinted.ro/items/42",
        "photo": {"url": "https://x/y.jpg"},   # fara high_resolution
    }]})
    (item,) = vs._search_vinted_library("rochie", None, None, None, [], [])
    assert item["listed_at"] is None
    assert item["images"] == ["https://x/y.jpg"]   # poza tot se ia


# ── T6 — Okazii nu are data (fapt documentat, nu bug) ───────────────────────────

_CARD_OKAZII = """
<html><body><div id="listing-Okazii">
  <div class="list-item">
    <a class="item-title" href="https://www.okazii.ro/telefon-exemplu-a123456789">
      Husa silicon transparenta</a>
    <div class="item-price"><span class="price">25,00 Lei</span></div>
    <img src="https://static.okazii.ro/x.jpg" />
  </div>
</div></body></html>
"""


def test_t6_okazii_nu_produce_listed_at(monkeypatch):
    from app.services.radar import okazii_scraper as ok

    monkeypatch.setattr(ok, "_request", lambda *a, **k: _CARD_OKAZII)
    monkeypatch.setattr(ok.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(ok.time, "sleep", lambda s: None)
    out = ok.search_okazii("husa", 1000)

    assert out, "cardul sintetic trebuie parsat"
    assert all(r.get("listed_at") is None for r in out)


def test_t6b_faptul_masurat_e_scris_in_modul():
    """Garda pe documentatie: cine cauta data pe Okazii gaseste raspunsul in docstring."""
    from app.services.radar import okazii_scraper as ok

    assert "NU publica data anuntului" in (ok.__doc__ or "")


# ── Garda: fixture-urile raman anonimizate ──────────────────────────────────────

def test_fixture_vinted_e_anonimizat():
    brut = open(_FIX_VINTED, encoding="utf-8").read()
    catalog = json.loads(brut)
    for item in catalog["items"]:
        assert item["user"] == {"id": 0, "login": "ANONIMIZAT"}
    assert "search_tracking_params" not in brut
    assert '"conversion"' not in brut


def test_fixture_as24_are_doar_date_de_firma():
    """Vanzatorul e dealer (firma), cu telefoane de birou — nimic de persoana fizica."""
    import re

    html = _as24_html()
    data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                html, re.DOTALL).group(1))
    seller = data["props"]["pageProps"]["listingDetails"]["seller"]
    assert seller["isDealer"] is True and seller["type"] == "Dealer"
    assert all(t.get("phoneType") == "Office" for t in seller.get("phones") or [])
    # singurele adrese din fixture sunt exemple/corporate, nu ale unei persoane
    adrese = set(re.findall(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", html))
    assert adrese <= {"ion.popescu@example.com", "ion.popescu@exemplu.ro",
                      "widerspruch@autoscout24.de"}


_ = timezone   # referit implicit prin conversia UTC -> naiv local de mai sus
