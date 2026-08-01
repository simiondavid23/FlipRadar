"""FlipRadar - rotatie IP prin modem USB Huawei HiLink.

Modul OPTIONAL, dezactivat implicit. Majoritatea instalarilor nu au modem USB,
deci get_rotator() intoarce NoopRotator daca MODEM_ROTATION_ENABLED nu e "true".

DOUA METODE, PENTRU CA DEPINDE DE OPERATOR
==========================================
Masurat empiric pe acelasi E3372-325 / FW 3.0.3.61(H057SP11C983):

                     Orange (AS8953)      Digi (AS8708)
  dataswitch 5s      fara efect           -
  dataswitch 30s     fara efect (0/2)     FUNCTIONEAZA (5/5, ~34s)
  reboot             FUNCTIONEAZA (~45s)  nerulat (inutil)
  net/reconnect      nesuportat de firmware, pe ambele
  set_register       INTERZIS - a blocat modemul pe inregistrare manuala
  set_net_mode       INTERZIS - acelasi risc de stare nerestaurata

Acelasi hardware, rezultate opuse: e politica de operator. Orange leaga alocarea
de abonat peste dezactivarea contextului PDP; Digi realoca.

Implicit: dataswitch - mai ieftin, fara repornire fizica, fara re-enumerare USB.
Rezerva: reboot, folosit automat daca dataswitch nu mai schimba nimic.

DE CE SEMNALUL E WanIPAddress, NU IP-UL PUBLIC
==============================================
Pe Digi, IP-ul public DERIVA singur la cateva minute, fara nicio rotatie:
86.125.23.175 -> 86.125.25.175 cu WAN intern neatins. Un control pasiv de 4
minute a aratat WAN-ul fix 12/12 in timp ce publicul se muta.

Daca succesul s-ar masura pe IP-ul public, modulul ar raporta ocazional rotatii
care nu s-au intamplat, iar daca metoda ar inceta sa functioneze n-ai afla.
WanIPAddress se schimba doar cand contextul PDP chiar se reface.

PATRU CAPCANE INVATATE EMPIRIC
==============================
1. SESIUNE: biblioteca reincearca automat doar 125002 (LoginCsrf), NU 125003
   (WrongSessionToken). Un Connection reutilizat dupa o operatie care reseteaza
   sesiunea web ramane mort definitiv. => Connection NOU la fiecare operatie.

2. BIND IP: dupa repornire adaptorul USB se re-enumereaza (MAC nou observat) si
   DHCP poate da alta adresa. Un bind_ip cache-uit ar ramane pe un IP mort si
   toate scraperele legate la el ar esua tacit. => invalidare la repornire.

3. ASTEPTARE: ConnectionStatus=901 apare INAINTE ca traficul sa treaca efectiv.
   => se asteapta o masuratoare reusita, nu un flag.

4. DATE OPRITE: daca procesul moare intre dataswitch=0 si dataswitch=1, modemul
   ramane offline. => restaurare in finally cu reincercari, plus recuperare la
   pornire (available() porneste datele daca le gaseste oprite).

Contract public:
    get_rotator()                     -> singleton (Noop sau Huawei)
    rotator.available()               -> bool
    rotator.rotate(force=False)       -> RotationResult
    rotator.wait_if_rotating(timeout) -> bool, apelat de scrapere
    rotator.bind_ip()                 -> IP local pe interfata modemului
    rotator.bind_device()             -> numele interfetei (Linux; None pe Windows)
"""
from __future__ import annotations

import json as _json
import os
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Optional

DEFAULT_HOST = "192.168.8.1"
DEFAULT_USERNAME = "admin"

METHOD_DATASWITCH = "dataswitch"
METHOD_REBOOT = "reboot"
VALID_METHODS = (METHOD_DATASWITCH, METHOD_REBOOT)

# 30s masurat suficient pe Digi (5/5). 5s nu functiona nici acolo.
DEFAULT_PDP_DOWN_S = 30

# Dupa atatea rotatii consecutive care NU schimba WanIPAddress, se escaladeaza
# o data la reboot. Acopera scenariul in care operatorul schimba politica.
DEFAULT_ESCALATE_AFTER = 2

# dataswitch ~34s, reboot ~45s. La 5 rotatii/ora cu dataswitch: 2.8 min/ora
# downtime pe calea modemului. Un blocaj real nu se ridica mai repede oricum,
# iar rotatiile in rafala arata mai suspect decat blocajul initial.
DEFAULT_COOLDOWN_S = 600
DEFAULT_MAX_PER_HOUR = 5

REBOOT_SETTLE_S = 15
API_RETURN_TIMEOUT_S = 180
DATA_PATH_TIMEOUT_S = 120
DATA_PATH_POLL_S = 3.0
API_POLL_S = 5.0

IP_API_URL = "http://ip-api.com/json/?fields=query,as"
IPIFY_URL = "https://api.ipify.org"


def _log(level: str, message: str) -> None:
    """Emite in log_manager daca exista, altfel pe stdout (import lazy)."""
    try:
        from app.services.log_manager import log_manager
        log_manager.emit("network", level, message)
    except Exception:
        print(f"[{level}] network: {message}")


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


def _asn_key(raw: Optional[str]) -> Optional[str]:
    """'AS8708 RCS & RDS' -> 'AS8708'. Doar numarul e stabil.

    Campul `as` de la ip-api e text liber al unei terte parti: ziua in care descrierea
    operatorului se schimba, o comparatie verbatim ar respinge masuratori perfect
    valide si s-ar manifesta ca „rotatia nu mai merge", fara nimic in log.
    """
    if not raw:
        return None
    token = str(raw).strip().split()[0].upper()
    return token if token.startswith("AS") else None


def local_ip_towards(target: str, port: int = 80) -> Optional[str]:
    """IP-ul sursa pe care OS-ul l-ar folosi ca sa ajunga la target.

    Socket UDP neconectat efectiv: consulta tabela de rutare fara sa trimita
    pachete si fara drepturi de admin. Identic pe Windows si Linux, si imun la
    redenumirea interfetei (usb0 / eth1 / enx... / "Ethernet 6").
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(2)
        sock.connect((target, port))
        return sock.getsockname()[0]
    except Exception:
        return None
    finally:
        sock.close()


# ---------------------------------------------------------------------------


@dataclass
class Measurement:
    """IP-ul public vazut PRIN modem. Binding-ul e obligatoriu."""
    ip: Optional[str] = None
    asn: Optional[str] = None
    bind_ip: Optional[str] = None
    valid: bool = False
    reason: Optional[str] = None


@dataclass
class RotationResult:
    """`changed` se refera la WanIPAddress - singurul semnal de incredere.

    `public_changed` e informativ: pe unii operatori IP-ul public deriva singur,
    deci nu poate confirma singur ca rotatia a avut loc.
    """
    ok: bool
    changed: Optional[bool] = None       # WAN intern; None = nu s-a putut compara
    public_changed: Optional[bool] = None
    old_ip: Optional[str] = None         # public
    new_ip: Optional[str] = None
    old_wan: Optional[str] = None
    new_wan: Optional[str] = None
    method: Optional[str] = None
    duration_s: float = 0.0
    error: Optional[str] = None
    skipped_reason: Optional[str] = None

    def summary(self) -> str:
        if self.skipped_reason:
            return f"rotatie ignorata: {self.skipped_reason}"
        if not self.ok:
            return f"rotatie esuata: {self.error}"
        arrow = f"{self.old_ip or '?'} -> {self.new_ip or '?'}"
        if self.changed is None:
            verdict = "rezultat neconcludent"
        elif self.changed:
            verdict = "IP schimbat"
        else:
            verdict = "ACELASI IP (WAN nemodificat)"
        return (f"{verdict} ({arrow}) prin {self.method or '?'} "
                f"in {self.duration_s:.0f}s")


class Rotator:
    """Interfata comuna. Scraperele si scheduler-ul depind doar de asta."""

    def available(self) -> bool:
        raise NotImplementedError

    def rotate(self, force: bool = False) -> RotationResult:
        raise NotImplementedError

    def bind_ip(self) -> Optional[str]:
        return None

    def bind_device(self) -> Optional[str]:
        return None

    @property
    def disabled_reason(self) -> Optional[str]:
        """Motivul dezactivarii definitive, sau None. Citire de camp, fara I/O —
        `available()` face request-uri catre modem, deci nu e folosibila per-request."""
        return None

    def wait_if_rotating(self, timeout: float = 180.0) -> bool:
        return True


class NoopRotator(Rotator):
    """Implicit. Nu face nimic, nu esueaza niciodata zgomotos."""

    def available(self) -> bool:
        return False

    def rotate(self, force: bool = False) -> RotationResult:
        return RotationResult(ok=False, skipped_reason="rotatie dezactivata")


# ---------------------------------------------------------------------------


class HuaweiHilinkRotator(Rotator):
    """Rotatie prin dataswitch (implicit) sau repornire. Vezi docstring modul."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        username: str = DEFAULT_USERNAME,
        password: Optional[str] = None,
        cooldown_s: int = DEFAULT_COOLDOWN_S,
        max_per_hour: int = DEFAULT_MAX_PER_HOUR,
        bind_ip_override: Optional[str] = None,
        method: str = METHOD_DATASWITCH,
        pdp_down_s: int = DEFAULT_PDP_DOWN_S,
        escalate_after: int = DEFAULT_ESCALATE_AFTER,
        expected_asn: Optional[str] = None,
    ) -> None:
        if method not in VALID_METHODS:
            raise ValueError(
                f"metoda necunoscuta: {method}. Valide: {', '.join(VALID_METHODS)}")
        self.host = host
        self.username = username
        self.password = password
        self.cooldown_s = cooldown_s
        self.max_per_hour = max_per_hour
        self.method = method
        self.pdp_down_s = pdp_down_s
        self.escalate_after = escalate_after
        self._bind_ip_override = bind_ip_override

        self._lock = threading.RLock()
        self._idle = threading.Event()
        self._idle.set()  # setat = nu rotim; scraperele trec liber

        self._disabled_reason: Optional[str] = None
        self._last_rotation_at: float = 0.0
        self._history: Deque[float] = deque(maxlen=64)
        self._bind_ip_cache: Optional[str] = None
        self._bind_device_cache: Optional[str] = None
        # Setat din mediu => auto-seedarea din _measure() nu mai are ce face. Fara el,
        # garda se calibreaza din PRIMA masuratoare reusita, si daca aceea a scurs pe
        # alta interfata ramane calibrata gresit definitiv.
        self._expected_asn: Optional[str] = _asn_key(expected_asn) or None
        self._consecutive_no_change: int = 0

    # -- sesiune -----------------------------------------------------------

    def _connect(self, fatal: bool = True) -> Any:
        """Connection NOU de fiecare data - vezi capcana 1 din docstring."""
        from huawei_lte_api.Client import Client
        from huawei_lte_api.Connection import Connection
        from huawei_lte_api.exceptions import (
            LoginErrorInvalidCredentialsException,
            LoginErrorUsernamePasswordOverrunException,
        )

        url = f"http://{self.host}/"

        # Multe stick-uri HiLink nu cer deloc autentificare.
        try:
            client = Client(Connection(url, timeout=15))
            client.device.information()
            return client
        except Exception:
            pass

        try:
            client = Client(Connection(
                url, username=self.username,
                password=self.password or DEFAULT_USERNAME, timeout=15))
            client.device.information()
            return client
        except LoginErrorUsernamePasswordOverrunException as exc:
            # Fatal chiar si in retry: reincercarea adanceste lockout-ul.
            self._disable("modemul a activat lockout dupa incercari esuate")
            raise RuntimeError(self._disabled_reason) from exc
        except LoginErrorInvalidCredentialsException as exc:
            self._disable("credentiale gresite pentru modem (MODEM_PASSWORD)")
            raise RuntimeError(self._disabled_reason) from exc
        except Exception:
            if not fatal:
                raise
            raise

    def _try_connect(self) -> Optional[Any]:
        try:
            return self._connect(fatal=False)
        except RuntimeError:
            raise  # lockout / credentiale: propaga, nu inghiti
        except Exception:
            return None

    @property
    def disabled_reason(self) -> Optional[str]:
        """Read-only: se seteaza doar prin `_disable()` (lockout de modem sau
        credentiale gresite)."""
        return self._disabled_reason

    def _disable(self, reason: str) -> None:
        self._disabled_reason = reason
        _log("ERROR", f"Rotatie IP dezactivata pana la restart: {reason}")

    # -- disponibilitate + recuperare --------------------------------------

    def available(self) -> bool:
        if self._disabled_reason:
            return False
        try:
            client = self._try_connect()
        except RuntimeError:
            return False
        if client is None:
            return False
        self._recover_data_off(client)
        return True

    def _recover_data_off(self, client: Any) -> None:
        """Daca un proces anterior a murit intre dataswitch=0 si =1, modemul a
        ramas offline. Se repara aici, la prima verificare de disponibilitate.
        """
        try:
            state = client.dial_up.mobile_dataswitch()
        except Exception:
            return  # firmware fara endpoint sau eroare tranzitorie
        if str(state.get("dataswitch")) != "0":
            return
        _log("WARN", "Modem: datele erau oprite (rotatie intrerupta?), le pornesc")
        self._force_data_on()

    def _force_data_on(self, tries: int = 4) -> bool:
        """Porneste datele, cu sesiune noua la fiecare incercare.

        Ultima linie de aparare: daca esueaza, modemul ramane fara internet.
        De aceea reincearca, si de aceea logheaza zgomotos la esec.
        """
        for attempt in range(1, tries + 1):
            try:
                client = self._connect(fatal=False)
                client.dial_up.set_mobile_dataswitch(dataswitch=1)
                return True
            except RuntimeError:
                raise
            except Exception as exc:
                _log("WARN", f"Modem: pornire date, incercarea {attempt}/{tries} "
                             f"a esuat ({type(exc).__name__})")
                time.sleep(4)
        _log("ERROR", "Modem: NU am putut porni datele. Modemul e probabil "
                      "offline. Verifica interfata web sau reintrodu stick-ul.")
        return False

    # -- bind IP -----------------------------------------------------------

    def bind_ip(self) -> Optional[str]:
        """IP local pe interfata modemului, pentru curl_cffi interface=."""
        if self._bind_ip_override:
            return self._bind_ip_override
        if self._bind_ip_cache:
            return self._bind_ip_cache
        self._bind_ip_cache = local_ip_towards(self.host)
        return self._bind_ip_cache

    def bind_device(self) -> Optional[str]:
        """Numele interfetei modemului. None pe Windows (libcurl nu accepta nume de
        interfata acolo) si None daca nu se poate rezolva. Cache langa bind_ip,
        invalidat odata cu el.

        Pe Linux, IP-ul singur nu ajunge: cautarea in tabela de rutare e dupa
        destinatie, adresa sursa nu participa la alegerea rutei. De aceea pe Pi e
        nevoie de SO_BINDTODEVICE, care cere NUMELE interfetei.
        """
        if os.name == "nt":
            return None
        if self._bind_device_cache:
            return self._bind_device_cache
        ip = self.bind_ip()
        if not ip:
            return None
        # `fcntl` nu exista pe Windows: importul la nivel de modul ar face rotator.py
        # neimportabil acolo si ar pica toate testele existente. Deci import IN CORP.
        try:
            import fcntl
            import struct
        except ImportError:
            return None
        _SIOCGIFADDR = 0x8915
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for _idx, name in socket.if_nameindex():
                try:
                    addr = socket.inet_ntoa(fcntl.ioctl(
                        sock.fileno(), _SIOCGIFADDR,
                        struct.pack("256s", name[:15].encode()))[20:24])
                except OSError:
                    continue
                if addr == ip:
                    self._bind_device_cache = name
                    return name
        except Exception:
            return None
        finally:
            sock.close()
        return None

    def invalidate_bind_ip(self) -> None:
        """Sterge cache-ul. OBLIGATORIU dupa repornire - vezi capcana 2.

        Goleste si numele interfetei: dupa repornire adaptorul se re-enumereaza si
        poate primi alt nume de la udev, nu doar alta adresa.
        """
        self._bind_ip_cache = None
        self._bind_device_cache = None

    # -- masuratoare -------------------------------------------------------

    def _measure(self) -> Measurement:
        """IP public PRIN modem. Fara binding valid nu exista masuratoare."""
        bind = self.bind_ip()
        if not bind:
            return Measurement(valid=False,
                               reason="fara IP local pe interfata modemului")
        try:
            from curl_cffi import requests as creq
        except ImportError:
            return Measurement(bind_ip=bind, valid=False,
                               reason="curl_cffi indisponibil")

        kwargs = {"timeout": 10, "impersonate": "chrome131", "interface": bind}
        ip = asn = None
        try:
            resp = creq.get(IP_API_URL, **kwargs)
            if resp.status_code == 200:
                data = _json.loads(resp.text)
                ip, asn = data.get("query"), data.get("as")
        except Exception:
            pass
        if not ip:
            try:
                resp = creq.get(IPIFY_URL, **kwargs)
                if resp.status_code == 200 and len(resp.text.strip()) < 64:
                    ip = resp.text.strip()
            except Exception:
                pass

        if not ip:
            return Measurement(bind_ip=bind, valid=False,
                               reason="niciun serviciu nu a raspuns prin modem")

        # Garda anti-scurgere: ASN diferit inseamna ca cererea a iesit pe alta
        # interfata, deci masuratoarea nu e despre modem. Comparatia se face pe NUMARUL
        # AS, nu pe descrierea operatorului (text liber de la ip-api) - vezi _asn_key.
        measured = _asn_key(asn)
        if self._expected_asn and measured and measured != self._expected_asn:
            return Measurement(ip=ip, asn=asn, bind_ip=bind, valid=False,
                               reason=f"ASN diferit ({asn}) - scurgere pe alta cale")

        if measured and not self._expected_asn:
            self._expected_asn = measured
        return Measurement(ip=ip, asn=asn, bind_ip=bind, valid=True)

    def _wait_data_path(self, timeout: float = DATA_PATH_TIMEOUT_S) -> Measurement:
        """Asteapta o masuratoare reusita - testul real ca traficul trece."""
        start = time.monotonic()
        last = Measurement(valid=False, reason="timeout")
        while time.monotonic() - start < timeout:
            last = self._measure()
            if last.valid:
                return last
            time.sleep(DATA_PATH_POLL_S)
        return last

    def _wait_api_back(self, timeout: float = API_RETURN_TIMEOUT_S) -> Any:
        """Asteapta ca interfata web sa revina dupa repornire."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            time.sleep(API_POLL_S)
            self.invalidate_bind_ip()
            if not self.bind_ip():
                continue
            client = self._try_connect()
            if client is not None:
                _log("INFO", f"Modem: API revenit dupa {time.monotonic()-start:.0f}s")
                return client
        raise RuntimeError("modemul nu a revenit dupa repornire")

    def _read_wan(self) -> Optional[str]:
        """WanIPAddress - semnalul de incredere pentru 'rotatia a avut loc'."""
        try:
            client = self._connect(fatal=False)
            return client.device.information().get("WanIPAddress")
        except RuntimeError:
            raise
        except Exception:
            return None

    # -- pauza pentru scrapere --------------------------------------------

    def wait_if_rotating(self, timeout: float = 180.0) -> bool:
        """Blocheaza cat timp o rotatie e in curs. True = liber sa continui."""
        return self._idle.wait(timeout)

    # -- rate limiting -----------------------------------------------------

    def _throttle_reason(self) -> Optional[str]:
        now = time.monotonic()
        if self._last_rotation_at:
            elapsed = now - self._last_rotation_at
            if elapsed < self.cooldown_s:
                return f"cooldown activ, mai sunt {int(self.cooldown_s - elapsed)}s"
        cutoff = now - 3600
        recent = [t for t in self._history if t > cutoff]
        if len(recent) >= self.max_per_hour:
            return f"buget orar epuizat ({self.max_per_hour} rotatii/ora)"
        return None

    # -- cele doua metode --------------------------------------------------

    def _apply_dataswitch(self) -> None:
        """Opreste contextul PDP, il tine jos, il reporneste.

        Restaurarea e in finally: daca ceva pica intre cele doua apeluri, modemul
        ar ramane offline. _force_data_on deschide sesiune noua - dupa 30s
        tokenul poate fi expirat (capcana 1).
        """
        client = self._connect()
        client.dial_up.set_mobile_dataswitch(dataswitch=0)
        try:
            time.sleep(self.pdp_down_s)
        finally:
            self._force_data_on()

    def _apply_reboot(self) -> None:
        from huawei_lte_api.enums.device import ControlModeEnum

        client = self._connect()
        try:
            client.device.set_control(ControlModeEnum.REBOOT)
        except Exception as exc:
            # Modemul poate pleca inainte sa raspunda - normal la repornire.
            _log("INFO", f"Modem: comanda de repornire, "
                         f"{type(exc).__name__} (asteptat)")
        # Adaptorul se re-enumereaza: cache-ul de bind devine invalid ACUM.
        self.invalidate_bind_ip()
        time.sleep(REBOOT_SETTLE_S)
        self._wait_api_back()

    # -- orchestrare -------------------------------------------------------

    def _effective_method(self) -> str:
        """Escaladeaza la reboot daca dataswitch nu mai schimba WAN-ul.

        Acopera scenariul in care operatorul schimba politica: fara escaladare,
        modulul ar continua sa rateze tacit.
        """
        if (self.method == METHOD_DATASWITCH
                and self._consecutive_no_change >= self.escalate_after):
            _log("WARN", f"Modem: {self._consecutive_no_change} rotatii fara "
                         f"schimbare de WAN, escaladez la repornire")
            return METHOD_REBOOT
        return self.method

    def rotate(self, force: bool = False) -> RotationResult:
        with self._lock:
            if self._disabled_reason:
                return RotationResult(ok=False, skipped_reason=self._disabled_reason)
            if not force:
                reason = self._throttle_reason()
                if reason:
                    return RotationResult(ok=False, skipped_reason=reason)

            method = self._effective_method()
            self._idle.clear()  # scraperele legate la modem se opresc aici
            started = time.monotonic()
            try:
                return self._do_rotate(started, method)
            finally:
                self._idle.set()
                self._last_rotation_at = time.monotonic()
                self._history.append(self._last_rotation_at)

    def _do_rotate(self, started: float, method: str) -> RotationResult:
        wan_before = self._read_wan()
        before = self._measure()
        if not before.valid:
            _log("WARN", f"Modem: stare initiala nemasurabila ({before.reason})")

        try:
            if method == METHOD_REBOOT:
                self._apply_reboot()
            else:
                self._apply_dataswitch()
        except RuntimeError as exc:
            return RotationResult(ok=False, method=method, old_ip=before.ip,
                                  old_wan=wan_before,
                                  duration_s=time.monotonic() - started,
                                  error=str(exc))
        except Exception as exc:
            return RotationResult(ok=False, method=method, old_ip=before.ip,
                                  old_wan=wan_before,
                                  duration_s=time.monotonic() - started,
                                  error=f"{type(exc).__name__}: {exc}")

        after = self._wait_data_path()
        wan_after = self._read_wan()
        duration = time.monotonic() - started

        if not after.valid:
            return RotationResult(ok=False, method=method, old_ip=before.ip,
                                  old_wan=wan_before, new_wan=wan_after,
                                  duration_s=duration,
                                  error=f"internetul nu a revenit ({after.reason})")

        # WAN-ul e semnalul de incredere. Publicul deriva singur pe unii
        # operatori, deci nu poate confirma singur ca rotatia a avut loc.
        changed: Optional[bool]
        if wan_before and wan_after:
            changed = wan_before != wan_after
        else:
            changed = None

        if changed is True:
            self._consecutive_no_change = 0
        elif changed is False:
            self._consecutive_no_change += 1

        public_changed: Optional[bool]
        if before.valid and after.valid:
            public_changed = before.ip != after.ip
        else:
            public_changed = None

        result = RotationResult(
            ok=True, changed=changed, public_changed=public_changed,
            old_ip=before.ip, new_ip=after.ip,
            old_wan=wan_before, new_wan=wan_after,
            method=method, duration_s=duration)
        _log("INFO", f"Modem: {result.summary()}")
        if changed is False and public_changed is True:
            _log("WARN", "Modem: IP public diferit dar WAN identic - "
                         "deriva de operator, nu rotatie reala")
        return result


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------

_instance: Optional[Rotator] = None
_instance_lock = threading.Lock()


def build_rotator() -> Rotator:
    """Construieste rotatorul din variabilele de mediu. Fara singleton."""
    if not _env_bool("MODEM_ROTATION_ENABLED", False):
        return NoopRotator()
    return HuaweiHilinkRotator(
        host=os.environ.get("MODEM_HOST", "").strip() or DEFAULT_HOST,
        username=os.environ.get("MODEM_USERNAME", "").strip() or DEFAULT_USERNAME,
        password=os.environ.get("MODEM_PASSWORD", "").strip() or None,
        cooldown_s=_env_int("MODEM_ROTATION_COOLDOWN_S", DEFAULT_COOLDOWN_S),
        max_per_hour=_env_int("MODEM_ROTATION_MAX_PER_HOUR", DEFAULT_MAX_PER_HOUR),
        bind_ip_override=os.environ.get("MODEM_BIND_IP", "").strip() or None,
        method=(os.environ.get("MODEM_ROTATION_METHOD", "").strip().lower()
                or METHOD_DATASWITCH),
        pdp_down_s=_env_int("MODEM_PDP_DOWN_S", DEFAULT_PDP_DOWN_S),
        escalate_after=_env_int("MODEM_ESCALATE_AFTER", DEFAULT_ESCALATE_AFTER),
        expected_asn=os.environ.get("MODEM_EXPECTED_ASN", "").strip() or None,
    )


def get_rotator() -> Rotator:
    """Singleton - o singura instanta per proces."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = build_rotator()
    return _instance


def reset_rotator() -> None:
    """Reconstruieste la urmatorul get_rotator(). Pentru teste si reconfigurare."""
    global _instance
    with _instance_lock:
        _instance = None
