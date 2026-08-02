"""NET-5.3d — cablarea raportarii de blocaje pe Vinted + gaurile de acoperire din audit.

Auditul Vinted a gasit ca `get_html` detecta blocajul dar NU il raporta nicaieri:
breakerul local se arma 6 ore, dar rotatia nu se declansa niciodata de aici, iar
watchdog-ul nu vedea niciun `note_blocked("vinted")`. Tot aici: divergenta
`guard_status` vs `guard_before_request` in fereastra half-open, si trei mutatii
care supravietuiau intregii suite (invalidarea wrapperului la rotatie, bind-key-ul
pe device, calea `_gone` din enrichment-ul de fundal).

`report_outcome` e FALSIFICAT in testele de get_html — politica de rotatie ramane
testata in test_rotation_triggers.py.
"""
import sys
import types

import pytest

from app.services.radar import base_scraper as bs
from app.services.radar import vinted_html as vh
from app.services.radar.base_scraper import Outcome


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


_STATE_DICTS = ("_breaker", "_daily", "_daily_global", "_daily_cap_warned",
                "_daily_global_warned", "_domain_next_ts")


@pytest.fixture(autouse=True)
def vh_clean(monkeypatch):
    """Stare curata in vinted_html, log silentios, throttle si binding neutre."""
    for name in _STATE_DICTS:
        getattr(vh, name).clear()
    monkeypatch.setattr(vh.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(vh, "_rate_limit", lambda d: None)
    monkeypatch.setattr(vh.binding, "curl_kwargs", lambda p: {})
    yield
    for name in _STATE_DICTS:
        getattr(vh, name).clear()


def _wire_get_html(monkeypatch, responses, rotates):
    """Sesiune HTTP falsa + report_outcome fals. Intoarce (calls, reported)."""
    calls, reported = [], []
    sess = types.SimpleNamespace(
        get=lambda url, headers=None, **kw: (calls.append(url), responses.pop(0))[1])
    monkeypatch.setattr(vh, "get_html_session", lambda: sess)
    monkeypatch.setattr(bs, "report_outcome",
                        lambda p, o: (reported.append((p, o)), rotates)[1])
    return calls, reported


# ── get_html raporteaza blocajul (5.3d-A) ────────────────────────────────────────

def test_get_html_blocat_raporteaza_si_intoarce_raspunsul(monkeypatch):
    calls, reported = _wire_get_html(monkeypatch, [_Resp(403, "blocked")], rotates=False)
    resp = vh.get_html("https://www.vinted.ro/items/1")
    assert resp is not None and resp.status_code == 403   # comportamentul vechi
    assert len(calls) == 1
    assert reported == [("vinted", Outcome.BLOCKED)]


def test_get_html_ip_nou_reincearca_imediat(monkeypatch):
    calls, reported = _wire_get_html(
        monkeypatch, [_Resp(403, "blocked"), _Resp(200, "<html>ok</html>")], rotates=True)
    resp = vh.get_html("https://www.vinted.ro/items/1")
    assert resp.status_code == 200
    assert len(calls) == 2
    assert reported == [("vinted", Outcome.BLOCKED)]


def test_get_html_curat_nu_raporteaza(monkeypatch):
    calls, reported = _wire_get_html(monkeypatch, [_Resp(200, "<html>ok</html>")], rotates=True)
    resp = vh.get_html("https://www.vinted.ro/items/1")
    assert resp.status_code == 200
    assert len(calls) == 1 and reported == []


def test_get_html_blocat_de_doua_ori_se_opreste(monkeypatch):
    # `range(2)` consuma reincercarea: doua blocaje = doua requesturi, apoi iesire
    # cu raspunsul blocat (nu bucla infinita cand rotatia reuseste mereu).
    calls, reported = _wire_get_html(
        monkeypatch, [_Resp(403, "b"), _Resp(403, "b")], rotates=True)
    resp = vh.get_html("https://www.vinted.ro/items/1")
    assert resp.status_code == 403
    assert len(calls) == 2
    assert len(reported) == 2


def test_get_html_404_curat_nu_raporteaza(monkeypatch):
    # Calea RAD-1 (item sters/vandut -> gone) se bazeaza pe 404-ul curat; un
    # report/rotatie aici ar transforma stergerile normale in trafic de rotatie.
    calls, reported = _wire_get_html(monkeypatch, [_Resp(404, "")], rotates=True)
    resp = vh.get_html("https://www.vinted.ro/items/1")
    assert resp.status_code == 404
    assert len(calls) == 1 and reported == []


# ── guard_status vede proba half-open (5.3d-B) ───────────────────────────────────

def test_guard_status_vede_proba_half_open():
    b = vh._breaker.setdefault("vinted.ro", vh._new_breaker())
    b["open_until"] = vh._now() - 1        # cooldown expirat, dar breakerul e nenul
    d = vh.guard_before_request("vinted.ro")
    assert d["allowed"] is True and b["half_open"] is True   # asta e proba
    gs = vh.guard_status("vinted.ro")
    assert gs["allowed"] is False and gs["reason"] == "breaker_open"


def test_guard_status_dupa_proba_reusita_permite():
    b = vh._breaker.setdefault("vinted.ro", vh._new_breaker())
    b["open_until"] = vh._now() - 1
    vh.guard_before_request("vinted.ro")
    vh.guard_after_response("vinted.ro", blocked=False)      # proba a reusit
    assert vh.guard_status("vinted.ro")["allowed"] is True


# ── rotatia cu changed=True invalideaza wrapperul (gaura M1 din audit) ───────────

def test_reset_ip_reputation_invalideaza_wrapperul(monkeypatch):
    from app.services.network import triggers
    from app.services.radar import vinted_scraper as vs
    order = []
    monkeypatch.setattr(vh, "reset_for_new_ip", lambda: order.append("reset_html"))
    monkeypatch.setattr(vs, "_invalidate_wrapper", lambda: order.append("invalidate"))
    triggers._reset_ip_reputation()
    assert order == ["reset_html", "invalidate"]


# ── bind-key-ul wrapperului include device-ul (gaura M2 din audit) ───────────────

def _fake_vinted_lib(monkeypatch, built):
    mod = types.ModuleType("vinted_scraper")

    class _FakeWrapper:
        def __init__(self, base, config=None):
            built.append(config)

    mod.VintedWrapper = _FakeWrapper
    monkeypatch.setitem(sys.modules, "vinted_scraper", mod)


class _StubRotator:
    def __init__(self, ip="192.168.8.123", device="usb0"):
        self._ip = ip
        self._device = device
        self.disabled_reason = None
        self.host = "192.168.8.1"

    def bind_ip(self):
        return self._ip

    def invalidate_bind_ip(self):
        pass

    def bind_device(self):
        return self._device

    def wait_if_rotating(self, timeout=180.0):
        return True


def test_wrapper_reconstruit_cand_device_se_schimba(monkeypatch):
    # Re-enumerare usb0 -> usb1 cu ACELASI IP DHCP: fara device in bind-key,
    # wrapperul ar ramane cu SO_BINDTODEVICE pe interfata moarta.
    import os as _os
    from app.services.network import binding
    from app.services.radar import vinted_scraper as vs

    binding.reset_state()
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "vinted")
    monkeypatch.setattr(binding, "os",
                        types.SimpleNamespace(name="posix", environ=_os.environ))
    monkeypatch.setattr(binding, "_log", lambda level, msg: None)
    monkeypatch.setattr(binding, "local_ip_towards",
                        lambda t: "192.168.8.123" if str(t).startswith("192.168.8.") else "192.168.1.144")
    rot = _StubRotator(device="usb0")
    monkeypatch.setattr(binding, "get_rotator", lambda: rot)
    monkeypatch.setattr(vs.log_manager, "emit", lambda *a, **k: None)
    monkeypatch.setattr(vs, "_wrapper", None)
    monkeypatch.setattr(vs, "_wrapper_bind", None)

    built = []
    _fake_vinted_lib(monkeypatch, built)
    w1 = vs._get_wrapper()
    rot._device = "usb1"                       # acelasi IP, alt device
    w2 = vs._get_wrapper()
    binding.reset_state()
    assert w2 is not w1 and len(built) == 2


# ── calea _gone din enrichment-ul de fundal (gaura M4 din audit) ─────────────────

def test_enrich_vinted_background_marcheaza_gone(monkeypatch):
    # Singura suita intreaga nu executa _enrich_vinted_background: mutatia
    # `_gone` -> altceva supravietuia. Testul fixeaza contractul RAD-1: item
    # disparut -> status "removed" + iese din coada (fetched=True).
    from app.database import SessionLocal
    from app.models.user import User
    from app.models.radar_keyword import RadarKeyword
    from app.models.radar_listing import RadarListing
    from app.utils import radar_scanner as rs

    db = SessionLocal()
    try:
        user = User(email="vgone@example.com", username="vgone", hashed_password="x")
        db.add(user)
        db.commit()
        db.refresh(user)
        kw = RadarKeyword(user_id=user.id, name="geaca nike", max_price=200.0,
                          resale_price=350.0)
        db.add(kw)
        db.commit()
        db.refresh(kw)
        row = RadarListing(user_id=user.id, keyword_id=kw.id, platform="vinted",
                           external_id="vinted_12345", title="Geaca Nike", price=120.0,
                           url="https://www.vinted.ro/items/12345", status="active",
                           vinted_detail_fetched=False)
        db.add(row)
        db.commit()
        db.refresh(row)

        monkeypatch.setattr(rs, "get_vinted_item_detail", lambda item_id: {"_gone": True})
        monkeypatch.setattr(rs, "vinted_guard_status",
                            lambda d: {"allowed": True, "reason": None, "open_until": 0.0})
        monkeypatch.setattr(rs.log_manager, "emit", lambda *a, **k: None)
        monkeypatch.setitem(rs._enrich_counters, "vinted", 0)

        rs._enrich_vinted_background(db, user)
        db.refresh(row)
        assert row.status == "removed"
        assert row.vinted_detail_fetched is True
    finally:
        db.close()
