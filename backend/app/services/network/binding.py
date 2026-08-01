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

from app.services.network.rotator import NoopRotator, get_rotator, local_ip_towards


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


def routed_platforms() -> frozenset[str]:
    """Allowlist-ul din mediu, citit LA APEL (nu la import) ca sa fie reconfigurabil."""
    raw = os.environ.get("MODEM_ROUTED_PLATFORMS", "")
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


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
        if not rot.available():
            _note_available(False, "modemul nu e disponibil")
            return None, None
        ip = rot.bind_ip()
        if not ip:
            _note_available(False, "fara IP local pe interfata modemului")
            return None, None
        device = rot.bind_device()
    except Exception as exc:
        _note_available(False, f"{type(exc).__name__}")
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
