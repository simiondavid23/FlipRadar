"""C-15 — watchdog de sănătate pentru scraperele Catalog (detecție blocaje la refresh preț).

Un magazin blocat (rate-limit, Cloudflare, schimbare de markup) tace: `refresh_price_from_source`
prinde excepțiile intern și întoarce None, ciclu după ciclu. `_refresh_all_scrapeable_products`
loghează per-produs și folosește prețul stocat, deci owner-ul nu primește niciun semnal agregat.
Watchdog-ul agregă PER MAGAZIN, peste toți userii și produsele, la finalul fiecărui ciclu complet
de refresh, și alertează la TRANZIȚII (intrare în `suspect` / revenire), nu la fiecare ciclu.

Semnal (UNUL singur, spre deosebire de RP-6 care are două): „rată de eșec" — magazin la care
TOATE refresh-urile din ciclu au întors None, cât timp măcar un alt magazin a întors un preț
(guard anti fals-pozitiv: dacă totul eșuează, probabil e net-ul, nu magazinul). Prag: 5 cicluri,
aliniat cu `_ZERO_STREAK_THRESHOLD` din RP-6. Nu există semnal separat de „excepții": scraper_service
înghite excepțiile și le transformă în None, deci eșecul e indistinct de „n-am găsit prețul".

Stare `suspect`: la atingerea pragului → o singură alertă WARN (live logs + Discord); cât e suspect
nu se mai alertează. Recovery: primul ciclu cu ≥1 preț preluat → alertă OK + reset streak + iese din
suspect. Magazin neatins într-un ciclu (fără surse pentru el) → streak-ul îngheață (nici incrementat,
nici resetat), consecvent cu RP-6 pe platforme nescanate.

Starea e IN MEMORIE (per proces) — se resetează la restart, ca la RP-6.
"""
from app.services.log_manager import log_manager
from app.models.radar_settings import RadarSettings
from app.services.radar.discord_service import send_system_alert


_FAIL_STREAK_THRESHOLD = 5  # cicluri consecutive fara niciun pret (cu alt magazin viu)

# ── Stare module-level (consecvent cu health_watchdog.py) ────────────────────────
_cycle_open: bool = False
_acc_ok: dict[str, int] = {}      # refresh-uri reusite (pret preluat) per magazin, ciclul curent
_acc_fail: dict[str, int] = {}    # refresh-uri esuate (None) per magazin, ciclul curent
_acc_scanned: set[str] = set()    # magazine atinse in ciclul curent
_fail_streak: dict[str, int] = {}
_suspect: set[str] = set()


_TEXT_DOWN = (
    "⚠️ Catalog — magazinul {s} pare blocat: {n} cicluri de refresh consecutive fără niciun "
    "preț preluat, cât timp alte magazine răspund. Verifică live logs."
)
_TEXT_RECOVERY = "✅ Catalog — magazinul {s} și-a revenit: prețuri preluate din nou."


def _reset_state() -> None:
    """Reset complet al starii module-level (folosit de teste)."""
    global _cycle_open
    _cycle_open = False
    _acc_ok.clear()
    _acc_fail.clear()
    _acc_scanned.clear()
    _fail_streak.clear()
    _suspect.clear()


def open_cycle() -> None:
    """Deschide un ciclu nou: goleste acumulatoarele."""
    global _cycle_open
    _acc_ok.clear()
    _acc_fail.clear()
    _acc_scanned.clear()
    _cycle_open = True


def note_refresh(source: str, success: bool) -> None:
    """Inregistreaza rezultatul unui refresh pentru `source` in ciclul curent.
    success = am preluat un pret. No-op daca niciun ciclu nu e deschis."""
    if not _cycle_open:
        return
    _acc_scanned.add(source)
    if success:
        _acc_ok[source] = _acc_ok.get(source, 0) + 1
    else:
        _acc_fail[source] = _acc_fail.get(source, 0) + 1


def close_cycle(db) -> None:
    """Evalueaza streak-urile la finalul ciclului si emite alerte la tranzitii.
    No-op daca niciun ciclu nu e deschis."""
    global _cycle_open
    if not _cycle_open:
        return

    any_alive = any(_acc_ok.get(s, 0) > 0 for s in _acc_scanned)
    for s in _acc_scanned:
        ok = _acc_ok.get(s, 0)
        fail = _acc_fail.get(s, 0)
        if ok > 0:
            # Sanatos: a intors macar un pret.
            if s in _suspect:
                _dispatch_alert(db, _TEXT_RECOVERY.format(s=s), "OK")
                _suspect.discard(s)
            _fail_streak[s] = 0
        elif fail > 0 and any_alive:
            # 0 reusite, dar chiar a fost incercat, iar alt magazin raspunde.
            _fail_streak[s] = _fail_streak.get(s, 0) + 1
            if s not in _suspect and _fail_streak[s] >= _FAIL_STREAK_THRESHOLD:
                _suspect.add(s)
                _dispatch_alert(db, _TEXT_DOWN.format(s=s, n=_fail_streak[s]), "WARN")
        # fail == 0 (magazin neatins efectiv) sau not any_alive (probabil net-ul):
        # streak-ul INGHEATA — nici resetat, nici incrementat.

    _acc_ok.clear()
    _acc_fail.clear()
    _acc_scanned.clear()
    _cycle_open = False


def _dispatch_alert(db, text: str, level: str) -> None:
    """level: 'WARN' (down) sau 'OK' (recovery). Emite in live logs si pe Discord.

    Live logs: intotdeauna. Discord: doar daca `db` nu e None (in teste e None) — catre
    webhook-urile distincte de alerte ale userilor. Catalog nu are canal de scan dedicat;
    un blocaj de magazin e relevant oricui primeste alerte de pret, fiindca exact alea
    inceteaza sa mai fie evaluate pe preturi proaspete. Best-effort per URL."""
    log_manager.emit("catalog", level, text)
    if db is None:
        return
    try:
        urls = {
            row[0] for row in db.query(RadarSettings.discord_webhook_alerts)
            .filter(RadarSettings.discord_webhook_alerts.isnot(None))
            .distinct().all()
            if row[0]
        }
    except Exception as exc:
        print(f"[Watchdog Catalog] Interogare audienta Discord esuata: {exc}")
        return
    for url in urls:
        try:
            send_system_alert(url, text)
        except Exception as exc:
            print(f"[Watchdog Catalog] Alerta Discord esuata: {exc}")
