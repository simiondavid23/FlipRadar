"""NET-5.2 — binding selectiv per platforma.

Rotatorul e FALSIFICAT (stub cu available/bind_ip/bind_device/wait_if_rotating): zero
atingere de modem, zero retea.

AMBELE ramuri de OS se testeaza, prin monkeypatch pe `os.name`. Suita ruleaza pe
Windows; fara asta, ramura Linux ar trece verde aici si ar cadea la prima rulare pe Pi.
"""
import sys
import types

import pytest

from app.services.network import binding
from app.services.network.rotator import NoopRotator, reset_rotator


class _StubRotator:
    def __init__(self, available=True, ip="192.168.8.123", device="usb0", wait=True):
        self._available = available
        self._ip = ip
        self._device = device
        self._wait = wait
        self.wait_calls = 0

    def available(self):
        return self._available

    def bind_ip(self):
        return self._ip

    def bind_device(self):
        return self._device

    def wait_if_rotating(self, timeout=180.0):
        self.wait_calls += 1
        return self._wait


@pytest.fixture(autouse=True)
def logs(monkeypatch):
    """Stare curata, allowlist implicit, log capturat. Implicit ruta default NU trece
    prin modem (adresa sursa catre internet difera de cea a modemului)."""
    binding.reset_state()
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "mobilede,vinted")
    captured = []
    monkeypatch.setattr(binding, "_log", lambda level, msg: captured.append((level, msg)))
    monkeypatch.setattr(binding, "local_ip_towards", lambda target: "192.168.1.144")
    yield captured
    binding.reset_state()


def _use(monkeypatch, **kw):
    rot = _StubRotator(**kw)
    monkeypatch.setattr(binding, "get_rotator", lambda: rot)
    return rot


def _warns(captured):
    return [m for lvl, m in captured if lvl == "WARN"]


# ── allowlist ────────────────────────────────────────────────────────────────────

def test_platforma_in_allowlist_leaga(monkeypatch):
    _use(monkeypatch)
    assert binding.curl_kwargs("mobilede") == {"interface": "192.168.8.123"}


def test_platforma_in_afara_listei_nu_leaga(monkeypatch, logs):
    _use(monkeypatch)
    # olx si facebook sunt excluse intentionat (sesiuni autentificate).
    assert binding.curl_kwargs("olx") == {}
    assert binding.httpx_config("facebook") == {}
    assert _warns(logs) == []       # nu e o anomalie, deci niciun WARN


def test_allowlist_goala_nu_leaga_nimic(monkeypatch):
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "")
    _use(monkeypatch)
    assert binding.curl_kwargs("mobilede") == {}
    assert binding.httpx_config("vinted") == {}


def test_rotatie_dezactivata_da_dict_gol(monkeypatch):
    # Fara stub: trece prin build_rotator real -> NoopRotator.
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "false")
    reset_rotator()
    try:
        assert binding.curl_kwargs("mobilede") == {}
    finally:
        reset_rotator()


# ── „oprit din config" vs „modem disparut" — perechea care tine fix-ul in loc ────

def test_rotatie_dezactivata_e_complet_tacuta(monkeypatch, logs):
    # NoopRotator = oprit din configuratie. Nu e anomalie: niciun log, niciun contor.
    monkeypatch.setattr(binding, "get_rotator", lambda: NoopRotator())
    assert binding.curl_kwargs("mobilede") == {}
    assert binding.httpx_config("vinted") == {}
    assert logs == []
    st = binding.bind_state()
    assert st["bound"] == 0 and st["unbound"] == 0


def test_modem_disparut_ramane_zgomotos(monkeypatch, logs):
    # Rotator REAL (nu Noop) dar indisponibil = anomalie. Daca fix-ul de mai sus ar fi
    # prea larg si ar tacea la orice indisponibilitate, am reintroduce „binding omis
    # tacit" — exact defectul pe care fail-open-ul zgomotos il previne.
    _use(monkeypatch, available=False)
    assert binding.curl_kwargs("mobilede") == {}
    warns = _warns(logs)
    assert len(warns) == 1 and "INDISPONIBIL" in warns[0]
    assert binding.bind_state()["unbound"] == 1


# ── fail-open ────────────────────────────────────────────────────────────────────

def test_available_false_e_fail_open(monkeypatch, logs):
    _use(monkeypatch, available=False)
    assert binding.curl_kwargs("mobilede") == {}
    assert len(_warns(logs)) == 1


def test_fara_bind_ip_un_singur_warn(monkeypatch, logs):
    _use(monkeypatch, ip=None)
    for _ in range(5):
        assert binding.curl_kwargs("mobilede") == {}
    assert len(_warns(logs)) == 1   # per tranzitie, nu per request


def test_exceptia_din_rotator_e_fail_open(monkeypatch, logs):
    class _Boom:
        def wait_if_rotating(self, timeout=180.0):
            raise RuntimeError("modem plecat")
    monkeypatch.setattr(binding, "get_rotator", lambda: _Boom())
    assert binding.curl_kwargs("mobilede") == {}
    assert len(_warns(logs)) == 1


def test_warnul_poarta_cauza_reala_nu_doar_tipul(monkeypatch, logs):
    # Config gresita in .env, nu modem lipsa: mesajul trebuie sa spuna ASTA, altfel
    # omul cauta la infinit un adaptor care functioneaza perfect.
    def _boom():
        raise ValueError("metoda necunoscuta: datswitch. Valide: dataswitch, reboot")
    monkeypatch.setattr(binding, "get_rotator", _boom)
    assert binding.curl_kwargs("mobilede") == {}
    warns = _warns(logs)
    assert len(warns) == 1 and "metoda necunoscuta" in warns[0]


# ── ramificarea pe OS ────────────────────────────────────────────────────────────

def test_windows_curl_fara_prefix(monkeypatch):
    monkeypatch.setattr(binding.os, "name", "nt")
    _use(monkeypatch, device="usb0")
    # libcurl NU accepta nume de interfata pe Windows.
    assert binding.curl_kwargs("mobilede") == {"interface": "192.168.8.123"}


def test_linux_curl_cu_prefix_ifhost(monkeypatch):
    monkeypatch.setattr(binding.os, "name", "posix")
    _use(monkeypatch, device="usb0")
    assert binding.curl_kwargs("mobilede") == {
        "interface": "ifhost!usb0!192.168.8.123"}


def test_linux_curl_fara_device_e_degradat_cu_warn(monkeypatch, logs):
    monkeypatch.setattr(binding.os, "name", "posix")
    _use(monkeypatch, device=None)
    assert binding.curl_kwargs("mobilede") == {"interface": "192.168.8.123"}
    assert any("numele interfetei" in m for m in _warns(logs))


def test_windows_httpx_fara_socket_options(monkeypatch):
    monkeypatch.setattr(binding.os, "name", "nt")
    _use(monkeypatch, device="usb0")
    assert binding.httpx_config("vinted") == {"local_address": "192.168.8.123"}


def test_linux_httpx_cu_so_bindtodevice(monkeypatch):
    monkeypatch.setattr(binding.os, "name", "posix")
    _use(monkeypatch, device="usb0")
    cfg = binding.httpx_config("vinted")
    assert cfg["local_address"] == "192.168.8.123"
    assert cfg["socket_options"] == [
        (binding.socket.SOL_SOCKET, binding._SO_BINDTODEVICE, b"usb0")]


def test_httpx_config_respecta_allowlist(monkeypatch):
    _use(monkeypatch)
    assert binding.httpx_config("okazii") == {}   # nu e in allowlist-ul fixture-ului


# ── rotatie in curs ──────────────────────────────────────────────────────────────

def test_wait_if_rotating_apelat_la_fiecare_request(monkeypatch):
    rot = _use(monkeypatch)
    binding.curl_kwargs("mobilede")
    binding.curl_kwargs("mobilede")
    binding.httpx_config("vinted")
    assert rot.wait_calls == 3


def test_wait_timeout_da_dict_gol_si_warn(monkeypatch, logs):
    _use(monkeypatch, wait=False)
    assert binding.curl_kwargs("mobilede") == {}
    assert any("rotatie in curs" in m for m in _warns(logs))


# ── zgomot exact o data ──────────────────────────────────────────────────────────

def test_tranzitia_da_exact_doua_warnuri(monkeypatch, logs):
    rot = _use(monkeypatch)
    binding.curl_kwargs("mobilede")          # disponibil (prima observatie) -> tacut
    assert _warns(logs) == []
    rot._ip = None
    binding.curl_kwargs("mobilede")          # -> indisponibil: 1
    binding.curl_kwargs("mobilede")
    binding.curl_kwargs("mobilede")
    rot._ip = "192.168.8.123"
    binding.curl_kwargs("mobilede")          # -> disponibil din nou: 2
    binding.curl_kwargs("mobilede")
    assert len(_warns(logs)) == 2


def test_modemul_detine_ruta_default_warn_o_singura_data(monkeypatch, logs):
    _use(monkeypatch, ip="192.168.8.123")
    # aceeasi adresa sursa catre modem si catre internet = modemul e pe calea default
    monkeypatch.setattr(binding, "local_ip_towards", lambda target: "192.168.8.123")
    for _ in range(4):
        # kwargs se intorc in continuare: e WARN, nu refuz (fail-open consecvent)
        assert binding.curl_kwargs("mobilede") == {"interface": "192.168.8.123"}
    warns = [m for m in _warns(logs) if "ruta default" in m]
    assert len(warns) == 1


def test_ruta_default_ok_niciun_warn(monkeypatch, logs):
    _use(monkeypatch)
    for _ in range(3):
        binding.curl_kwargs("mobilede")
    assert _warns(logs) == []


# ── contoare ─────────────────────────────────────────────────────────────────────

def test_bind_state_numara(monkeypatch):
    _use(monkeypatch)
    binding.curl_kwargs("mobilede")
    binding.httpx_config("vinted")
    binding.curl_kwargs("olx")            # in afara listei -> unbound
    st = binding.bind_state()
    assert st["bound"] == 2 and st["unbound"] == 1
    assert st["ip"] == "192.168.8.123" and st["device"] == "usb0"


# ── wrapper-ul Vinted (httpx: transport inghetat la constructie) ─────────────────

def _fake_vinted_lib(monkeypatch, built):
    mod = types.ModuleType("vinted_scraper")

    class _FakeWrapper:
        def __init__(self, base, config=None):
            built.append(config)

    mod.VintedWrapper = _FakeWrapper
    monkeypatch.setitem(sys.modules, "vinted_scraper", mod)


def _fresh_vinted_module(monkeypatch):
    from app.services.radar import vinted_scraper as vs
    monkeypatch.setattr(vs, "_wrapper", None)
    monkeypatch.setattr(vs, "_wrapper_bind", None)
    return vs


def test_wrapper_nu_se_reconstruieste_cand_bind_key_e_acelasi(monkeypatch):
    built = []
    _fake_vinted_lib(monkeypatch, built)
    vs = _fresh_vinted_module(monkeypatch)
    _use(monkeypatch, device=None)
    w1 = vs._get_wrapper()
    w2 = vs._get_wrapper()
    assert w2 is w1 and len(built) == 1


def test_wrapper_reconstruit_cand_bind_key_se_schimba(monkeypatch):
    built = []
    _fake_vinted_lib(monkeypatch, built)
    vs = _fresh_vinted_module(monkeypatch)
    rot = _use(monkeypatch, device=None)
    w1 = vs._get_wrapper()
    rot._ip = "192.168.8.199"    # re-enumerare USB / alt DHCP
    w2 = vs._get_wrapper()
    assert w2 is not w1 and len(built) == 2


def test_wrapper_fara_binding_nu_primeste_config(monkeypatch):
    monkeypatch.setenv("MODEM_ROUTED_PLATFORMS", "")
    built = []
    _fake_vinted_lib(monkeypatch, built)
    vs = _fresh_vinted_module(monkeypatch)
    _use(monkeypatch)
    vs._get_wrapper()
    assert built == [None]       # `config` nu se trimite deloc
