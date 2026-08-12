"""NET-5.2 — binding selectiv per platforma.

Traficul platformelor dintr-o ALLOWLIST iese prin modem; restul, pe conexiunea
principala. Nu declanseaza nicio rotatie (aia e 5.3), doar alege calea de iesire.

CONTRACT: dict gol inseamna „nimic schimbat"
===========================================
`curl_kwargs` / `httpx_config` intorc `{}` pentru ORICE motiv — platforma nu e in
allowlist, `MODEM_ROTATION_ENABLED=false`, modemul indisponibil, fara IP local, sau
`wait_if_rotating` expirat. Un `**{}` la finalul unui apel existent nu schimba nimic,
deci integrarea e reversibila PRIN CONFIG: `MODEM_ROUTED_PLATFORMS=` gol readuce
comportamentul de dinainte de NET-5, fara revert de cod. Asta e kill-switch-ul.

ALLOWLIST, nu blocklist
=======================
Ce nu e in lista nu se leaga. `olx` (logat) si `facebook` sunt excluse intentionat:
ambele merg pe cookie de sesiune, iar un cookie care apare de pe IP-uri diferite e
semnatura de sesiune furata si duce la checkpoint pe cont.

DE CE `wait_if_rotating` SE APELEAZA AICI
=========================================
Nu in scrapere, nu in radar_scanner. SCHED-1: cele 8 platforme ruleaza in joburi
APScheduler PARALELE, iar `max_instances=1` acopera doar acelasi job — deci o rotatie
ceruta de mobile.de prinde jobul Vinted in zbor. O pauza per ciclu ar fi prea grosiera;
una per request e corecta si e automata pentru orice platforma adaugata ulterior in
allowlist. Cost zero cand nu rotim: `_idle` e un Event setat, iar `.wait()` pe un event
setat intoarce imediat.

FAIL-OPEN, DAR ZGOMOTOS EXACT O DATA
====================================
Bind indisponibil => request-ul pleaca pe conexiunea principala. Dar „binding omis
tacit" e o clasa de defect care a produs deja o concluzie falsa, deci omiterea trebuie
sa fie vizibila: WARN DOAR LA TRANZITIE (un WARN per request umple jurnalele si devine
invizibil; zero WARN-uri repeta defectul), plus contoare in `bind_state()`.
"""
import os
import socket
import threading
from typing import Optional

from app.services.network.rotator import (
    DEFAULT_HOST, NoopRotator, get_rotator, local_ip_towards,
)


_PUBLIC_PROBE = "1.1.1.1"
_WAIT_TIMEOUT_S = 180.0

# Pe Windows constanta nu exista in `socket`; valoarea Linux e 25. Definita necontitionat
# ca ramura POSIX sa fie testabila si de pe Windows (monkeypatch pe os.name).
_SO_BINDTODEVICE = getattr(socket, "SO_BINDTODEVICE", 25)

_lock = threading.Lock()
_state: dict = {"bound": 0, "unbound": 0, "ip": None, "device": None}


def _log(level: str, message: str) -> None:
    """Emite in log_manager daca exista, altfel pe stdout (import lazy, ca in rotator)."""
    try:
        from app.services.log_manager import log_manager
        log_manager.emit("network", level, message)
    except Exception:
        print(f"[{level}] binding: {message}")


# ── stare de tranzitie ───────────────────────────────────────────────────────────

def _note_available(ok: bool, reason: str = "") -> None:
    """WARN doar cand disponibilitatea se SCHIMBA. Prima observatie „disponibil" e
    tacuta: nu anuntam ca totul e in regula la pornire."""
    with _lock:
        prev = _state.get("available")
        if prev == ok:
            return
        _state["available"] = ok
        first = prev is None
    if ok:
        if not first:
            _log("WARN", "Binding modem: DISPONIBIL din nou - requesturile platformelor "
                         "din allowlist se leaga la modem")
    else:
        _log("WARN", f"Binding modem: INDISPONIBIL ({reason}) - requesturile pleaca pe "
                     "conexiunea principala (fail-open)")


def _note_flag(key: str, on: bool, msg_on: str, msg_off: str) -> None:
    """WARN la intrarea in starea proasta, INFO la iesire. Prima observatie „bine" e
    tacuta."""
    with _lock:
        prev = _state.get(key)
        if prev == on:
            return
        _state[key] = on
        first = prev is None
    if on:
        _log("WARN", msg_on)
    elif not first:
        _log("INFO", msg_off)


# ── API public ───────────────────────────────────────────────────────────────────

def _rotation_disabled() -> bool:
    """True cand rotatia e OPRITA DIN CONFIG (NoopRotator).

    „Rotatia e dezactivata" nu e o anomalie; „rotatia e activata dar modemul a
    disparut" este. Doar a doua merita un WARN — un WARN fals livrat implicit (majoritatea
    instalarilor n-au modem USB) erodeaza increderea in tot jurnalul.

    Verificarea e pe TIP, nu pe `available()`: ambele intorc False si acolo nu se mai
    poate distinge „oprit din config" de „modem disparut". Nu se recitesc variabilele de
    mediu aici — `build_rotator()` ramane singura sursa de adevar.
    """
    try:
        return isinstance(get_rotator(), NoopRotator)
    except Exception:
        return False   # nu putem decide -> lasam calea normala sa raporteze zgomotos


def _on_modem_link(src: str, host: str) -> bool:
    """Sursa e pe LINK-ul modemului? LAN-ul HiLink e un /24 (implicit 192.168.8.0/24)."""
    return src.rsplit(".", 1)[0] == host.rsplit(".", 1)[0]


def _live_bind_ip(rot) -> Optional[str]:
    """IP-ul cu care chiar ne putem lega, verificat NECACHE-UIT la fiecare apel.
    None = adaptorul modemului nu mai e acolo.

    NET-5.2c — masurat: `available()` face I/O HTTP catre modem (doua `_try_connect`,
    `timeout=15` fiecare), deci cu modemul scos costa 30s PER REQUEST. La 6 platforme ×
    3 reincercari × paginare, o pana de modem nu degrada scanerul, il OPREA — adica exact
    opusul motivului pentru care s-a ales fail-open. `local_ip_towards` consulta tabela de
    rutare pe un socket UDP neconectat: nu trimite pachete, nu deschide sesiune, nu cere
    drepturi, si nu poate astepta un timeout de retea.

    DAR „a intors ceva" NU inseamna „modemul e viu" (masurat pe Windows): cand adaptorul
    dispare, `192.168.8.1` nu mai are ruta on-link, cade pe ruta DEFAULT si intoarce
    adresa WiFi. Daca ne-am opri la „non-None", am trece de verificare, ne-am lega la
    `bind_ip()` CACHE-UIT (un IP mort) si curl ar arunca `InterfaceError` errno 10049 in
    scraper — fail-CLOSED din greseala, opusul deciziei luate. Deci sursa trebuie sa fie
    pe link-ul modemului.

    `bind_ip()` nu se foloseste ca DETECTOR (e cache-uit), doar ca sursa a adresei — si
    se re-verifica fata de ruta proaspata: la replug, adaptorul se re-enumereaza si poate
    primi alta adresa, iar cache-ul ar ramane pe cea moarta (capcana 2 din handover).
    Invalidarea nu costa I/O.
    """
    host = getattr(rot, "host", None) or DEFAULT_HOST
    src = local_ip_towards(host)
    if not src or not _on_modem_link(src, host):
        return None
    ip = rot.bind_ip()
    if ip and ip != src:
        try:
            rot.invalidate_bind_ip()
        except Exception:
            pass
        ip = rot.bind_ip()
    return ip or None


def modem_link_up(rot=None) -> bool:
    """True daca ruta catre MODEM_HOST iese pe LINK-ul modemului.

    Ieftin: doar cautare de ruta, fara I/O catre modem si fara cache (vezi `_live_bind_ip`).
    Invelis boolean peste acelasi semnal — folosit de `triggers.recover_data_if_link_up`
    ca sa nu plateasca 30s de `available()` cand modemul e configurat dar absent.
    """
    return _live_bind_ip(rot if rot is not None else get_rotator()) is not None


# NET-6 — platforme care nu au voie sa iasa prin modem, indiferent de .env:
# merg pe cookie de sesiune, iar acelasi cookie de pe IP-uri diferite =
# semnatura de sesiune furata -> checkpoint pe cont (NET-5, sectiunea 3.2).
# DE REEVALUAT daca Facebook trece pe scraping logat-out: atunci nu mai
# exista sesiune de protejat si rotatia devine dezirabila.
_NEVER_ROUTED = frozenset({"facebook", "olx"})


def routed_platforms() -> frozenset[str]:
    """Allowlist-ul din mediu, citit LA APEL (nu la import) ca sa fie reconfigurabil.

    NET-6: `_NEVER_ROUTED` se scade DUR din allowlist. Pana acum politica traia doar in
    valoarea din .env; de cand R3 a cablat `report_outcome("facebook", BLOCKED)`, o
    configurare gresita chiar ar declansa rotatie pe un cont logat. Filtrarea e pe
    valorile deja normalizate (strip + lower), deci si "Facebook " e prinsa.

    Aceasta functie e SINGURUL cititor al variabilei de mediu, iar ambii apelanti
    (`_bind_target` de aici si `triggers.rotate_for`) trec prin ea — deci filtrul
    acopera si legarea la interfata, si rotatia.
    """
    raw = os.environ.get("MODEM_ROUTED_PLATFORMS", "")
    cerute = frozenset(p.strip().lower() for p in raw.split(",") if p.strip())
    interzise = cerute & _NEVER_ROUTED
    # Acelasi mecanism de tranzitie ca restul modulului: WARN o singura data la
    # intrarea in configurarea gresita, INFO cand e reparata (fara zgomot pe calea
    # normala — prima observatie „curat" e tacuta).
    _note_flag(
        "never_routed", bool(interzise),
        f"MODEM_ROUTED_PLATFORMS contine platforme INTERZISE ({', '.join(sorted(interzise))}) "
        "- ignorate: merg pe cookie de sesiune, iar rotatia de IP le-ar duce in checkpoint "
        "pe cont (NET-6). Scoate-le din .env.",
        "MODEM_ROUTED_PLATFORMS nu mai contine platforme interzise",
    )
    return cerute - _NEVER_ROUTED


def _bind_target(platform: str) -> tuple[Optional[str], Optional[str]]:
    """(ip, device) daca platforma trebuie legata, altfel (None, None).

    Aici se face `wait_if_rotating` si toate verificarile de stare. Nu arunca niciodata.
    """
    if (platform or "").strip().lower() not in routed_platforms():
        return None, None          # in afara allowlist-ului: nicio stare, niciun WARN
    try:
        rot = get_rotator()
        # Intai asteptam o eventuala rotatie in curs, apoi intrebam de disponibilitate:
        # in timpul rotatiei available() poate fi fals tranzitoriu.
        if not rot.wait_if_rotating(_WAIT_TIMEOUT_S):
            _note_available(False, f"rotatie in curs peste {_WAIT_TIMEOUT_S:.0f}s")
            return None, None
        # Dezactivare definitiva (lockout de modem / credentiale gresite): citire de
        # camp, gratis. `available()` NU se apeleaza aici - vezi _modem_alive.
        reason = getattr(rot, "disabled_reason", None)
        if reason:
            _note_available(False, reason)
            return None, None
        ip = _live_bind_ip(rot)
        if not ip:
            _note_available(False, "fara ruta on-link catre modem (adaptor absent?)")
            return None, None
        device = rot.bind_device()
    except Exception as exc:
        # Textul excepției, nu doar tipul: cauza cea mai probabila e o greseala in .env
        # (ex. MODEM_ROTATION_METHOD scris gresit -> ValueError din build_rotator), iar
        # un mesaj care spune doar „indisponibil" trimite omul sa caute la modem.
        _note_available(False, f"{type(exc).__name__}: {str(exc)[:120]}")
        return None, None

    _note_available(True)
    _note_flag(
        "degraded", os.name != "nt" and not device,
        "Binding modem: nu pot rezolva numele interfetei - raman pe bind doar pe IP, "
        "care pe Linux probabil NU schimba ruta de iesire",
        "Binding modem: numele interfetei rezolvat din nou",
    )
    # Topologia se poate inversa singura (Ethernet scos, WiFi cazut) si atunci tot
    # design-ul se intoarce pe dos TACUT. Aceeasi adresa sursa catre modem si catre
    # internet => modemul e pe calea default => binding-ul selectiv nu are efect util.
    _note_flag(
        "default_via_modem", ip == local_ip_towards(_PUBLIC_PROBE),
        "Binding modem: modemul DETINE ruta default - binding-ul selectiv nu are efect "
        "util (tot traficul iese oricum prin modem). Ridica metrica interfetei modemului.",
        "Binding modem: ruta default nu mai trece prin modem - binding selectiv activ",
    )
    with _lock:
        _state["ip"] = ip
        _state["device"] = device
    return ip, device


def _bump(bound: bool) -> None:
    with _lock:
        _state["bound" if bound else "unbound"] += 1


def curl_kwargs(platform: str) -> dict:
    """kwargs pentru curl_cffi. `{}` = nimic schimbat (vezi docstring modul)."""
    if _rotation_disabled():
        return {}      # nici WARN, nici contoare: n-a fost o cerere de binding ratata
    ip, device = _bind_target(platform)
    if not ip:
        _bump(False)
        return {}
    _bump(True)
    if os.name == "nt":
        # libcurl NU accepta nume de interfata pe Windows (vezi CURLOPT_INTERFACE).
        return {"interface": ip}
    if device:
        return {"interface": f"ifhost!{device}!{ip}"}
    return {"interface": ip}       # degradat - WARN-ul a plecat deja din _bind_target


def httpx_config(platform: str) -> dict:
    """kwargs pentru httpx.HTTPTransport. `{}` = nimic schimbat."""
    if _rotation_disabled():
        return {}
    ip, device = _bind_target(platform)
    if not ip:
        _bump(False)
        return {}
    _bump(True)
    cfg: dict = {"local_address": ip}
    if os.name != "nt" and device:
        cfg["socket_options"] = [
            (socket.SOL_SOCKET, _SO_BINDTODEVICE, device.encode())
        ]
    return cfg


def bind_state() -> dict:
    """Contoare pentru linia de sumar a ciclului + ce s-a folosit efectiv."""
    with _lock:
        return {
            "bound": _state["bound"],
            "unbound": _state["unbound"],
            "ip": _state.get("ip"),
            "device": _state.get("device"),
        }


def reset_state() -> None:
    """Reset complet (teste si reconfigurare)."""
    with _lock:
        _state.clear()
        _state.update({"bound": 0, "unbound": 0, "ip": None, "device": None})
