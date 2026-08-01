"""Teste pentru app/services/network/rotator.py - modem complet mock-uit.

Acopera in special cele trei capcane descoperite empiric:
  - sesiune noua la fiecare operatie (125003 nu e prins de retry-ul bibliotecii)
  - invalidarea cache-ului bind_ip dupa repornire
  - masuratoare esuata => changed=None, NU False
"""
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.network import rotator as rot
from app.services.network.rotator import (
    METHOD_DATASWITCH,
    METHOD_REBOOT,
    HuaweiHilinkRotator,
    Measurement,
    NoopRotator,
    RotationResult,
    build_rotator,
    reset_rotator,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MODEM_"):
            monkeypatch.delenv(key, raising=False)
    reset_rotator()
    yield
    reset_rotator()


def valid(ip="86.1.2.3", asn="AS8953 Orange"):
    return Measurement(ip=ip, asn=asn, bind_ip="192.168.8.100", valid=True)


def invalid(reason="timeout"):
    return Measurement(valid=False, reason=reason)


def rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.2",
                pub_before="86.1.2.3", pub_after="86.9.9.9"):
    """Context manager compus pentru o rotatie reusita, complet mock-uita."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(r, "_connect", return_value=MagicMock()))
    stack.enter_context(patch.object(r, "_wait_api_back", return_value=MagicMock()))
    stack.enter_context(patch.object(r, "_read_wan",
                                     side_effect=[wan_before, wan_after]))
    stack.enter_context(patch.object(r, "_measure", return_value=valid(pub_before)))
    stack.enter_context(patch.object(r, "_wait_data_path",
                                     return_value=valid(pub_after)))
    stack.enter_context(patch("app.services.network.rotator.REBOOT_SETTLE_S", 0))
    stack.enter_context(patch("time.sleep"))
    return stack


# --- factory ---------------------------------------------------------------

def test_default_is_noop():
    assert isinstance(build_rotator(), NoopRotator)


def test_noop_never_available_and_never_raises():
    noop = NoopRotator()
    assert noop.available() is False
    result = noop.rotate()
    assert result.ok is False
    assert result.skipped_reason
    assert noop.wait_if_rotating(0.1) is True


def test_enabled_builds_huawei(monkeypatch):
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "true")
    monkeypatch.setenv("MODEM_HOST", "10.0.0.1")
    monkeypatch.setenv("MODEM_ROTATION_COOLDOWN_S", "42")
    monkeypatch.setenv("MODEM_ROTATION_MAX_PER_HOUR", "9")
    monkeypatch.setenv("MODEM_ROTATION_METHOD", "reboot")
    monkeypatch.setenv("MODEM_PDP_DOWN_S", "45")
    monkeypatch.setenv("MODEM_ESCALATE_AFTER", "7")
    built = build_rotator()
    assert isinstance(built, HuaweiHilinkRotator)
    assert built.host == "10.0.0.1"
    assert built.cooldown_s == 42
    assert built.max_per_hour == 9
    assert built.method == METHOD_REBOOT
    assert built.pdp_down_s == 45
    assert built.escalate_after == 7


def test_env_defaults_to_dataswitch(monkeypatch):
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "true")
    assert build_rotator().method == METHOD_DATASWITCH


def test_singleton_is_stable(monkeypatch):
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "true")
    assert rot.get_rotator() is rot.get_rotator()
    reset_rotator()
    assert rot.get_rotator() is not None


# --- sesiune: capcana 125003 ----------------------------------------------

def test_every_operation_opens_a_new_connection():
    """Reutilizarea unui Connection dupa o operatie duce la 125003 permanent."""
    r = HuaweiHilinkRotator()
    made = []

    def make(*a, **kw):
        made.append(1)
        return MagicMock()

    with patch("huawei_lte_api.Connection.Connection", side_effect=make):
        r._connect()
        r._connect()
        r._connect()
    assert len(made) == 3, "fiecare _connect trebuie sa deschida o sesiune noua"


def test_no_client_is_cached_between_calls():
    r = HuaweiHilinkRotator()
    assert not hasattr(r, "_client"), "clientul NU trebuie cache-uit"


def test_bad_credentials_disable_without_retry():
    from huawei_lte_api.exceptions import LoginErrorUsernamePasswordWrongException

    r = HuaweiHilinkRotator(password="gresita")
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise LoginErrorUsernamePasswordWrongException("wrong", 108006)

    with patch("huawei_lte_api.Connection.Connection", side_effect=boom):
        assert r.available() is False
        assert r.available() is False
        assert r.rotate().ok is False
    assert "credentiale" in (r._disabled_reason or "")


def test_lockout_disables_permanently():
    from huawei_lte_api.exceptions import LoginErrorUsernamePasswordOverrunException

    r = HuaweiHilinkRotator()
    with patch("huawei_lte_api.Connection.Connection",
               side_effect=LoginErrorUsernamePasswordOverrunException("over", 108007)):
        assert r.available() is False
    assert "lockout" in (r._disabled_reason or "")


# --- bind IP: capcana re-enumerarii ---------------------------------------

def test_bind_ip_override_wins():
    r = HuaweiHilinkRotator(bind_ip_override="192.168.8.100")
    assert r.bind_ip() == "192.168.8.100"


def test_bind_ip_autodetect_is_cached():
    r = HuaweiHilinkRotator()
    with patch("app.services.network.rotator.local_ip_towards", return_value="192.168.8.55") as spy:
        assert r.bind_ip() == "192.168.8.55"
        assert r.bind_ip() == "192.168.8.55"
    assert spy.call_count == 1


def test_invalidate_bind_ip_forces_relookup():
    r = HuaweiHilinkRotator()
    with patch("app.services.network.rotator.local_ip_towards", side_effect=["192.168.8.55",
                                                        "192.168.8.77"]):
        assert r.bind_ip() == "192.168.8.55"
        r.invalidate_bind_ip()
        assert r.bind_ip() == "192.168.8.77"


def test_reboot_invalidates_bind_ip_cache():
    """Dupa repornire adaptorul se re-enumereaza; un cache vechi ar fi mort."""
    r = HuaweiHilinkRotator(cooldown_s=0, method=METHOD_REBOOT)
    r._bind_ip_cache = "192.168.8.OLD"
    seen = []

    def spy_invalidate():
        seen.append(r._bind_ip_cache)
        r._bind_ip_cache = None

    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_wait_api_back", return_value=MagicMock()), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch.object(r, "invalidate_bind_ip", side_effect=spy_invalidate), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        r.rotate()
    assert seen, "invalidate_bind_ip trebuie apelat la repornire"


# --- semnal: WAN, nu IP public ---------------------------------------------

def test_wan_change_is_the_success_signal():
    r = HuaweiHilinkRotator(cooldown_s=0)
    with rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.2"):
        result = r.rotate()
    assert result.ok is True
    assert result.changed is True
    assert result.old_wan == "10.0.0.1"
    assert result.new_wan == "10.0.0.2"
    assert result.method == METHOD_DATASWITCH


def test_public_drift_without_wan_change_is_not_success():
    """Pe Digi IP-ul public deriva singur. WAN identic => rotatia NU a avut loc."""
    r = HuaweiHilinkRotator(cooldown_s=0)
    with rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.1",
                     pub_before="86.125.23.175", pub_after="86.125.25.175"):
        result = r.rotate()
    assert result.ok is True
    assert result.changed is False, "WAN identic inseamna fara rotatie"
    assert result.public_changed is True, "publicul chiar s-a schimbat (deriva)"
    assert "WAN nemodificat" in result.summary()


def test_same_wan_and_same_public():
    r = HuaweiHilinkRotator(cooldown_s=0)
    with rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.1",
                     pub_before="86.1.2.3", pub_after="86.1.2.3"):
        result = r.rotate()
    assert result.changed is False
    assert result.public_changed is False


def test_unreadable_wan_gives_none_not_false():
    """Masuratoare esuata != rezultat negativ."""
    r = HuaweiHilinkRotator(cooldown_s=0)
    with rotation_ok(r, wan_before=None, wan_after="10.0.0.2"):
        result = r.rotate()
    assert result.ok is True
    assert result.changed is None, "trebuie None, nu False"
    assert "neconcludent" in result.summary()


def test_internet_not_back_is_failure():
    r = HuaweiHilinkRotator(cooldown_s=0)
    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_read_wan", return_value="10.0.0.1"), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=invalid("timeout")), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        result = r.rotate()
    assert result.ok is False
    assert "internetul nu a revenit" in result.error


# --- metoda dataswitch -----------------------------------------------------

def test_dataswitch_is_default():
    r = HuaweiHilinkRotator()
    assert r.method == METHOD_DATASWITCH


def test_invalid_method_rejected():
    with pytest.raises(ValueError, match="metoda necunoscuta"):
        HuaweiHilinkRotator(method="magie")


def test_dataswitch_turns_data_off_then_on():
    r = HuaweiHilinkRotator(cooldown_s=0, pdp_down_s=0)
    client = MagicMock()
    restored = []
    with patch.object(r, "_connect", return_value=client), \
         patch.object(r, "_force_data_on",
                      side_effect=lambda *a, **k: restored.append(1) or True), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch("time.sleep"):
        result = r.rotate()
    client.dial_up.set_mobile_dataswitch.assert_called_once_with(dataswitch=0)
    assert restored, "_force_data_on trebuie apelat pentru repornirea datelor"
    assert result.ok is True


def test_dataswitch_restores_data_even_if_wait_throws():
    """Fara finally, un proces oprit la mijloc ar lasa modemul offline."""
    r = HuaweiHilinkRotator(cooldown_s=0, pdp_down_s=1)
    restored = []
    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_force_data_on",
                      side_effect=lambda *a, **k: restored.append(1) or True), \
         patch("time.sleep", side_effect=KeyboardInterrupt("Ctrl+C")):
        with pytest.raises(KeyboardInterrupt):
            r._apply_dataswitch()
    assert restored, "datele trebuie repornite chiar si la intrerupere"


def test_dataswitch_does_not_reboot():
    r = HuaweiHilinkRotator(cooldown_s=0, pdp_down_s=0)
    client = MagicMock()
    with patch.object(r, "_connect", return_value=client), \
         patch.object(r, "_force_data_on", return_value=True), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch("time.sleep"):
        r.rotate()
    client.device.set_control.assert_not_called()


# --- metoda reboot ---------------------------------------------------------

def test_reboot_method_calls_set_control():
    r = HuaweiHilinkRotator(cooldown_s=0, method=METHOD_REBOOT)
    client = MagicMock()
    with patch.object(r, "_connect", return_value=client), \
         patch.object(r, "_wait_api_back", return_value=MagicMock()), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        result = r.rotate()
    client.device.set_control.assert_called_once()
    assert result.method == METHOD_REBOOT


def test_reboot_command_exception_is_tolerated():
    """Modemul poate pleca inainte sa raspunda - normal, nu eroare."""
    r = HuaweiHilinkRotator(cooldown_s=0, method=METHOD_REBOOT)
    client = MagicMock()
    client.device.set_control.side_effect = OSError("connection reset")
    with patch.object(r, "_connect", return_value=client), \
         patch.object(r, "_wait_api_back", return_value=MagicMock()), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        result = r.rotate()
    assert result.ok is True
    assert result.changed is True


def test_modem_never_returns_is_failure():
    r = HuaweiHilinkRotator(cooldown_s=0, method=METHOD_REBOOT)
    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_wait_api_back",
                      side_effect=RuntimeError("modemul nu a revenit")), \
         patch.object(r, "_read_wan", return_value="10.0.0.1"), \
         patch.object(r, "_measure", return_value=valid()), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        result = r.rotate()
    assert result.ok is False
    assert "nu a revenit" in result.error


# --- escaladare ------------------------------------------------------------

def test_no_escalation_while_dataswitch_works():
    r = HuaweiHilinkRotator(cooldown_s=0, escalate_after=2)
    assert r._effective_method() == METHOD_DATASWITCH
    r._consecutive_no_change = 1
    assert r._effective_method() == METHOD_DATASWITCH


def test_escalates_to_reboot_after_repeated_no_change():
    r = HuaweiHilinkRotator(cooldown_s=0, escalate_after=2)
    r._consecutive_no_change = 2
    assert r._effective_method() == METHOD_REBOOT


def test_counter_increments_on_no_change():
    r = HuaweiHilinkRotator(cooldown_s=0)
    with rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.1"):
        r.rotate()
    assert r._consecutive_no_change == 1


def test_counter_resets_on_success():
    r = HuaweiHilinkRotator(cooldown_s=0)
    r._consecutive_no_change = 5
    with rotation_ok(r, wan_before="10.0.0.1", wan_after="10.0.0.2"):
        r.rotate()
    assert r._consecutive_no_change == 0


def test_unknown_result_does_not_move_counter():
    r = HuaweiHilinkRotator(cooldown_s=0)
    r._consecutive_no_change = 1
    with rotation_ok(r, wan_before=None, wan_after="10.0.0.2"):
        r.rotate()
    assert r._consecutive_no_change == 1


def test_reboot_method_never_escalates():
    r = HuaweiHilinkRotator(method=METHOD_REBOOT, escalate_after=1)
    r._consecutive_no_change = 99
    assert r._effective_method() == METHOD_REBOOT


# --- recuperare date oprite ------------------------------------------------

def test_available_turns_data_back_on_if_left_off():
    """Un proces mort la mijlocul rotatiei lasa modemul offline."""
    r = HuaweiHilinkRotator()
    client = MagicMock()
    client.dial_up.mobile_dataswitch.return_value = {"dataswitch": "0"}
    with patch.object(r, "_try_connect", return_value=client), \
         patch.object(r, "_force_data_on", return_value=True) as forced:
        assert r.available() is True
    forced.assert_called_once()


def test_available_leaves_data_alone_when_on():
    r = HuaweiHilinkRotator()
    client = MagicMock()
    client.dial_up.mobile_dataswitch.return_value = {"dataswitch": "1"}
    with patch.object(r, "_try_connect", return_value=client), \
         patch.object(r, "_force_data_on", return_value=True) as forced:
        assert r.available() is True
    forced.assert_not_called()


def test_force_data_on_retries_with_fresh_sessions():
    r = HuaweiHilinkRotator()
    attempts = []

    def flaky(*a, **kw):
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("token mort")
        return MagicMock()

    with patch.object(r, "_connect", side_effect=flaky), patch("time.sleep"):
        assert r._force_data_on(tries=4) is True
    assert len(attempts) == 3, "fiecare incercare deschide sesiune noua"


def test_force_data_on_gives_up_loudly():
    r = HuaweiHilinkRotator()
    with patch.object(r, "_connect", side_effect=OSError("mort")), \
         patch("time.sleep"):
        assert r._force_data_on(tries=2) is False


# --- garda ASN -------------------------------------------------------------

def test_measurement_without_bind_ip_is_invalid():
    r = HuaweiHilinkRotator()
    with patch("app.services.network.rotator.local_ip_towards", return_value=None):
        m = r._measure()
    assert m.valid is False
    assert "fara IP local" in m.reason


# --- throttling ------------------------------------------------------------

def test_cooldown_blocks_second_rotation():
    r = HuaweiHilinkRotator(cooldown_s=600)
    r._last_rotation_at = time.monotonic()
    result = r.rotate()
    assert result.ok is False
    assert "cooldown" in result.skipped_reason


def test_force_bypasses_cooldown():
    r = HuaweiHilinkRotator(cooldown_s=600)
    r._last_rotation_at = time.monotonic()
    with rotation_ok(r):
        result = r.rotate(force=True)
    assert result.ok is True


def test_hourly_budget_exhausted():
    r = HuaweiHilinkRotator(cooldown_s=0, max_per_hour=3)
    now = time.monotonic()
    r._history.extend([now - 10, now - 20, now - 30])
    result = r.rotate()
    assert result.ok is False
    assert "buget orar" in result.skipped_reason


def test_old_rotations_fall_out_of_window():
    r = HuaweiHilinkRotator(cooldown_s=0, max_per_hour=2)
    now = time.monotonic()
    r._history.extend([now - 7200, now - 5000])
    assert r._throttle_reason() is None


# --- concurenta ------------------------------------------------------------

def test_scrapers_pause_during_rotation():
    """Sincronizare pe Event, nu pe sleep.

    O varianta bazata pe time.sleep e dubla-gresita aici: patch("time.sleep")
    anuleaza si sleep-urile testului (acelasi atribut de modul), iar chiar si
    cu sleep real ramane o cursa care poate cadea pe hardware lent.
    """
    r = HuaweiHilinkRotator(cooldown_s=0)
    observed = []
    entered = threading.Event()   # rotatia a ajuns la mijloc
    release = threading.Event()   # firul principal a terminat de verificat

    def hold(*a, **kw):
        observed.append(r._idle.is_set())
        entered.set()
        release.wait(10)
        return valid("86.9.9.9")

    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_wait_api_back", return_value=MagicMock()), \
         patch.object(r, "_read_wan", side_effect=["10.0.0.1", "10.0.0.2"]), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", side_effect=hold), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        assert r._idle.is_set() is True
        thread = threading.Thread(target=r.rotate)
        thread.start()
        assert entered.wait(10), "rotatia nu a ajuns la _wait_data_path"
        blocked = not r._idle.is_set()
        release.set()
        thread.join(10)
        assert not thread.is_alive(), "firul de rotatie nu s-a incheiat"

    assert blocked, "scraperele trebuie sa fie in pauza in timpul rotatiei"
    assert all(not was_set for was_set in observed)
    assert r._idle.is_set() is True


def test_concurrent_rotations_serialize():
    r = HuaweiHilinkRotator(cooldown_s=999)
    results = []
    with patch.object(r, "_connect", return_value=MagicMock()), \
         patch.object(r, "_wait_api_back", return_value=MagicMock()), \
         patch.object(r, "_read_wan", return_value="10.0.0.1"), \
         patch.object(r, "_measure", return_value=valid()), \
         patch.object(r, "_wait_data_path", return_value=valid("86.9.9.9")), \
         patch("app.services.network.rotator.REBOOT_SETTLE_S", 0), patch("time.sleep"):
        threads = [threading.Thread(target=lambda: results.append(r.rotate()))
                   for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert sum(1 for x in results if x.ok) == 1


def test_idle_released_even_on_exception():
    r = HuaweiHilinkRotator(cooldown_s=0)
    with patch.object(r, "_do_rotate", side_effect=RuntimeError("boom")), \
         patch("time.sleep"):
        with pytest.raises(RuntimeError):
            r.rotate()
    assert r._idle.is_set() is True


# --- rezumate --------------------------------------------------------------

def test_summary_is_human_readable():
    assert "dezactivata" in NoopRotator().rotate().summary()
    assert "esuata" in RotationResult(ok=False, error="x").summary()
    assert "ignorata" in RotationResult(ok=False, skipped_reason="y").summary()
    assert "dataswitch" in RotationResult(
        ok=True, changed=True, method=METHOD_DATASWITCH).summary()
