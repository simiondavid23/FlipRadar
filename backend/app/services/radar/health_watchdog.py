"""RP-6 — watchdog de sănătate pentru scraperele Radar Piață (detecție blocaje).

Un scraper blocat (rate-limit, ban de IP, schimbare de markup) tace: returnează 0
rezultate ciclu după ciclu. Watchdog-ul agregă, PER PLATFORMĂ, peste toți userii și
keyword-urile, la finalul fiecărui ciclu al platformei (`run_radar_scan_platform`), și
alertează la TRANZIȚII (intrare în `suspect` / revenire), nu la fiecare ciclu.

SCHED-1: fiecare platformă are jobul ei, deci ciclurile sunt PER PLATFORMĂ și se
suprapun în timp — mai multe pot fi deschise simultan (`_open_platforms`). Guard-ul
anti fals-pozitiv nu se mai poate uita „în ciclul curent" după o altă platformă vie
(ciclul curent are o singură platformă), așa că folosește `_last_alive_at`: ultima
dată când FIECARE platformă a returnat >0, cu o fereastră de `_ALIVE_WINDOW_S`.

Semnale:
  • „zero": platformă scanată care a returnat 0 rezultate BRUTE (înainte de orice
    filtrare), cât timp măcar o altă platformă a returnat >0 în ultimele
    `_ALIVE_WINDOW_S` secunde (guard anti fals-pozitiv: dacă TOTUL e 0, probabil e
    net-ul, nu platforma). Prag: 5 cicluri.
  • „erori": scraperul a crăpat (except din `_run_scraper`) în cicluri consecutive.
    Prag: 3 cicluri (fără guard any_alive — o excepție e semnal puternic).

Stare `suspect`: la atingerea unui prag → o singură alertă WARN (live logs + Discord);
cât e suspect nu se mai alertează. Recovery: primul ciclu cu >0 rezultate → alertă OK
+ reset ambele streak-uri + iese din suspect. Platformă nescanată într-un ciclu (fără
keyword-uri active pe ea) → streak-urile îngheață (nici incrementate, nici resetate).

Comportament acceptat (documentat): la o PANĂ TOTALĂ (toate platformele pe erori),
după 3 cicluri vor pleca alerte per-platformă — zgomotos o dată, dar corect: ceva chiar
e stricat. Scan-now (`_scan_user` direct) nu deschide cicluri → note_* sunt no-op; dacă
se suprapune peste ciclul deschis al platformei respective, rezultatele lui intră în
agregat (date reale).

Starea e IN MEMORIE (per proces) — se resetează la restart (decizie aprobată, fără DB).
La pornire, `_last_alive_at` e gol: până când o platformă închide un ciclu cu rezultate,
streak-urile de „zero" îngheață (conservator — evită alertele false la boot).
"""
import time

from app.services.log_manager import log_manager
from app.models.radar_keyword import RadarKeyword
from app.models.radar_settings import RadarSettings
from app.services.radar.discord_service import send_system_alert


_ZERO_STREAK_THRESHOLD = 5   # cicluri consecutive cu 0 rezultate (cu alta platforma vie)
_ERROR_STREAK_THRESHOLD = 3  # cicluri consecutive cu exceptii de scraper
_ALIVE_WINDOW_S = 30 * 60    # SCHED-1 — cat timp o platforma ramane "vie" pentru guard


def _now() -> float:
    """Ceas monotonic — injectabil in teste (conventia din vinted_html)."""
    return time.monotonic()


# ── Stare module-level (nu clasa, consecvent cu _enrich_counters/_cycle_counter) ──
_open_platforms: set[str] = set()    # SCHED-1 — cicluri deschise (mai multe simultan)
_acc_results: dict[str, int] = {}   # rezultate brute acumulate in ciclul curent, per platforma
_acc_errors: dict[str, int] = {}    # exceptii in ciclul curent, per platforma
_acc_scanned: set[str] = set()      # platforme atinse in ciclul curent
_last_alive_at: dict[str, float] = {}  # SCHED-1 — ultimul ciclu cu rezultate >0, per platforma
_zero_streak: dict[str, int] = {}
_error_streak: dict[str, int] = {}
_suspect: set[str] = set()


_TEXT_DOWN_ZERO = (
    "⚠️ Radar Piață — platforma {p} pare blocată: {n} cicluri consecutive fără niciun "
    "rezultat, în timp ce alte platforme returnează normal. Verifică live logs."
)
_TEXT_DOWN_ERR = (
    "⚠️ Radar Piață — platforma {p} pare blocată: scraperul a crăpat în {n} cicluri "
    "consecutive. Verifică live logs."
)
_TEXT_RECOVERY = "✅ Radar Piață — platforma {p} și-a revenit: rezultate primite din nou."


def _reset_state() -> None:
    """Reset complet al starii module-level (folosit de teste)."""
    _open_platforms.clear()
    _acc_results.clear()
    _acc_errors.clear()
    _acc_scanned.clear()
    _last_alive_at.clear()
    _zero_streak.clear()
    _error_streak.clear()
    _suspect.clear()


def open_cycle(platform: str) -> None:
    """Deschide un ciclu nou pentru `platform`: goleste acumulatoarele EI.
    Ciclurile altor platforme, deschise in paralel, raman intacte."""
    _acc_results.pop(platform, None)
    _acc_errors.pop(platform, None)
    _acc_scanned.discard(platform)
    _open_platforms.add(platform)


def note_results(platform: str, count: int) -> None:
    """Inregistreaza `count` rezultate brute pentru `platform` in ciclul ei.
    No-op daca platforma nu are un ciclu deschis (ex. scan-now)."""
    if platform not in _open_platforms:
        return
    _acc_scanned.add(platform)
    _acc_results[platform] = _acc_results.get(platform, 0) + count


def note_error(platform: str) -> None:
    """Inregistreaza o exceptie de scraper pentru `platform` in ciclul ei.
    No-op daca platforma nu are un ciclu deschis."""
    if platform not in _open_platforms:
        return
    _acc_scanned.add(platform)
    _acc_errors[platform] = _acc_errors.get(platform, 0) + 1


def close_cycle(db, platform: str) -> None:
    """Evalueaza streak-urile platformei la finalul ciclului EI si emite alerte la
    tranzitii. No-op daca platforma nu are un ciclu deschis.

    Platforma deschisa dar neatinsa (job fara keyword-uri pe ea) nu e evaluata:
    streak-urile ingheata, exact ca inainte pentru o platforma nescanata."""
    if platform not in _open_platforms:
        return
    p = platform
    if p in _acc_scanned:
        now = _now()
        r = _acc_results.get(p, 0)
        e = _acc_errors.get(p, 0)
        if r > 0:
            # Sanatos: marcam platforma vie INAINTE de recovery, apoi reset streak-uri.
            _last_alive_at[p] = now
            if p in _suspect:
                _dispatch_alert(db, _TEXT_RECOVERY.format(p=p), "OK")
                _suspect.discard(p)
            _zero_streak[p] = 0
            _error_streak[p] = 0
        else:
            # 0 rezultate: streak zero doar daca o ALTA platforma a fost vie recent
            # (guard fals-pozitiv: daca TOTUL tace, probabil e net-ul, nu platforma).
            any_alive = any(now - t <= _ALIVE_WINDOW_S
                            for q, t in _last_alive_at.items() if q != p)
            if any_alive:
                _zero_streak[p] = _zero_streak.get(p, 0) + 1
            if e > 0:
                _error_streak[p] = _error_streak.get(p, 0) + 1
            else:
                _error_streak[p] = 0
            if p not in _suspect:
                zs = _zero_streak.get(p, 0)
                es = _error_streak.get(p, 0)
                if es >= _ERROR_STREAK_THRESHOLD:
                    _suspect.add(p)
                    _dispatch_alert(db, _TEXT_DOWN_ERR.format(p=p, n=es), "WARN")
                elif zs >= _ZERO_STREAK_THRESHOLD:
                    _suspect.add(p)
                    _dispatch_alert(db, _TEXT_DOWN_ZERO.format(p=p, n=zs), "WARN")

    _acc_results.pop(p, None)
    _acc_errors.pop(p, None)
    _acc_scanned.discard(p)
    _open_platforms.discard(p)


def _dispatch_alert(db, text: str, level: str) -> None:
    """level: 'WARN' (down) sau 'OK' (recovery). Emite in live logs si pe Discord.

    Live logs: intotdeauna. Discord: doar daca `db` nu e None (in teste e None) —
    catre webhook-urile distincte ale userilor activi cu cel putin un keyword activ.
    Fara filtrare pe platforma la audienta (RadarKeyword.platform e nullable) — un
    blocaj de platforma e relevant oricui foloseste aplicatia. Best-effort per URL."""
    log_manager.emit("radar", level, text)
    if db is None:
        return
    try:
        urls = {
            row[0] for row in db.query(RadarSettings.discord_webhook_all)
            .join(RadarKeyword, RadarKeyword.user_id == RadarSettings.user_id)
            .filter(RadarKeyword.is_active == True, RadarSettings.discord_webhook_all.isnot(None))  # noqa: E712
            .distinct().all()
            if row[0]
        }
    except Exception as exc:
        print(f"[Watchdog] Interogare audienta Discord esuata: {exc}")
        return
    for url in urls:
        try:
            send_system_alert(url, text)
        except Exception as exc:
            print(f"[Watchdog] Alerta Discord esuata: {exc}")
