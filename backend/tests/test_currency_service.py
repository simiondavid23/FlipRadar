"""CUR-1 — lantul de rezerva al conversiei valutare.

Toate testele sunt OFFLINE: `_fetch_bnr_rates` e monkeypatch-uit sa esueze, iar
starea se pune direct in `_CACHE` / `_CACHE_TIMESTAMP`. Fixture-ul le salveaza si
le restaureaza, fiindca sunt globale de modul — o scurgere ar contamina orice alt
test care converteste sume.

Ordinea pinuita aici: cache proaspat > fetch BNR > cache EXPIRAT > fallback static
> 1.0. Pasul care lipsea si care conta e cache-ul expirat.
"""
import pytest

from app.services import currency_service as cs


@pytest.fixture
def cache_curat(monkeypatch):
    """Cache golit si fetch BNR picat; starea initiala se pune la loc la final."""
    cache_vechi = dict(cs._CACHE)
    timestamp_vechi = dict(cs._CACHE_TIMESTAMP)
    cs._CACHE.clear()
    cs._CACHE_TIMESTAMP.clear()
    monkeypatch.setattr(cs, "_fetch_bnr_rates", lambda: None)
    yield
    cs._CACHE.clear()
    cs._CACHE.update(cache_vechi)
    cs._CACHE_TIMESTAMP.clear()
    cs._CACHE_TIMESTAMP.update(timestamp_vechi)


def test_cache_expirat_bate_fallback_static(cache_curat):
    # O rata reala, veche de o zi, e mai buna decat orice constanta din cod.
    cs._CACHE["SEK"] = 0.4712
    cs._CACHE_TIMESTAMP["SEK"] = 0.0  # epoca -> expirat cu mult peste TTL

    assert cs._get_rate("SEK") == 0.4712


def test_sek_fallback_static_la_pornire_rece(cache_curat):
    # Fara nimic in memorie si cu BNR picat, SEK cade pe fallback-ul static.
    # Inainte de CUR-1 ajungea la 1.0, adica un pret SEK trecea nealterat in RON
    # (umflat ~2,1x) — exact bugul tacut gasit la sonda SHOP-1a pe caliroots.
    assert cs._get_rate("SEK") == cs._FALLBACK_SEK_RON == 0.44


def test_moneda_necunoscuta_ramane_1_la_1(cache_curat):
    # Semantica pastrata DELIBERAT pentru restul aplicatiei: o moneda pe care n-o
    # cunoastem trece 1:1, nu arunca.
    assert cs._get_rate("XYZ") == 1.0
