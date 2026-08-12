"""SCRAPE-AUDIT (radar) — fix-urile auditului scraperelor din modulul Radar.

Bug-urile reparate: pret lipsa -> grad A fals (Facebook + garda din scorer),
moneda OLX hardcodata RON pe anunturi in EUR, orasele cu cratima taiate la "-",
conditia locala OLX care golea rezultatele cand cardul n-o expunea, "Reactualizat
azi" fara data, excluderile sensibile la diacritice pe calea implicita, parametrul
`condition` mort pe Vinted, sesiunea Facebook >30 zile fara re-auth, sesiunea DB
otravita dupa o exceptie per-listing.
"""
import types

import pytest

from app.services.radar import olx_scraper as olx
from app.services.radar import vinted_scraper as vs
from app.services.radar.base_scraper import is_excluded
from app.services.radar.scorer import calculate_score


# ── scorer: pretul care nu exista nu poate primi scor ────────────────────────────

def test_pret_zero_nu_primeste_scor():
    out = calculate_score(0, 500)
    assert out["filtered"] is True and out["score"] is None


def test_pret_none_nu_primeste_scor():
    out = calculate_score(None, 500)
    assert out["filtered"] is True and out["score"] is None


def test_scorul_normal_ramane_neschimbat():
    out = calculate_score(100, 500)   # marja 80% -> A, nefiltrat
    assert out["score"] == "A" and out["filtered"] is False
    assert abs(out["margin_pct"] - 80.0) < 0.01


# ── excluderi: diacritice pliate pe ambele parti ─────────────────────────────────

def test_exclude_cu_diacritice_prinde_titlul_fara():
    assert is_excluded("Masina de spalat defecta", ["mașină", "defectă"]) is True


def test_exclude_fara_diacritice_prinde_titlul_cu():
    assert is_excluded("Mașină de spălat", ["masina"]) is True


def test_exclude_nu_da_fals_pozitiv():
    assert is_excluded("Casti audio noi", ["mașină"]) is False


# ── OLX: data pe anunturi repromovate ────────────────────────────────────────────

def test_reactualizat_azi_are_data():
    dt = olx._parse_olx_date("Reactualizat azi la 10:30")
    assert dt is not None and dt.hour == 10 and dt.minute == 30


# ── OLX: parsarea cardului (moneda, oras cu cratima, conditie absenta) ───────────

_CARD_HTML = """
<html><body>
<div data-cy="l-card">
  <a href="/d/oferta/iphone-15-pro-IDabc12.html">
    <h6>iPhone 15 Pro ca nou</h6>
  </a>
  <p data-testid="ad-price">1 500 €</p>
  <p data-testid="location-date">Cluj-Napoca - Azi la 10:30</p>
  <img src="https://img.olx.ro/x.jpg">
</div>
</body></html>
"""


def _run_search_olx(monkeypatch, condition="all"):
    resp = types.SimpleNamespace(status_code=200, text=_CARD_HTML)
    monkeypatch.setattr(olx.curl_requests, "get", lambda url, **kw: resp)
    monkeypatch.setattr(olx.time, "sleep", lambda s: None)
    monkeypatch.setattr(olx, "_fetch_detail_image", lambda href: None)
    return olx.search_olx("iphone", max_price=None, condition=condition)


def test_olx_anunt_in_euro_salveaza_moneda_eur(monkeypatch):
    results = _run_search_olx(monkeypatch)
    assert len(results) == 1
    assert results[0]["price"] == 1500.0
    assert results[0]["currency"] == "EUR"


def test_olx_orasul_cu_cratima_ramane_intreg(monkeypatch):
    results = _run_search_olx(monkeypatch)
    assert results[0]["location"] == "Cluj-Napoca"
    assert results[0]["listed_at"] is not None      # data separata corect


def test_olx_conditia_absenta_pe_card_nu_arunca_rezultatul(monkeypatch):
    # Cardul nu are data-testid=ad-state; conditia e deja filtrata server-side.
    results = _run_search_olx(monkeypatch, condition="new")
    assert len(results) == 1


# ── Vinted: parametrul condition filtreaza local pe eticheta de stare ────────────

def _vinted_item(item_id, status):
    return {
        "id": item_id,
        "title": f"Geaca {item_id}",
        "price": {"amount": "100.0", "currency_code": "RON"},
        "status": status,
        "user": {"login": "u", "id": 1},
        "photo": {"url": "https://img/x.jpg"},
    }


def _run_search_vinted(monkeypatch, condition):
    items = [_vinted_item(1, "Nou, cu etichetă"),
             _vinted_item(2, "Foarte bun"),
             _vinted_item(3, "")]                     # fara status -> fail-open
    wrapper = types.SimpleNamespace(search=lambda params: {"items": items})
    monkeypatch.setattr(vs, "_get_wrapper", lambda: wrapper)
    monkeypatch.setattr(vs.log_manager, "emit", lambda *a, **k: None)
    return vs.search_vinted("geaca", max_price=None, condition=condition)


def test_vinted_condition_new_filtreaza_second_hand(monkeypatch):
    ids = {r["external_id"] for r in _run_search_vinted(monkeypatch, "new")}
    assert ids == {"vinted_1", "vinted_3"}            # nou + necunoscut (fail-open)


def test_vinted_condition_used_filtreaza_noul(monkeypatch):
    ids = {r["external_id"] for r in _run_search_vinted(monkeypatch, "used")}
    assert ids == {"vinted_2", "vinted_3"}


def test_vinted_condition_all_pastreaza_tot(monkeypatch):
    assert len(_run_search_vinted(monkeypatch, "all")) == 3


# ── Vinted: filtrul de pret maxim (gaura demonstrata de mutatia revizorului) ─────

def test_vinted_filtrul_de_pret_maxim(monkeypatch):
    items = [_vinted_item(1, ""), _vinted_item(2, "")]
    items[1]["price"] = {"amount": "999.0", "currency_code": "RON"}
    wrapper = types.SimpleNamespace(search=lambda params: {"items": items})
    monkeypatch.setattr(vs, "_get_wrapper", lambda: wrapper)
    monkeypatch.setattr(vs.log_manager, "emit", lambda *a, **k: None)
    out = vs.search_vinted("geaca", max_price=500)
    assert [r["external_id"] for r in out] == ["vinted_1"]


# ── Facebook: sesiunea invalida SEMNALIZEAZA (nu mai incearca re-auth) ───────────

def test_facebook_sesiune_invalida_semnalizeaza_fara_login_automat(monkeypatch):
    """REscris la R5. Testul de dinainte (`test_facebook_sesiune_invalida_incearca_reauth`)
    pinuia exact comportamentul ELIMINAT deliberat: un login headless automat cu
    FACEBOOK_EMAIL/FACEBOOK_PASSWORD, care atragea checkpoint pe cont si putea bloca
    si sesiunile MANUALE ulterioare. Invarianta utila ramane „sesiunea invalida nu
    trece tacut", asa ca o verificam pe noul semnal: WARN + BLOCKED, zero login-uri.
    """
    from app.services.radar import facebook_scraper as fb
    from app.services.radar.base_scraper import Outcome
    logs, blocked = [], []
    monkeypatch.setattr(fb, "is_facebook_session_valid", lambda p: False)
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda module, level, msg: logs.append((level, msg)))
    monkeypatch.setattr(fb, "report_outcome",
                        lambda platform, outcome: (blocked.append((platform, outcome)), False)[1])
    assert fb.search_facebook("test", max_price=None) == []
    assert [lvl for lvl, _ in logs] == ["WARN"]
    assert blocked == [("facebook", Outcome.BLOCKED)]
