"""CUR-1 + BNR-1 — lantul de rezerva si persistenta cursului valutar.

Toate testele sunt OFFLINE: fie `_fetch_bnr_rates` e monkeypatch-uit, fie stratul
curl_cffi din modul. `DATA_DIR` e mutat pe `tmp_path`, deci niciun test nu atinge
fisierul real de cache.

Ordinea pinuita aici (BNR-1 a inserat treapta de disc intre cache si constante):
  (a) cache proaspat > (b) fetch BNR > (c) cache EXPIRAT > (d) disc > (e) static > 1.0

Starea de modul (cache, backoff, cache-ul de pe disc, timestamp-urile de WARN) e
GLOBALA — fixture-ul o goleste si o pune la loc, altfel testele s-ar contamina intre
ele si ar contamina orice alt test care converteste sume.
"""
from datetime import date, timedelta
import json

import pytest

from app.services import bnr_exchange
from app.services import currency_service as cs


# XML-ul BNR real, redus: namespace-ul oficial, EUR fara multiplier, HUF cu
# multiplier="100" si un nod gol (feed-ul chiar contine astfel de noduri).
XML_BNR = """<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="http://www.bnr.ro/xsd">
  <Header><Publisher>National Bank of Romania</Publisher></Header>
  <Body>
    <Subject>Reference rates</Subject>
    <OrigCurrency>RON</OrigCurrency>
    <Cube date="2026-08-13">
      <Rate currency="EUR">5.2435</Rate>
      <Rate currency="USD">4.5612</Rate>
      <Rate currency="HUF" multiplier="100">1.2882</Rate>
      <Rate currency="XDR"></Rate>
    </Cube>
  </Body>
</DataSet>
"""


class _Raspuns:
    """Raspuns curl_cffi minimal (doar ce citeste `_fetch_bnr_rates`)."""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


@pytest.fixture
def stare_curata(monkeypatch, tmp_path):
    """Modul resetat complet + DATA_DIR pe tmp_path; starea initiala se pune la loc."""
    salvate = {
        "_CACHE": dict(cs._CACHE),
        "_CACHE_TIMESTAMP": dict(cs._CACHE_TIMESTAMP),
        "_DISK_CACHE": dict(cs._DISK_CACHE),
        "_WARN_TIMESTAMPS": dict(cs._WARN_TIMESTAMPS),
    }
    for d in (cs._CACHE, cs._CACHE_TIMESTAMP, cs._DISK_CACHE, cs._WARN_TIMESTAMPS):
        d.clear()
    # Scalarii merg prin monkeypatch (restaurare automata la teardown).
    monkeypatch.setattr(cs, "_LAST_FETCH_FAILURE", 0.0)
    monkeypatch.setattr(cs, "_DISK_LOADED", False)
    monkeypatch.setattr(cs, "_DISK_AGE_DAYS", None)
    monkeypatch.setattr(cs, "DATA_DIR", tmp_path)

    yield tmp_path

    for nume, continut in salvate.items():
        d = getattr(cs, nume)
        d.clear()
        d.update(continut)


@pytest.fixture
def fetch_picat(stare_curata, monkeypatch):
    """BNR inaccesibil. Returneaza lista de apeluri, ca sa se poata numara."""
    apeluri = []

    def _esueaza():
        apeluri.append(1)
        return None

    monkeypatch.setattr(cs, "_fetch_bnr_rates", _esueaza)
    return apeluri


def _scrie_cache_pe_disc(dosar, rates, varsta_zile):
    """Fabrica un curs_bnr.json de o anumita vechime."""
    (dosar / "curs_bnr.json").write_text(
        json.dumps({
            "fetched_at": (date.today() - timedelta(days=varsta_zile)).isoformat(),
            "rates": rates,
        }),
        encoding="utf-8",
    )


# ── 1. Parserul ─────────────────────────────────────────────────────────────────

def test_parserul_respecta_namespace_ul_si_multiplierul():
    """Parserul ET (mutat din bnr_exchange) inlocuieste regexul: namespace-agnostic,
    respecta `multiplier` si sare peste nodurile fara text."""
    rates = cs._parse(XML_BNR)

    assert rates["EUR"] == pytest.approx(5.2435)          # fara multiplier
    assert rates["HUF"] == pytest.approx(0.012882)        # multiplier="100"
    assert rates["USD"] == pytest.approx(4.5612)
    assert "XDR" not in rates                             # nod gol, ignorat


# ── 2. Fetch reusit -> persistenta pe disc ──────────────────────────────────────

def test_fetch_reusit_persista_cursul_pe_disc(stare_curata, monkeypatch):
    monkeypatch.setattr(cs.curl_requests, "get", lambda url, **kw: _Raspuns(XML_BNR))

    assert cs.get_eur_ron_rate() == pytest.approx(5.2435)

    pe_disc = json.loads((stare_curata / "curs_bnr.json").read_text(encoding="utf-8"))
    assert pe_disc["fetched_at"] == date.today().isoformat()
    assert pe_disc["rates"]["EUR"] == pytest.approx(5.2435)
    assert pe_disc["rates"]["HUF"] == pytest.approx(0.012882)  # toate cele parsate, nu doar EUR


def test_fetch_ul_foloseste_subdomeniul_nou_si_profilul_central(stare_curata, monkeypatch):
    """Regresia care a impus BNR-1: www.bnr.ro raspunde 200 cu HTML, deci parsarea
    esua tacut. Adresa e pinuita aici ca sa nu se mai poata intoarce pe furis."""
    from app.utils.http_profile import impersonate_for

    apeluri = []

    def _get(url, **kw):
        apeluri.append((url, kw))
        return _Raspuns(XML_BNR)

    monkeypatch.setattr(cs.curl_requests, "get", _get)
    cs.get_eur_ron_rate()

    url, kw = apeluri[0]
    assert url == "https://curs.bnr.ro/nbrfxrates.xml"
    assert kw["impersonate"] == impersonate_for("bnr")


# ── 3-4. Treapta de disc ────────────────────────────────────────────────────────

def test_pornire_rece_ia_cursul_de_pe_disc_si_avertizeaza(fetch_picat, stare_curata, capsys):
    """Proces nou + BNR picat, dar cursul de ieri e pe disc: NU se cade pe constanta.
    Si nu se intampla tacut — tacerea a fost exact bugul mutarii feed-ului."""
    _scrie_cache_pe_disc(stare_curata, {"EUR": 5.1987}, varsta_zile=1)

    assert cs.get_eur_ron_rate() == pytest.approx(5.1987)

    out = capsys.readouterr().out
    assert "[CURS]" in out
    assert "disc" in out


def test_discul_prea_vechi_e_ignorat_si_varsta_e_spusa(fetch_picat, stare_curata, capsys,
                                                       monkeypatch):
    """Peste pragul CUR_MAX_STALE_DAYS cursul de pe disc nu mai e informatie, e zgomot."""
    monkeypatch.setenv("CUR_MAX_STALE_DAYS", "7")
    _scrie_cache_pe_disc(stare_curata, {"EUR": 4.9012}, varsta_zile=10)

    assert cs.get_eur_ron_rate() == cs._FALLBACK_EUR_RON == 5.24

    out = capsys.readouterr().out
    assert "[CURS]" in out
    assert "10 zile" in out


# ── 5. Backoff ──────────────────────────────────────────────────────────────────

def test_backoff_nu_reincearca_fetch_ul_imediat(fetch_picat):
    """`get_eur_ron_rate` e apelat PER ANUNT in scorare: fara backoff, un BNR cazut ar
    lipi un timeout de 10s de fiecare anunt."""
    cs.get_eur_ron_rate()
    assert len(fetch_picat) == 1

    cs.get_eur_ron_rate()
    cs.get_eur_ron_rate()
    assert len(fetch_picat) == 1, "fetch-ul s-a reincercat inauntrul ferestrei de backoff"


# ── 6. Adaptorul ────────────────────────────────────────────────────────────────

def test_bnr_exchange_deleaga_catre_implementarea_unica(monkeypatch):
    """BNR-1: bnr_exchange nu mai are fetch/parser/cache propriu. Numele si tipul de
    retur raman, ca cele 11 situri de apel din Radar/Auto/Imobiliare sa nu se atinga."""
    monkeypatch.setattr(cs, "get_eur_ron_rate", lambda: 7.77)

    assert bnr_exchange.get_eur_ron() == 7.77
    # Al doilea fetch+cache paralel a disparut cu totul.
    assert not hasattr(bnr_exchange, "_fetch")
    assert not hasattr(bnr_exchange, "_BNR_URL")


def test_adaptorul_da_exact_valoarea_din_lantul_unic(stare_curata, monkeypatch):
    """Nu doar acelasi tip — aceeasi valoare, prin lantul real."""
    monkeypatch.setattr(cs, "_fetch_bnr_rates", lambda: {"EUR": 5.31})

    assert bnr_exchange.get_eur_ron() == cs.get_eur_ron_rate() == 5.31


# ── 7. Testele CUR-1, pastrate ──────────────────────────────────────────────────

def test_cache_expirat_bate_fallback_static(fetch_picat):
    # O rata reala, veche de o zi, e mai buna decat orice constanta din cod.
    cs._CACHE["SEK"] = 0.4712
    cs._CACHE_TIMESTAMP["SEK"] = 0.0  # epoca -> expirat cu mult peste TTL

    assert cs._get_rate("SEK") == 0.4712


def test_sek_fallback_static_la_pornire_rece(fetch_picat):
    # Fara nimic in memorie, fara nimic pe disc si cu BNR picat, SEK cade pe fallback-ul
    # static. Inainte de CUR-1 ajungea la 1.0, adica un pret SEK trecea nealterat in RON
    # (umflat ~2,1x) — exact bugul tacut gasit la sonda SHOP-1a pe caliroots.
    assert cs._get_rate("SEK") == cs._FALLBACK_SEK_RON == 0.44


def test_moneda_necunoscuta_ramane_1_la_1(fetch_picat):
    # Semantica pastrata DELIBERAT pentru restul aplicatiei: o moneda pe care n-o
    # cunoastem trece 1:1, nu arunca.
    assert cs._get_rate("XYZ") == 1.0
