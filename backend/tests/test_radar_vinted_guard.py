"""RP-1.1 — guard vinted_html: throttle cu jitter, plafon zilnic, circuit breaker.

Fara retea: ceas (_now) + sleep (_sleep) injectate; raspunsuri simulate prin
guard_before_request / guard_after_response. Starea de modul e resetata per test.
"""
import pytest

import app.services.radar.vinted_html as vh

_D = "vinted.ro"


class Clock:
    def __init__(self, t=1000.0):
        self.t = float(t)

    def now(self):
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture
def guard(monkeypatch):
    clock = Clock(1000.0)
    monkeypatch.setattr(vh, "_now", clock.now)
    vh._breaker.clear()
    vh._daily.clear()
    vh._daily_cap_warned.clear()
    vh._domain_next_ts.clear()
    return clock


def _blocked_cycle():
    vh.guard_before_request(_D)
    vh.guard_after_response(_D, blocked=True)


# ── Circuit breaker ─────────────────────────────────────────────────────────────
def test_one_blocked_still_allowed(guard):
    _blocked_cycle()
    assert vh.guard_status(_D)["allowed"] is True


def test_two_blocked_opens_breaker(guard):
    _blocked_cycle()
    _blocked_cycle()
    st = vh.guard_status(_D)
    assert st["allowed"] is False and st["reason"] == "breaker_open"
    # deschis -> guard_before_request refuza (skip, fara HTTP)
    assert vh.guard_before_request(_D)["allowed"] is False


def test_half_open_single_probe_then_close(guard):
    _blocked_cycle()
    _blocked_cycle()
    guard.advance(vh._BREAKER_COOLDOWN_S + 1)
    # half-open: prima cerere = proba, permisa
    assert vh.guard_before_request(_D)["allowed"] is True
    # a doua, cat timp proba e in curs -> skip
    assert vh.guard_before_request(_D)["allowed"] is False
    # proba reuseste -> breaker inchis + contoare resetate
    vh.guard_after_response(_D, blocked=False)
    assert vh.guard_status(_D)["allowed"] is True
    assert vh._breaker[_D]["consec"] == 0 and vh._breaker[_D]["open_until"] == 0.0


def test_half_open_probe_fail_reopens(guard):
    _blocked_cycle()
    _blocked_cycle()
    guard.advance(vh._BREAKER_COOLDOWN_S + 1)
    assert vh.guard_before_request(_D)["allowed"] is True   # proba
    vh.guard_after_response(_D, blocked=True)                # proba esueaza
    assert vh.guard_status(_D)["allowed"] is False           # re-deschis
    assert vh.guard_before_request(_D)["allowed"] is False


def test_success_resets_consecutive(guard):
    _blocked_cycle()  # consec=1
    vh.guard_before_request(_D)
    vh.guard_after_response(_D, blocked=False)  # succes -> reset
    assert vh._breaker[_D]["consec"] == 0
    # inca un blocked singur nu deschide (contorul a fost resetat)
    _blocked_cycle()
    assert vh.guard_status(_D)["allowed"] is True


# ── Plafon zilnic ───────────────────────────────────────────────────────────────
def test_daily_cap_and_reset(guard):
    cap = vh._DAILY_CAP[_D]
    for _ in range(cap):
        assert vh.guard_before_request(_D)["allowed"] is True
        vh.guard_after_response(_D, blocked=False)  # tine breaker-ul inchis
    r = vh.guard_before_request(_D)  # al (cap+1)-lea
    assert r["allowed"] is False and r["reason"] == "daily_cap"
    # ziua urmatoare -> contor resetat
    guard.advance(86400)
    assert vh.guard_before_request(_D)["allowed"] is True


# ── Throttle cu jitter (interval efectiv in [min, min+jitter]) ──────────────────
def test_rate_limit_interval_bounds(guard, monkeypatch):
    slept = []
    monkeypatch.setattr(vh, "_sleep", lambda s: (slept.append(s), guard.advance(s)))
    vh._rate_limit(_D)          # prima cerere: fara asteptare (fara prior)
    slept.clear()
    vh._rate_limit(_D)          # a doua: asteapta min..min+jitter
    total = sum(slept)
    mn = vh._MIN_INTERVAL[_D]
    jx = vh._JITTER_MAX[_D]
    assert mn <= total <= mn + jx + 1e-6, f"wait={total} nu e in [{mn},{mn+jx}]"


# ── get_html: SKIP fara HTTP cand breaker-ul e deschis ──────────────────────────
def test_get_html_skips_without_http(guard, monkeypatch):
    _blocked_cycle()
    _blocked_cycle()  # breaker deschis

    class _Boom:
        def get(self, *a, **k):
            raise AssertionError("get_html a facut HTTP desi breaker-ul e deschis")

    monkeypatch.setattr(vh, "get_html_session", lambda: _Boom())
    assert vh.get_html("https://www.vinted.ro/catalog") is None
