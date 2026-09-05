"""NET-5.3b — cablarea clasificatorului in restul allowlist-ului.

`okazii`, `publi24`, `lajumate` ies prin modem din 5.2, dar pana la
etapa asta un 403 acolo era un `return []` / `return None` TACUT — nici watchdog,
nici rotatie. Testele de aici verifica exact cablarea (clasificare -> raportare ->
retry imediat pe IP nou / backoff altfel), cu `report_outcome` FALSIFICAT: politica
de rotatie in sine e testata separat in test_rotation_triggers.py.

Toate trei au un singur punct de intrare (`_request`, prin care trece si cautarea,
si enrichment-ul) — se testeaza direct.

RC-1: sectiunile `autovit` (bucla din search + fetch de detalii) au disparut odata cu
scraperul; comportamentele lor traiesc in testele parametrizate de mai jos.
"""
import pytest

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
def test_401_ia_aceeasi_cale_ca_403(monkeypatch, mod, platform):
    # RC-1: 401 era acoperit DOAR de `test_autovit_401_ia_aceeasi_cale`. `classify`
    # trateaza 401 si 403 la fel (`status in (401, 403) -> BLOCKED`), dar pana aici
    # nicio platforma ramasa nu proba ramura pe 401.
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(401, ""), _Resp(200, "<html>ok</html>")],
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


# ── calea de detalii e single-shot pe blocaj (audit 5.3c) ────────────────────────
# Un blocaj e PERSISTENT (spre deosebire de 429): backoff-ul l-ar plati fiecare item
# din enrichment — 36 iteme × ~15s = ~10 minute de sleep per pagina.

_DETAILS = [
    pytest.param(oks, "okazii", "fetch_okazii_listing_details", id="okazii"),
    pytest.param(pbs, "publi24", "fetch_publi24_listing_details", id="publi24"),
]
# LJ-2: LaJumate nu mai are cale de detalii (enrichment scos, masurat redundant in
# SONDA-LJ4). Ramane in `_REQUEST_MODS` de mai sus — cautarea lui trece prin acelasi
# `_request`, deci toata cablarea de blocaje ii ramane testata.


@pytest.mark.parametrize("mod,platform,fn", _DETAILS)
def test_detaliile_blocate_nu_fac_backoff(monkeypatch, mod, platform, fn):
    calls, slept, reported = _wire(monkeypatch, mod, [_Resp(403, "blocked")], rotates=False)
    out = getattr(mod, fn)("http://x")
    assert out.get("images") == [] and out.get("description") is None
    assert len(calls) == 1 and slept == []
    assert reported == [(platform, Outcome.BLOCKED)]


@pytest.mark.parametrize("mod,platform,fn", _DETAILS)
def test_detaliile_blocate_reiau_imediat_pe_ip_nou(monkeypatch, mod, platform, fn):
    # Rotatia reusita salveaza itemul curent — gratis, fara sleep.
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")], rotates=True)
    getattr(mod, fn)("http://x")
    assert len(calls) == 2 and slept == []
    assert reported[0] == (platform, Outcome.BLOCKED)


@pytest.mark.parametrize("mod,platform,fn", _DETAILS)
def test_detaliile_pastreaza_retry_pe_429(monkeypatch, mod, platform, fn):
    # 429 pe detalii avea retry cu backoff DINAINTE de 5.3b — fereastra se inchide
    # singura, deci reincercarea are sens. Doar blocajul e single-shot.
    calls, slept, reported = _wire(
        monkeypatch, mod, [_Resp(429, ""), _Resp(200, "<html>ok</html>")], rotates=False)
    getattr(mod, fn)("http://x")
    assert len(calls) == 2 and len(slept) == 1
    assert reported[0] == (platform, Outcome.RATE_LIMITED)


@pytest.mark.parametrize("mod,platform,fn", _DETAILS)
def test_detaliile_200_cu_marker_nu_se_parseaza(monkeypatch, mod, platform, fn):
    # RC-1: portat de la `test_autovit_details_200_cu_marker_nu_se_parseaza`, singurul
    # care proba interstitialul pe CALEA DE DETALII. Fara clasificare, pagina de blocaj
    # ar fi fost parsata ca pagina buna -> imagini/descriere gunoi in feed.
    _, _, reported = _wire(monkeypatch, mod, [_Resp(200, _MARKER_BODY)], rotates=False)
    out = getattr(mod, fn)("http://x")
    assert out.get("images") == [] and out.get("description") is None
    assert reported == [(platform, Outcome.BLOCKED)]
