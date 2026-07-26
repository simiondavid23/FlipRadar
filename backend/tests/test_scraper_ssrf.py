"""C-14 / C-14b — anti-SSRF pe fetch_ean_from_url.

`source_url` vine liber din formularul userului si e cerut server-side de
_backfill_ean (BackgroundTask dupa create_product). Fara allow-list, un URL intern
face backend-ul sa scaneze reteaua interna in numele atacatorului (SSRF blind).
C-14 valideaza URL-ul initial; C-14b valideaza si fiecare hop de redirect, fiindca
un open-redirect pe un magazin permis ar sari peste allow-list.
Teste pure de functie: nu ating reteaua si nu au nevoie de DB.
"""
import pytest

from app.services.scraper_service import _is_allowed_shop_url, fetch_ean_from_url


class _FakeResponse:
    """Raspuns minimal: doar ce citeste fetch_ean_from_url."""

    def __init__(self, status_code=200, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


def _fake_get(responses, recorder):
    """Fals pentru curl_requests.get: intoarce raspunsul programat per URL si
    inregistreaza fiecare URL cerut. Un URL neprogramat = request pe care nu-l
    astepta nimeni -> il inregistram si intoarcem 404 (testul verifica recorderul)."""
    def _get(url, *args, **kwargs):
        recorder.append(url)
        return responses.get(url, _FakeResponse(status_code=404))
    return _get


_JSONLD_EAN = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"Product","gtin13":"5901234123457"}'
    "</script></head><body></body></html>"
)


# URL-uri care trebuie respinse: metadata cloud, loopback, scheme non-http,
# si sufixe inselatoare care contin un domeniu permis fara sa fie el.
@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # metadata cloud (AWS/GCP)
    "http://localhost:8000/x",
    "http://127.0.0.1/x",
    "http://[::1]/x",
    "file:///etc/passwd",                          # schema non-http
    "http://evil-altex.ro.attacker.com/x",         # sufix inselator
    "http://attacker.com/altex.ro",                # domeniu permis doar in path
    "",
    "not a url",
])
def test_url_neautorizat_e_respins(url):
    assert _is_allowed_shop_url(url) is False


# Domeniile magazinelor, inclusiv subdomenii legitime.
@pytest.mark.parametrize("url", [
    "https://altex.ro/cpd/ABC/",
    "https://www.emag.ro/x",
    "https://comenzi.farmaciatei.ro/y",
    "https://sole.ro/z",
    "https://pcgarage.ro/w",
])
def test_url_magazin_e_acceptat(url):
    assert _is_allowed_shop_url(url) is True


def test_fetch_ean_nu_face_request_pe_url_neautorizat(monkeypatch):
    """Respingerea trebuie sa fie INAINTE de request — la SSRF blind, request-ul
    in sine e dauna, deci nu e destul ca raspunsul sa fie ignorat.

    Atentie: NU verificam asta aruncand din fals-ul de `get`. fetch_ean_from_url
    are `except Exception: pass`, iar AssertionError e subclasa de Exception —
    exceptia ar fi inghitita, functia ar intoarce None si testul ar trece si FARA
    fix. Inregistram apelurile si verificam lista in corpul testului, unde
    try/except-ul functiei nu ajunge.
    """
    calls = []

    def _record(url, *args, **kwargs):
        calls.append(url)
        raise AssertionError("nu trebuie chemat")

    monkeypatch.setattr("app.services.scraper_service.curl_requests.get", _record)

    assert fetch_ean_from_url("http://localhost/x") is None
    assert fetch_ean_from_url("http://169.254.169.254/latest/meta-data/") is None
    assert calls == [], f"S-a facut request server-side pe URL neautorizat: {calls}"


def test_allow_list_e_derivata_din_scrapere():
    """Allow-list-ul si scraperele trebuie sa ramana o singura sursa de adevar:
    un magazin nou in _SCRAPERS_BY_SOURCE devine automat permis, fara a doua lista."""
    from app.services.scraper_service import _SCRAPERS_BY_SOURCE

    for domain in _SCRAPERS_BY_SOURCE:
        assert _is_allowed_shop_url(f"https://{domain}/produs") is True


# ── C-14b: validarea per-hop a redirecturilor ────────────────────────────────────
def test_redirect_catre_url_intern_oprit(monkeypatch):
    """Open-redirect pe un magazin permis nu trebuie sa duca la un request intern.
    Recorderul e verificat in corpul testului: fetch_ean_from_url inghite exceptiile
    (except Exception: pass), deci un assert aruncat din fals ar fi mascat."""
    calls = []
    responses = {
        "https://www.emag.ro/x": _FakeResponse(
            status_code=302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
        ),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_ean_from_url("https://www.emag.ro/x") is None
    assert calls == ["https://www.emag.ro/x"], (
        f"Redirectul intern a fost urmat server-side: {calls}"
    )


def test_redirect_legitim_urmarit(monkeypatch):
    """Un redirect intre URL-uri permise trebuie sa functioneze in continuare."""
    calls = []
    responses = {
        "https://www.emag.ro/x": _FakeResponse(
            status_code=301, headers={"Location": "https://www.emag.ro/produs-final"}
        ),
        "https://www.emag.ro/produs-final": _FakeResponse(status_code=200, text=_JSONLD_EAN),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_ean_from_url("https://www.emag.ro/x") == "5901234123457"
    assert calls == ["https://www.emag.ro/x", "https://www.emag.ro/produs-final"]


def test_prea_multe_redirecturi(monkeypatch):
    """Lant lung intre URL-uri permise: se opreste, fara bucla infinita."""
    calls = []
    responses = {
        f"https://www.emag.ro/r{i}": _FakeResponse(
            status_code=302, headers={"location": f"https://www.emag.ro/r{i + 1}"}
        )
        for i in range(10)
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_ean_from_url("https://www.emag.ro/r0") is None
    assert len(calls) == 4, f"Trebuie exact 4 hop-uri (1 initial + 3), au fost: {calls}"


def test_location_relativ(monkeypatch):
    """Location relativ se rezolva fata de URL-ul curent (urljoin), nu se ignora."""
    calls = []
    responses = {
        "https://www.emag.ro/x": _FakeResponse(
            status_code=302, headers={"location": "/produs-x"}
        ),
        "https://www.emag.ro/produs-x": _FakeResponse(status_code=200, text=_JSONLD_EAN),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_ean_from_url("https://www.emag.ro/x") == "5901234123457"
    assert calls == ["https://www.emag.ro/x", "https://www.emag.ro/produs-x"]


def test_redirect_relativ_nu_poate_evada_domeniul(monkeypatch):
    """Un Location absolut cu schema non-http (ex. file://) nu trebuie urmat."""
    calls = []
    responses = {
        "https://www.emag.ro/x": _FakeResponse(
            status_code=307, headers={"location": "file:///etc/passwd"}
        ),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_ean_from_url("https://www.emag.ro/x") is None
    assert calls == ["https://www.emag.ro/x"]


# ── C-14c: aceeasi garda pe refresh-ul de pret PCGarage ──────────────────────────
# source_url vine tot din produsul creat de user (refresh_price_from_source), iar
# lantul e declansat si automat din scheduler (alert_checker) — deci SSRF-ul era
# direct, fara sa fie nevoie macar de un open-redirect.
def test_pcgarage_url_intern_respins(monkeypatch):
    """URL interzis: zero request-uri si fara consum de retry-uri (fail-fast)."""
    from app.services.scraper_service import fetch_pcgarage_price_from_url

    calls = []
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get({}, calls))
    # Daca fail-fast-ul n-ar exista, cele 3 retry-uri ar dormi 1-3s fiecare.
    monkeypatch.setattr("app.services.scraper_service.time.sleep", lambda *_: None)

    assert fetch_pcgarage_price_from_url("http://169.254.169.254/x") is None
    assert calls == [], f"S-a facut request server-side pe URL interzis: {calls}"


def test_pcgarage_redirect_intern_oprit(monkeypatch):
    """Open-redirect de pe pcgarage.ro catre loopback: hop-ul nu e urmat."""
    from app.services.scraper_service import fetch_pcgarage_price_from_url

    calls = []
    responses = {
        "https://www.pcgarage.ro/produs": _FakeResponse(
            status_code=302, headers={"location": "http://127.0.0.1/"}
        ),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))
    monkeypatch.setattr("app.services.scraper_service.time.sleep", lambda *_: None)

    assert fetch_pcgarage_price_from_url("https://www.pcgarage.ro/produs") is None
    assert "http://127.0.0.1/" not in calls, f"Redirect intern urmat: {calls}"


def test_pcgarage_legitim(monkeypatch):
    """Fluxul normal nu se schimba: 200 + selector de pret -> float."""
    from app.services.scraper_service import fetch_pcgarage_price_from_url

    calls = []
    responses = {
        "https://www.pcgarage.ro/produs": _FakeResponse(
            status_code=200,
            text='<html><body><span class="price_num">1.234,56 RON</span></body></html>',
        ),
    }
    monkeypatch.setattr("app.services.scraper_service.curl_requests.get",
                        _fake_get(responses, calls))

    assert fetch_pcgarage_price_from_url("https://www.pcgarage.ro/produs") == 1234.56
    assert calls == ["https://www.pcgarage.ro/produs"]


# ── RETAIL-5: allow-list-ul e uniunea scraperelor cu domeniile validate ────────

def test_domeniu_doar_din_validated_domains_e_acceptat(monkeypatch):
    """Un magazin monitorizabil prin link, dar FARA scraper de cautare, trebuie
    sa treaca de C-14 — altfel extract_product l-ar respinge pe propriul domeniu."""
    import app.services.scraper_service as ss

    assert "magazin-nou.ro" not in ss._SCRAPERS_BY_SOURCE
    assert _is_allowed_shop_url("https://magazin-nou.ro/p/1") is False  # inainte

    monkeypatch.setattr(ss, "VALIDATED_DOMAINS", ss.VALIDATED_DOMAINS | {"magazin-nou.ro"})

    assert _is_allowed_shop_url("https://magazin-nou.ro/p/1") is True


def test_subdomeniul_unui_domeniu_validat_e_acceptat(monkeypatch):
    import app.services.scraper_service as ss

    monkeypatch.setattr(ss, "VALIDATED_DOMAINS", ss.VALIDATED_DOMAINS | {"magazin-nou.ro"})

    assert _is_allowed_shop_url("https://shop.magazin-nou.ro/p/1") is True
    # ...dar sufixul inselator ramane respins (aceeasi regula ca la scrapere).
    assert _is_allowed_shop_url("https://magazin-nou.ro.attacker.com/p/1") is False


def test_domeniu_absent_din_ambele_multimi_ramane_respins(monkeypatch):
    """Regresie: extinderea allow-list-ului nu deschide poarta pentru altcineva."""
    import app.services.scraper_service as ss

    monkeypatch.setattr(ss, "VALIDATED_DOMAINS", ss.VALIDATED_DOMAINS | {"magazin-nou.ro"})

    assert _is_allowed_shop_url("https://alt-magazin.ro/p/1") is False
    assert _is_allowed_shop_url("http://169.254.169.254/latest/meta-data/") is False
    assert _is_allowed_shop_url("http://localhost:8000/api/products/") is False
