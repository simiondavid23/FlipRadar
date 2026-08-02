"""NET-5.3b — cablarea clasificatorului in restul allowlist-ului.

`autovit`, `okazii`, `publi24`, `lajumate` ies prin modem din 5.2, dar pana la
etapa asta un 403 acolo era un `return []` / `return None` TACUT — nici watchdog,
nici rotatie. Testele de aici verifica exact cablarea (clasificare -> raportare ->
retry imediat pe IP nou / backoff altfel), cu `report_outcome` FALSIFICAT: politica
de rotatie in sine e testata separat in test_rotation_triggers.py.

Trei dintre platforme au un singur punct de intrare (`_request`, prin care trece si
cautarea, si enrichment-ul) — se testeaza direct. `autovit` are doua, oglinda cu
`mobilede` (bucla din search + fetch-ul de detalii).
"""
import pytest

from app.services.radar import autovit_scraper as avs
from app.services.radar import okazii_scraper as oks
from app.services.radar import publi24_scraper as pbs
from app.services.radar import lajumate_scraper as ljs
from app.services.radar.base_scraper import Outcome


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


# Body mic cu marker: la 200 clasifica BLOCKED (interstitial), la 429 NU (ordinea).
_MARKER_BODY = "<html>captcha-delivery</html>"


def _wire(monkeypatch, mod, responses, rotates):
    """Cableaza un modul de scraper cu raspunsuri predefinite si telemetrie falsa.

    `responses` = lista de _Resp sau Exception (aruncata in locul raspunsului).
    `rotates` = ce intoarce report_outcome (rotatia a dat IP nou sau nu).
    Returneaza (calls, slept, reported) — liste populate in timpul rularii.
    """
    calls, slept, reported = [], [], []

    def fake_get(url, **kw):
        calls.append(url)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(mod.binding, "curl_kwargs", lambda p: {})
    monkeypatch.setattr(mod.curl_requests, "get", fake_get)
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(mod, "report_outcome",
                        lambda p, o: (reported.append((p, o)), rotates)[1])
    if hasattr(mod, "log_manager"):
        monkeypatch.setattr(mod.log_manager, "emit", lambda *a, **k: None)
    return calls, slept, reported


# ── cele trei platforme cu un singur punct de intrare: _request ──────────────────

_REQUEST_MODS = [
    pytest.param(oks, "okazii", id="okazii"),
    pytest.param(pbs, "publi24", id="publi24"),
    pytest.param(ljs, "lajumate", id="lajumate"),
]


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_blocat_cu_ip_nou_reia_fara_backoff(monkeypatch, mod, platform):
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")],
        rotates=True)
    assert mod._request("http://x") == "<html>ok</html>"
    assert len(calls) == 2 and slept == []
    assert reported[0] == (platform, Outcome.BLOCKED)


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_blocat_fara_ip_nou_face_backoff(monkeypatch, mod, platform):
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")],
        rotates=False)
    assert mod._request("http://x") == "<html>ok</html>"
    assert len(calls) == 2 and len(slept) == 1
    assert reported[0] == (platform, Outcome.BLOCKED)


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_200_cu_marker_ia_aceeasi_cale_ca_403(monkeypatch, mod, platform):
    # Interstitialul vine si cu 200; fara clasificare l-am fi intors ca pagina buna.
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(200, _MARKER_BODY), _Resp(200, "<html>ok</html>")],
        rotates=True)
    assert mod._request("http://x") == "<html>ok</html>"
    assert len(calls) == 2 and slept == []
    assert reported[0] == (platform, Outcome.BLOCKED)


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_bucla_nu_e_infinita_cand_rotatia_reuseste_mereu(monkeypatch, mod, platform):
    # `continue` CONSUMA incercarea: 3 raspunsuri blocate = 3 apeluri, apoi None.
    calls, slept, _ = _wire(
        monkeypatch, mod, [_Resp(403, "b"), _Resp(403, "b"), _Resp(403, "b")],
        rotates=True)
    assert mod._request("http://x") is None
    assert len(calls) == 3 and slept == []


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_404_ramane_none_fara_retry(monkeypatch, mod, platform):
    # Paginare depasita / anunt sters: comportamentul de dinainte, fara rotatie.
    calls, slept, reported = _wire(monkeypatch, mod, [_Resp(404, "")], rotates=True)
    assert mod._request("http://x") is None
    assert len(calls) == 1 and slept == []
    assert reported == [(platform, Outcome.NOT_FOUND)]


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_429_ramane_rate_limited_nu_blocked(monkeypatch, mod, platform):
    # Ordinea din classify: un 429 cu marker in body NU e blocaj — fereastra se
    # reseteaza singura, rotatia n-ar rezolva ritmul.
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(429, _MARKER_BODY), _Resp(200, "<html>ok</html>")],
        rotates=True)
    assert mod._request("http://x") == "<html>ok</html>"
    assert len(calls) == 2 and len(slept) == 1
    assert [o for _, o in reported] == [Outcome.RATE_LIMITED, Outcome.OK]


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_exceptia_se_raporteaza_transient(monkeypatch, mod, platform):
    # TRANSIENT ajunge la report_outcome (care NU roteste pe el — politica e in
    # triggers), iar bucla reia ca inainte.
    calls, slept, reported = _wire(
        monkeypatch, mod, [ConnectionError("reset"), _Resp(200, "<html>ok</html>")],
        rotates=False)
    assert mod._request("http://x") == "<html>ok</html>"
    assert len(calls) == 2 and len(slept) == 1
    assert reported[0] == (platform, Outcome.TRANSIENT)


@pytest.mark.parametrize("mod,platform", _REQUEST_MODS)
def test_500_ramane_none_dupa_un_apel(monkeypatch, mod, platform):
    # Statusurile necunoscute pastreaza comportamentul actual: WARN + None, fara retry.
    calls, slept, reported = _wire(monkeypatch, mod, [_Resp(500, "")], rotates=True)
    assert mod._request("http://x") is None
    assert len(calls) == 1 and slept == []
    assert reported == [(platform, Outcome.TRANSIENT)]


# ── autovit: bucla din search + fetch-ul de detalii, oglinda cu mobilede ─────────

def _run_search_autovit(monkeypatch, responses, rotates):
    calls, slept, reported = _wire(monkeypatch, avs, responses, rotates)
    avs.search_autovit("bmw", None)
    return calls, slept, reported


def test_autovit_reia_fara_backoff_cand_rotatia_da_ip_nou(monkeypatch):
    calls, slept, reported = _run_search_autovit(
        monkeypatch, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")], rotates=True)
    assert len(calls) == 2 and slept == []
    assert reported[0] == ("autovit", Outcome.BLOCKED)


def test_autovit_face_backoff_cand_rotatia_nu_ajuta(monkeypatch):
    calls, slept, _ = _run_search_autovit(
        monkeypatch, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")], rotates=False)
    assert len(calls) == 2 and len(slept) == 1


def test_autovit_200_cu_marker_ia_aceeasi_cale_ca_403(monkeypatch):
    calls, slept, reported = _run_search_autovit(
        monkeypatch, [_Resp(200, _MARKER_BODY), _Resp(200, "<html>ok</html>")], rotates=True)
    assert len(calls) == 2 and slept == []
    assert reported[0] == ("autovit", Outcome.BLOCKED)


def test_autovit_401_ia_aceeasi_cale(monkeypatch):
    calls, slept, reported = _run_search_autovit(
        monkeypatch, [_Resp(401, ""), _Resp(200, "<html>ok</html>")], rotates=True)
    assert len(calls) == 2 and slept == []
    assert reported[0] == ("autovit", Outcome.BLOCKED)


def test_autovit_bucla_nu_e_infinita(monkeypatch):
    calls, slept, _ = _run_search_autovit(
        monkeypatch, [_Resp(403, "b"), _Resp(403, "b"), _Resp(403, "b")], rotates=True)
    assert len(calls) == 3 and slept == []


def test_autovit_details_403_raporteaza_si_intoarce_gol(monkeypatch):
    calls, _, reported = _wire(monkeypatch, avs, [_Resp(403, "blocked")], rotates=False)
    assert avs.fetch_autovit_listing_details("http://x") == {
        "images": [], "description": None, "specs": {}}
    assert len(calls) == 1
    assert reported == [("autovit", Outcome.BLOCKED)]


def test_autovit_details_200_cu_marker_nu_se_parseaza(monkeypatch):
    # Interstitialul cu 200 ar fi fost parsat ca pagina buna -> imagini/descriere gunoi.
    _, _, reported = _wire(monkeypatch, avs, [_Resp(200, _MARKER_BODY)], rotates=False)
    assert avs.fetch_autovit_listing_details("http://x") == {
        "images": [], "description": None, "specs": {}}
    assert reported == [("autovit", Outcome.BLOCKED)]


def test_autovit_details_200_curat_raporteaza_ok(monkeypatch):
    _, _, reported = _wire(
        monkeypatch, avs, [_Resp(200, "<html><body>curat</body></html>")], rotates=False)
    out = avs.fetch_autovit_listing_details("http://x")
    assert set(out) == {"images", "description", "specs"}
    assert reported == [("autovit", Outcome.OK)]
