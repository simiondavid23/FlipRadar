"""C-14 — anti-SSRF pe fetch_ean_from_url.

`source_url` vine liber din formularul userului si e cerut server-side de
_backfill_ean (BackgroundTask dupa create_product). Fara allow-list, un URL intern
face backend-ul sa scaneze reteaua interna in numele atacatorului (SSRF blind).
Teste pure de functie: nu ating reteaua si nu au nevoie de DB.
"""
import pytest

from app.services.scraper_service import _is_allowed_ean_url, fetch_ean_from_url


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
    assert _is_allowed_ean_url(url) is False


# Domeniile magazinelor, inclusiv subdomenii legitime.
@pytest.mark.parametrize("url", [
    "https://altex.ro/cpd/ABC/",
    "https://www.emag.ro/x",
    "https://comenzi.farmaciatei.ro/y",
    "https://sole.ro/z",
    "https://pcgarage.ro/w",
])
def test_url_magazin_e_acceptat(url):
    assert _is_allowed_ean_url(url) is True


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
        assert _is_allowed_ean_url(f"https://{domain}/produs") is True
