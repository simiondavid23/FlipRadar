"""NET-5.3 — politica de declansare a rotatiei de IP.

Singurul loc care stie CAND merita rotit. Rotatorul stie CUM, clasificatorul stie CE
s-a intamplat, binding-ul stie PE UNDE iese traficul — niciunul nu decide. Aici se leaga.

DOUA REGULI CARE NU SE NEGOCIAZA
================================
1. O platforma din afara `MODEM_ROUTED_PLATFORMS` nu roteste NICIODATA. Traficul ei nu
   iese prin modem, deci un IP nou nu-i rezolva nimic — dar ar consuma cooldown-ul de
   600s si ar taia ~34s platformele care chiar sunt legate. Un 403 pe OLX ar sabota
   scanarea mobile.de.
2. Doar `BLOCKED` roteste. `RATE_LIMITED` e o fereastra de timp care se reseteaza
   singura (si cadenta e deja gestionata de throttle). `SITE_CHANGED` nu se repara cu
   alt IP, iar rotatia ar masca semnalul fix cand vrei sa-l vezi. `TRANSIENT` e CRITIC:
   rotatia insasi taie conexiunea ~34s, deci requesturile prinse in zbor cad cu eroare
   de retea — daca aia ar roti, o rotatie ar declansa-o pe urmatoarea, in cascada, pana
   la epuizarea bugetului orar.

Declansarea se auto-limiteaza: `rotate()` are deja cooldown 600s si plafon 5/ora, deci
majoritatea BLOCKED-urilor primesc `skipped_reason` si cad pe backoff-ul normal. Nu mai
e nevoie de un al doilea nivel de throttling aici.
"""
from typing import Optional

from app.services.network import binding
from app.services.network.rotator import NoopRotator, get_rotator


# Politica, nu `if`-uri imprastiate. Gol = implicit pentru orice platforma.
# Cheile sunt VALORILE lui Outcome (str Enum) — asa `triggers` nu depinde de
# `services.radar` la nivel de modul.
_DEFAULT_ROTATE_ON = frozenset({"blocked"})
_ROTATE_ON: dict[str, frozenset] = {}


def _log(level: str, message: str) -> None:
    try:
        from app.services.log_manager import log_manager
        log_manager.emit("network", level, message)
    except Exception:
        print(f"[{level}] triggers: {message}")


def rotate_for(platform: str, outcome) -> bool:
    """Roteste daca politica platformei o cere. Intoarce True DOAR daca s-a rotit si
    WanIPAddress chiar s-a schimbat — adica apelantul poate reincerca imediat pe alt IP.
    Nu arunca niciodata."""
    try:
        p = (platform or "").strip().lower()
        if p not in binding.routed_platforms():
            return False
        key = getattr(outcome, "value", outcome)
        if key not in _ROTATE_ON.get(p, _DEFAULT_ROTATE_ON):
            return False
        # Rotatie oprita din config: nici macar nu se CONTORIZEAZA. `rotate()` ar intoarce
        # oricum `ok=False`, dar `note_rotation` ar fi rulat deja si alertele ar spune
        # „dupa N rotatii de IP" fara sa se fi rotit nimic — iar `.env.example` livreaza
        # exact combinatia asta (ENABLED=false + ROUTED_PLATFORMS nevid).
        if isinstance(get_rotator(), NoopRotator):
            return False

        from app.services.radar import health_watchdog
        # INAINTE de rotatie: o rotatie esuata trebuie tot numarata, altfel contorul ar
        # spune „0 rotatii" fix cand rotatia e stricata.
        health_watchdog.note_rotation(p)

        result = get_rotator().rotate()
        # Tri-stare: `changed is None` inseamna „n-am putut compara WAN-ul", NU succes.
        # `if result.changed` ar fi corect azi din intamplare; `is True` e corect prin
        # constructie.
        if result.ok and result.changed is True:
            _reset_ip_reputation()
            return True
        return False
    except Exception as exc:
        _log("WARN", f"Rotatie la blocaj esuata ({type(exc).__name__}: {str(exc)[:100]})")
        return False


def _reset_ip_reputation() -> None:
    """Doar dupa o rotatie cu changed=True: blocajul era pe IP-ul VECHI.

    Importuri lazy — `triggers` nu depinde de `services.radar` la nivel de modul.
    Fiecare reset e independent: unul care crapa nu-l impiedica pe celalalt.
    """
    try:
        from app.services.radar import vinted_html
        vinted_html.reset_for_new_ip()
    except Exception as exc:
        _log("WARN", f"Reset stare Vinted esuat: {type(exc).__name__}")
    try:
        from app.services.radar import vinted_scraper
        vinted_scraper._invalidate_wrapper()
    except Exception as exc:
        _log("WARN", f"Invalidare wrapper Vinted esuata: {type(exc).__name__}")


def recover_data_if_link_up() -> bool:
    """NET-5.3 §7 — repara capcana 4, la BOOT. Intoarce True daca `available()` a rulat.

    Un proces mort intre `dataswitch=0` si `dataswitch=1` lasa modemul OFFLINE.
    `available()` repara asta prin `_recover_data_off()` — dar 5.2c a scos-o de pe calea
    per-request (facea 30s per request cu modemul absent), deci acum n-o mai cheama
    nimeni. Pana la NET-5.3 gaura era inaccesibila (nimic nu chema `rotate()`); etapa
    asta o face accesibila, deci compensarea intra in acelasi commit cu cauza.

    `available()` face I/O si poate dura ~30s daca modemul e configurat dar ABSENT —
    intr-un `lifespan` async asta ar intarzia pornirea si uvicorn n-ar mai deveni ready.
    Deci intai semnalul ieftin din 5.2c (ruta on-link catre MODEM_HOST) si abia daca
    link-ul e sus chemam `available()`. Atunci e sub o secunda.
    """
    try:
        rot = get_rotator()
        if binding._live_bind_ip(rot) is None:
            return False
        rot.available()
        return True
    except Exception as exc:
        _log("WARN", f"Recuperare date modem esuata ({type(exc).__name__})")
        return False
