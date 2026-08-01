"""FlipRadar - rotatie IP prin repornirea modemului USB Huawei HiLink.

Modul OPTIONAL, dezactivat implicit. Majoritatea instalarilor nu au modem USB,
deci get_rotator() intoarce NoopRotator daca MODEM_ROTATION_ENABLED nu e "true".

DE CE REPORNIRE SI NU mobile-dataswitch
=======================================
Masurat empiric pe E3372-325 / FW 3.0.3.61(H057SP11C983) / Orange RO:

  mobile-dataswitch 5s   -> IP intern SI public neschimbate
  mobile-dataswitch 30s  -> IP intern SI public neschimbate
  net/reconnect          -> nesuportat de firmware (-1: Unknown)
  set_register           -> a lasat modemul blocat pe inregistrare manuala
  set_net_mode           -> acelasi risc de stare nerestaurata
  REPORNIRE              -> IP public schimbat, 5 IP-uri distincte / 5 rotatii,
                            4 subretele /24 distincte, ~45s downtime

Oprirea contextului PDP nu declanseaza realocare indiferent cat o tii: modemul
ramane inregistrat pe retea si primeste inapoi aceeasi alocare. Repornirea face
detach complet (echivalentul modului avion), iar operatorul aloca IP nou.

Repornirea are si cel mai sigur mod de esec: daca procesul moare la mijloc,
modemul revine singur intr-o stare curata. set_register / set_net_mode lasa
setari nerestaurate - inacceptabil pe o masina fara operator (Pi, 24/7).

TREI CAPCANE INVATATE EMPIRIC
=============================
1. SESIUNE: biblioteca reincearca automat doar 125002 (LoginCsrf), NU 125003
   (WrongSessionToken). Un Connection reutilizat dupa o operatie care reseteaza
   sesiunea web ramane mort definitiv. => Connection NOU la fiecare operatie.

2. BIND IP: dupa repornire adaptorul USB se re-enumereaza (MAC nou observat) si
   DHCP poate da alta adresa. Un bind_ip cache-uit ar ramane pe un IP mort si
   toate scraperele legate la el ar esua tacit. => invalidare la fiecare rotatie.

3. ASTEPTARE: ConnectionStatus=901 apare INAINTE ca traficul sa treaca efectiv.
   => se asteapta o masuratoare reusita, nu un flag.

Contract public:
    get_rotator()                     -> singleton (Noop sau Huawei)
    rotator.available()               -> bool
    rotator.rotate(force=False)       -> RotationResult
    rotator.wait_if_rotating(timeout) -> bool, apelat de scrapere
    rotator.bind_ip()                 -> IP local pe interfata modemului
"""
from __future__ import annotations

import os
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Optional

DEFAULT_HOST = "192.168.8.1"
DEFAULT_USERNAME = "admin"

# Repornirea costa ~45s. Cooldown-ul e mai lung decat la varianta dataswitch:
# un blocaj real nu se ridica mai repede de atat, iar rotatiile in rafala arata
# mai suspect decat blocajul initial.
DEFAULT_COOLDOWN_S = 600
DEFAULT_MAX_PER_HOUR = 4

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
    ok: bool
    changed: Optional[bool] = None  # None = nu s-a putut compara
    old_ip: Optional[str] = None
    new_ip: Optional[str] = None
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
            verdict = "ACELASI IP"
        return f"{verdict} ({arrow}) in {self.duration_s:.0f}s"


class Rotator:
    """Interfata comuna. Scraperele si scheduler-ul depind doar de asta."""

    def available(self) -> bool:
        raise NotImplementedError

    def rotate(self, force: bool = False) -> RotationResult:
        raise NotImplementedError

    def bind_ip(self) -> Optional[str]:
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
    """Rotatie prin repornirea modemului. Vezi docstring-ul modulului."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        username: str = DEFAULT_USERNAME,
        password: Optional[str] = None,
        cooldown_s: int = DEFAULT_COOLDOWN_S,
        max_per_hour: int = DEFAULT_MAX_PER_HOUR,
        bind_ip_override: Optional[str] = None,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.cooldown_s = cooldown_s
        self.max_per_hour = max_per_hour
        self._bind_ip_override = bind_ip_override

        self._lock = threading.RLock()
        self._idle = threading.Event()
        self._idle.set()  # setat = nu rotim; scraperele trec liber

        self._disabled_reason: Optional[str] = None
        self._last_rotation_at: float = 0.0
        self._history: Deque[float] = deque(maxlen=64)
        self._bind_ip_cache: Optional[str] = None
        self._expected_asn: Optional[str] = None

    # -- sesiune -----------------------------------------------------------

    def _connect(self, fatal: bool = True) -> Any:
        """Connection NOU de fiecare data - vezi capcana 1 din docstring.

        Costul unui obiect nou e neglijabil fata de operatiile de retea, iar
        reutilizarea duce la 125003 pe tot restul sesiunii.
        """
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

    def _disable(self, reason: str) -> None:
        self._disabled_reason = reason
        _log("ERROR", f"Rotatie IP dezactivata pana la restart: {reason}")

    # -- disponibilitate ---------------------------------------------------

    def available(self) -> bool:
        if self._disabled_reason:
            return False
        try:
            return self._try_connect() is not None
        except RuntimeError:
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

    def invalidate_bind_ip(self) -> None:
        """Sterge cache-ul. OBLIGATORIU dupa repornire - vezi capcana 2."""
        self._bind_ip_cache = None

    # -- masuratoare -------------------------------------------------------

    def _measure(self) -> Measurement:
        """IP public PRIN modem. Fara binding valid nu exista masuratoare.

        Un fallback tacit pe ruta default ar masura cu totul alta retea si ar
        produce comparatii false.
        """
        bind = self.bind_ip()
        if not bind:
            return Measurement(valid=False,
                               reason="fara IP local pe interfata modemului")
        try:
            from curl_cffi import requests as creq
        except ImportError:
            return Measurement(bind_ip=bind, valid=False,
                               reason="curl_cffi indisponibil")

        kwargs = {"timeout": 10, "impersonate": "chrome110", "interface": bind}
        ip = asn = None
        try:
            import json as _json
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
        # interfata, deci masuratoarea nu e despre modem.
        if self._expected_asn and asn and asn != self._expected_asn:
            return Measurement(ip=ip, asn=asn, bind_ip=bind, valid=False,
                               reason=f"ASN diferit ({asn}) - scurgere pe alta cale")

        if asn and not self._expected_asn:
            self._expected_asn = asn
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

    # -- rotatia -----------------------------------------------------------

    def rotate(self, force: bool = False) -> RotationResult:
        with self._lock:
            if self._disabled_reason:
                return RotationResult(ok=False, skipped_reason=self._disabled_reason)
            if not force:
                reason = self._throttle_reason()
                if reason:
                    return RotationResult(ok=False, skipped_reason=reason)

            self._idle.clear()  # scraperele legate la modem se opresc aici
            started = time.monotonic()
            try:
                return self._do_rotate(started)
            finally:
                self._idle.set()
                self._last_rotation_at = time.monotonic()
                self._history.append(self._last_rotation_at)

    def _do_rotate(self, started: float) -> RotationResult:
        from huawei_lte_api.enums.device import ControlModeEnum

        before = self._measure()
        if not before.valid:
            _log("WARN", f"Modem: stare initiala nemasurabila ({before.reason})")

        try:
            client = self._connect()
        except RuntimeError as exc:
            return RotationResult(ok=False, old_ip=before.ip,
                                  duration_s=time.monotonic() - started,
                                  error=str(exc))
        except Exception as exc:
            return RotationResult(ok=False, old_ip=before.ip,
                                  duration_s=time.monotonic() - started,
                                  error=f"conectare: {type(exc).__name__}: {exc}")

        try:
            client.device.set_control(ControlModeEnum.REBOOT)
        except Exception as exc:
            # Modemul poate pleca inainte sa raspunda - normal la repornire.
            _log("INFO", f"Modem: comanda de repornire, "
                         f"{type(exc).__name__} (asteptat)")

        # Adaptorul se re-enumereaza: cache-ul de bind devine invalid ACUM.
        self.invalidate_bind_ip()
        time.sleep(REBOOT_SETTLE_S)

        try:
            self._wait_api_back()
        except RuntimeError as exc:
            return RotationResult(ok=False, old_ip=before.ip,
                                  duration_s=time.monotonic() - started,
                                  error=str(exc))

        after = self._wait_data_path()
        duration = time.monotonic() - started

        if not after.valid:
            return RotationResult(ok=False, old_ip=before.ip,
                                  duration_s=duration,
                                  error=f"internetul nu a revenit ({after.reason})")

        changed: Optional[bool]
        if before.valid and after.valid:
            changed = before.ip != after.ip
        else:
            changed = None  # NU False: o masuratoare esuata nu e una negativa

        result = RotationResult(ok=True, changed=changed, old_ip=before.ip,
                                new_ip=after.ip, duration_s=duration)
        _log("INFO", f"Modem: {result.summary()}")
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
