"""CUR-1 — orice monedă din catalogul BNR se convertește; codurile din afara lui NU.

DE CE EXISTĂ: primul ciclu Facebook pe sesiune (2026-09-05) a raportat
`2 anunturi au trecut de filtrele de pret fara verificare` — două anunțuri au sărit
porțile de preț fiindcă moneda lor nu era EUR/USD, deși `currency_service` avea deja
tot catalogul BNR (~30 de coduri) în cache. Scorarea era și mai rea: 800 GBP intra în
`calculate_score` ca 800 RON, adică marjă falsă și grad fals.

Distincția pe care o apără fișierul: `_get_rate` are voie să spună „1:1" pentru un cod
necunoscut (`convert` preferă o sumă nealterată unei excepții), dar porțile de preț și
scorarea NU au voie — de aceea există `get_rate_strict`, care întoarce None.

Fără rețea: `_fetch_cu_backoff` și `_disk_rates` sunt monkeypatch-uite în fiecare test,
iar cache-ul se golește înainte și după (e stare de modul, partajată cu restul suitei).
"""
from datetime import datetime, timezone

import pytest

from app.services import currency_service as cs
from app.services.radar import base_scraper as bs
from app.utils import radar_scanner as rs


_CATALOG = {"EUR": 5.0, "USD": 4.5, "GBP": 6.0, "MDL": 0.26}


@pytest.fixture
def catalog(monkeypatch):
    """Catalog BNR simulat, servit din cache-ul de memorie. Zero rețea, zero disc."""
    monkeypatch.setattr(cs, "_fetch_cu_backoff", lambda now: dict(_CATALOG))
    monkeypatch.setattr(cs, "_disk_rates", lambda: {})
    cs._CACHE.clear()
    cs._CACHE_TIMESTAMP.clear()
    yield _CATALOG
    cs._CACHE.clear()
    cs._CACHE_TIMESTAMP.clear()


@pytest.fixture
def fara_surse(monkeypatch):
    """Toate sursele mute: fetch picat, disc gol, cache gol."""
    monkeypatch.setattr(cs, "_fetch_cu_backoff", lambda now: None)
    monkeypatch.setattr(cs, "_disk_rates", lambda: {})
    cs._CACHE.clear()
    cs._CACHE_TIMESTAMP.clear()
    yield
    cs._CACHE.clear()
    cs._CACHE_TIMESTAMP.clear()


# ── 1. get_rate_strict: din surse reale sau None, niciodată 1.0 ──────────────────
def test_get_rate_strict_gaseste_orice_cod_din_catalog(catalog):
    assert cs.get_rate_strict("GBP") == 6.0
    assert cs.get_rate_strict("MDL") == 0.26
    assert cs.get_rate_strict("RON") == 1.0
    assert cs.get_rate_strict("gbp ") == 6.0          # normalizare


def test_get_rate_strict_da_none_pe_cod_din_afara_catalogului(catalog):
    """`XXX` e codul ISO 4217 pentru „fără monedă", deci garantat absent din BNR —
    de-asta e ales aici, nu GBP (care de la CUR-1 CHIAR e în catalog)."""
    assert cs.get_rate_strict("XXX") is None
    assert cs.get_rate_strict("") is None
    assert cs.get_rate_strict(None) is None


def test_get_rate_strict_da_none_si_cand_nicio_sursa_nu_raspunde(fara_surse):
    assert cs.get_rate_strict("EUR") is None          # nici fallback static


# ── 2. contractul vechi al lui _get_rate rămâne neatins (convert depinde de el) ──
def test_get_rate_ramane_1_la_1_pe_cod_necunoscut(catalog):
    assert cs._get_rate("XXX") == 1.0
    assert cs._get_rate("GBP") == 6.0
    assert cs._get_rate("RON") == 1.0


# ── 3. catalog_ron ──────────────────────────────────────────────────────────────
def test_catalog_ron_intoarce_tot_catalogul_plus_ron(catalog):
    c = cs.catalog_ron()
    assert c["RON"] == 1.0
    assert c["GBP"] == 6.0 and c["EUR"] == 5.0
    assert "XXX" not in c


def test_catalog_ron_gol_cand_nicio_sursa_nu_raspunde(fara_surse):
    assert cs.catalog_ron() == {"RON": 1.0}


# ── 4. porțile de preț (base_scraper) ───────────────────────────────────────────
def test_portile_convertesc_orice_cod_din_catalog(catalog):
    assert bs.pret_comparabil_ron(800, "GBP") == 4800.0
    assert bs.pret_comparabil_ron(800, "gbp ") == 4800.0
    assert bs.pret_comparabil_ron(800, "XXX") is None          # D2
    assert bs.pret_comparabil_ron(1000, "RON") == 1000.0       # identitate


def test_moneda_convertibila_urmeaza_catalogul(catalog):
    assert bs.moneda_convertibila("RON") is True
    assert bs.moneda_convertibila("GBP") is True                # CUR-1
    assert bs.moneda_convertibila("MDL") is True
    assert bs.moneda_convertibila("XXX") is False


def test_eur_usd_raman_pe_adaptorul_lor(monkeypatch, catalog):
    """Ruta hibridă: EUR/USD trec mai departe prin `bnr_exchange`, ca D3 (curs picat)
    să rămână DISTINCT de D2 (cod necunoscut) și ca pinuirea cursului din testele
    existente să continue să prindă."""
    from app.services import bnr_exchange
    monkeypatch.setattr(bnr_exchange, "get_eur_ron", lambda: 7.0)
    assert bs.pret_comparabil_ron(100, "EUR") == 700.0          # 7.0, nu 5.0 din catalog

    def explodeaza():
        raise RuntimeError("BNR indisponibil")

    monkeypatch.setattr(bnr_exchange, "get_eur_ron", explodeaza)
    assert bs.pret_comparabil_ron(100, "EUR") is None           # D3
    assert bs.moneda_convertibila("EUR") is True                # ...dar tot o știm


# ── 5. scorarea (_price_to_ron) — pură, catalogul se pasează ────────────────────
def test_scorarea_converteste_din_catalog():
    assert rs._price_to_ron(800, "GBP", 5.0, 4.5, cursuri={"GBP": 6.0}) == 4800.0


def test_scorarea_cade_pe_eur_usd_cand_catalogul_lipseste(monkeypatch):
    """Fără catalog, comportamentul e EXACT cel dinainte de CUR-1 — inclusiv WARN-ul."""
    linii = []
    monkeypatch.setattr(rs.log_manager, "emit",
                        lambda m, n, msg: linii.append((n, msg)))
    rs._unknown_currency_warned.clear()

    assert rs._price_to_ron(800, "GBP", 5.0, 4.5) == 800.0
    assert rs._price_to_ron(800, "EUR", 5.0) == 4000.0          # fallback-ul neatins
    assert any("GBP" in m for niv, m in linii if niv == "WARN"), linii


def test_scorarea_avertizeaza_cu_textul_de_catalog_pe_cod_necunoscut(monkeypatch):
    linii = []
    monkeypatch.setattr(rs.log_manager, "emit",
                        lambda m, n, msg: linii.append((n, msg)))
    rs._unknown_currency_warned.clear()

    assert rs._price_to_ron(800, "XXX", 5.0, cursuri={"GBP": 6.0}) == 800.0
    warn = [m for niv, m in linii if niv == "WARN"]
    assert any("nu e în catalogul BNR" in m and "XXX" in m for m in warn), warn


# ── 6. Facebook: linia INFO numește codurile ────────────────────────────────────
def test_info_facebook_enumera_codurile_necunoscute(monkeypatch):
    """Două anunțuri, două monede pe care porțile nu le pot converti — linia INFO
    trebuie să spună CARE sunt, altfel diagnosticul cere o sesiune de depanare.

    Se apelează direct `_din_canonice`: acolo stă contorul, iar funcția e ACEEAȘI
    pentru calea logat-out și pentru cea de bazin (extrasă la FBS-5), deci un singur
    apel acoperă ambele. Porțile sunt pinuite ca să nu depindem de catalogul real.
    """
    from app.services.radar import facebook_scraper as fb

    monkeypatch.setattr(fb, "pret_comparabil_ron", lambda pret, moneda: None)
    monkeypatch.setattr(fb, "moneda_convertibila", lambda moneda: False)

    linii = []
    monkeypatch.setattr(fb.log_manager, "emit",
                        lambda m, n, msg: linii.append((n, msg)))

    def _canonic(ext_id, moneda):
        return {"external_id": ext_id, "title": "Geaca de piele", "price": 200.0,
                "currency": moneda, "location": "București", "image_url": None,
                "listed_at": datetime(2026, 8, 15, 6, 30, tzinfo=timezone.utc),
                "category_id": None,
                "source_url": f"https://www.facebook.com/marketplace/item/{ext_id}/"}

    canonice = [_canonic("1", "MDL"), _canonic("2", "GBP")]
    rez = fb._din_canonice(canonice, "geaca", 10, [], None, None)

    assert len(rez) == 2, "D2 — permisiv: anunturile trec, doar se numara"
    info = [m for niv, m in linii if niv == "INFO"]
    assert any("nu se poate aduce in RON (GBP, MDL)" in m for m in info), info
