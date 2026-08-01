"""NET-5.1 — clasificatorul de blocaje din `base_scraper`.

Teste pure: fara retea, fara DB. Contractul testat nu e doar „ce intoarce", ci si
ORDINEA de decizie — un 429 cu markeri in body trebuie sa ramana RATE_LIMITED, altfel
am trata un rate-limit ca pe un ban si am reincerca gresit.

Ultimul test pazeste delegarea din `vinted_html._looks_blocked`: daca vreunul din cele
4 cazuri de acolo cade, clasificatorul e gresit, nu testul.
"""
from app.services.radar.base_scraper import Outcome, classify


def _pad(body: str, size: int) -> str:
    """Umple `body` pana la `size` cu 'x' (nu introduce markeri noi)."""
    return body + "x" * max(0, size - len(body))


_INTERSTITIAL = "<html><body>captcha-delivery</body></html>"


# ── cate un test per ramura din ordinea de decizie ───────────────────────────────

def test_exceptia_e_transient_si_bate_statusul():
    assert classify(exc=TimeoutError("boom")) is Outcome.TRANSIENT
    # Prima ramura: exceptia castiga chiar daca avem si un status „bun".
    assert classify(status=200, body="ok", exc=OSError("reset")) is Outcome.TRANSIENT
    # Statusuri care AR intoarce altceva decat OK — astea prind ordinea reala.
    # (Fara ele, mutarea ramurii `exc` la final trece nedetectata.)
    assert classify(status=404, body="Not found", exc=OSError("reset")) is Outcome.TRANSIENT
    assert classify(status=403, exc=OSError("reset")) is Outcome.TRANSIENT


def test_404_e_not_found():
    assert classify(status=404, body="Not found") is Outcome.NOT_FOUND


def test_401_si_403_sunt_blocked():
    assert classify(status=401) is Outcome.BLOCKED
    assert classify(status=403) is Outcome.BLOCKED


def test_429_e_rate_limited():
    assert classify(status=429) is Outcome.RATE_LIMITED


def test_5xx_e_transient():
    assert classify(status=500) is Outcome.TRANSIENT
    assert classify(status=503) is Outcome.TRANSIENT


def test_200_curat_e_ok():
    assert classify(status=200, body="<html>rezultate</html>") is Outcome.OK


def test_200_cu_interstitial_mic_e_blocked():
    assert classify(status=200, body=_INTERSTITIAL) is Outcome.BLOCKED


def test_200_parsed_zero_e_site_changed():
    assert classify(status=200, body="<html>ok</html>", parsed=0) is Outcome.SITE_CHANGED


# ── ordinea de decizie ───────────────────────────────────────────────────────────

def test_ordine_429_cu_markeri_ramane_rate_limited():
    # Un rate-limit servit cu pagina de challenge NU e ban: backoff, nu rotatie.
    assert classify(status=429, body=_INTERSTITIAL) is Outcome.RATE_LIMITED


def test_ordine_403_e_blocked_indiferent_de_body():
    assert classify(status=403, body="<html>continut absolut normal</html>") is Outcome.BLOCKED
    assert classify(status=403, body="") is Outcome.BLOCKED


def test_ordine_blocajul_bate_site_changed():
    # Interstitialul parseaza 0 carduri; diagnosticul corect e BLOCKED, nu SITE_CHANGED.
    assert classify(status=200, body=_INTERSTITIAL, parsed=0) is Outcome.BLOCKED


def test_parsed_none_nu_e_site_changed():
    # None = „nu s-a parsat inca", nu zero.
    assert classify(status=200, body="<html>ok</html>", parsed=None) is Outcome.OK


# ── pragul de dimensiune si markerii ─────────────────────────────────────────────

def test_prag_dimensiune_acelasi_body_sub_si_peste():
    mic = _pad(_INTERSTITIAL, 1_000)
    mare = _pad(_INTERSTITIAL, 45_000)
    assert classify(status=200, body=mic) is Outcome.BLOCKED
    assert classify(status=200, body=mare) is Outcome.OK
    # Pragul e parametru, nu constanta ascunsa.
    assert classify(status=200, body=mare, interstitial_max_bytes=50_000) is Outcome.BLOCKED


def test_datadome_singur_nu_e_marker():
    # SDK-ul client DataDome apare si pe pagina buna — singur nu dovedeste nimic.
    assert classify(status=200, body="<script src='js.datadome.co/tags.js'></script>") is Outcome.OK
    assert classify(status=200, body="datadome ... please solve the captcha") is Outcome.BLOCKED


def test_just_a_moment_e_ancorat_pe_titlu():
    # Singura expresie englezeasca obisnuita din lista: intr-o descriere de vanzator ar
    # clasifica pagina BLOCKED si, pe Vinted, ar arma breaker-ul de 6 ore.
    proza = "<html><body>Trimit coletul just a moment dupa plata, promit!</body></html>"
    assert classify(status=200, body=proza) is Outcome.OK
    cloudflare = "<html><head><title>Just a moment...</title></head><body></body></html>"
    assert classify(status=200, body=cloudflare) is Outcome.BLOCKED


def test_extra_markers_se_adauga_nu_inlocuiesc():
    body = "<html>acces restrictionat temporar</html>"
    assert classify(status=200, body=body) is Outcome.OK
    assert classify(status=200, body=body,
                    extra_markers=("acces restrictionat",)) is Outcome.BLOCKED
    # Markerii comuni raman activi cand se dau si extra.
    assert classify(status=200, body="<html>imperva</html>",
                    extra_markers=("altceva",)) is Outcome.BLOCKED


# ── delegarea din vinted_html (contract de non-regresie) ─────────────────────────

def test_delegarea_vinted_looks_blocked_pastreaza_cele_4_cazuri():
    from app.services.radar.vinted_html import _looks_blocked

    assert _looks_blocked(403, "orice") is True
    assert _looks_blocked(200, _pad("<html>datadome</html>", 45_000)) is False
    assert _looks_blocked(200, _INTERSTITIAL) is True
    # Cel mai fragil: 404 curat NU e blocaj. Daca cade, calea RAD-1 (item sters) se
    # rupe si listingurile sterse se reincearca la nesfarsit, arzand plafonul zilnic.
    assert _looks_blocked(404, "<html><body>Not found</body></html>") is False


def test_mesajul_breakerului_nu_mai_hardcodeaza_403(monkeypatch):
    """NET-5.2b — de cand `classify` numara si 401 si 200-cu-marker drept blocaj,
    un breaker deschis de doua 401-uri raportand „403 consecutive" ar trimite pe cineva
    sa caute in jurnale un cod care nu apare niciodata acolo."""
    import app.services.radar.vinted_html as vh

    vh._breaker.clear()
    emis = []
    monkeypatch.setattr(vh.log_manager, "emit",
                        lambda modul, nivel, mesaj, *a, **k: emis.append(mesaj))
    for _ in range(2):
        vh.guard_after_response("vinted.ro", blocked=True, status=401)
    deschis = [m for m in emis if "breaker DESCHIS" in m]
    assert len(deschis) == 1
    assert "401" in deschis[0] and "403" not in deschis[0]
    vh._breaker.clear()
