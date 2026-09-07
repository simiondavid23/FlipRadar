# -*- coding: utf-8 -*-
"""TZ-2 — sonda de verificare DUPA deploy. STRICT read-only: doar SELECT.

Doua probe, deliberat diferite, fiindca una singura minte:

  1. ABSOLUTA — `max(coloana)` fata de `datetime('now','localtime')`. Raspunde direct la
     „ora din baza e ora sistemului?", dar are sens DOAR pe coloane scrise recent: un
     maxim vechi de o saptamana e la fel de departe de ambele ceasuri, iar sonda ar
     raporta „GRESIT" si pentru o coloana perfect convertita. De aceea verdictul se da
     doar sub `_PRAG_PROSPETIME_H`; altfel scrie explicit „date vechi".

  2. REGISTRU — `schema_migrations` contine numele celor trei backfill-uri? Raspuns
     exact, independent de vechimea datelor, si singurul care spune daca o migrare s-a
     intrerupt la mijloc (marcaje `tz2p:` ramase). Asta e proba pe care se poate conta.

Rulare (in venv, din backend/):
    venv\\Scripts\\python.exe sonda_TZ2_verif.py [cale_catre.db]

Fara argument, ia baza din DATABASE_URL / app.paths.
"""
import io
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_PRAG_PROSPETIME_H = 6.0

# (tabel, coloana, asteptat) — cate una din fiecare grup, plus doua martore.
_ABSOLUTE = [
    ("deals", "last_seen_at", "local"),              # grup A — pagina Deals
    ("shop_scan_state", "last_scan_at", "local"),    # grup A — „ULTIMUL SCAN"
    ("price_history", "recorded_at", "local"),       # grup B — retail
    ("discord_queue", "created_at", "local"),        # grup C
    ("radar_listings", "found_at", "local"),         # TZ-1, martor: era deja local
    ("fb_scan_state", "next_due_at", "utc"),         # exceptie FB, martor: ramane UTC
]

def _baza() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    url = os.getenv("DATABASE_URL") or ""
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app.paths import data_dir           # noqa: E402
    return os.path.join(str(data_dir()), "flipradar.db")


def _dt(v):
    try:
        return datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def _absoluta(con, local, utc) -> int:
    print("── 1. proba ABSOLUTA (are sens doar pe date proaspete) ──")
    print(f"{'tabel.coloana':40} {'max(coloana)':24} {'varsta':>8}  verdict")
    print("-" * 92)
    rau = 0
    for tabel, coloana, asteptat in _ABSOLUTE:
        eticheta = f"{tabel}.{coloana}"
        try:
            v = con.execute(f"SELECT MAX({coloana}) FROM {tabel}").fetchone()[0]
        except sqlite3.OperationalError:
            print(f"{eticheta:40} {'(tabel/coloana lipsa)':24} {'—':>8}  —")
            continue
        m = _dt(v)
        if m is None:
            print(f"{eticheta:40} {'(gol)':24} {'—':>8}  —")
            continue
        varsta = (local - m).total_seconds() / 3600
        d_local, d_utc = abs((m - local).total_seconds()), abs((m - utc).total_seconds())
        aproape = "local" if d_local <= d_utc else "utc"
        if varsta > _PRAG_PROSPETIME_H:
            print(f"{eticheta:40} {str(v)[:24]:24} {varsta:7.1f}h  date vechi — fara verdict")
            continue
        ok = aproape == asteptat
        rau += 0 if ok else 1
        print(f"{eticheta:40} {str(v)[:24]:24} {varsta:7.1f}h  "
              f"{'OK' if ok else 'GRESIT'} (mai aproape de {aproape}, asteptat {asteptat})")
    return rau


def _registru(con) -> int:
    """Proba EXACTA: backfill-ul si-a scris numele in `schema_migrations`?

    Inlocuieste o idee care nu functiona: comparasem, pe acelasi rand, `last_checked_at`
    cu `found_at` (despre care stim ca e local de la TZ-1), sperand ca diferenta sa arate
    offsetul masinii cand conversia lipseste. Nu arata: cele doua coloane masoara momente
    DIFERITE (inserarea vs ultima reverificare), deci diferenta lor e timp scurs real —
    pe `real_estate_listings` iesea 22,5 h pe o baza perfect convertita. Registrul, in
    schimb, raspunde fara ambiguitate si fara sa depinda de date.
    """
    print()
    print("── 2. proba pe REGISTRU (exacta, nu depinde de date) ──")
    rau = 0
    for nume in ("tz1_ore_locale", "tz2a_feed", "tz2b_retail", "tz2c_rest"):
        gasit = con.execute("SELECT 1 FROM schema_migrations WHERE migration_name = ?",
                            (nume,)).fetchone() is not None
        rau += 0 if gasit else 1
        print(f"   {nume:20} {'APLICATA' if gasit else 'LIPSA — backfill-ul nu a rulat'}")
    ramase = con.execute("SELECT COUNT(*) FROM schema_migrations "
                         "WHERE migration_name LIKE 'tz2p:%'").fetchone()[0]
    if ramase:
        rau += 1
        print(f"   {'marcaje de progres':20} {ramase} ramase — o migrare s-a intrerupt "
              f"la mijloc si se va relua la urmatoarea pornire")
    return rau


def main() -> int:
    cale = _baza()
    if not os.path.exists(cale):
        print(f"BAZA LIPSA: {cale}")
        return 2
    con = sqlite3.connect(f"file:{cale}?mode=ro", uri=True)   # READ-ONLY, explicit
    try:
        local = _dt(con.execute("SELECT datetime('now','localtime')").fetchone()[0])
        utc = _dt(con.execute("SELECT datetime('now')").fetchone()[0])
        offset_h = (local - utc).total_seconds() / 3600
        print(f"baza       : {cale}")
        print(f"ceas local : {local}   ceas UTC: {utc}   offset masina: {offset_h:+.0f} h\n")
        if abs(offset_h) < 0.5:
            print("ATENTIE: masina ruleaza pe UTC — cele doua ceasuri coincid, deci\n"
                  "         sonda NU poate distinge o coloana convertita de una neconvertita.\n")
        rau = _absoluta(con, local, utc) + _registru(con)
        print("\nREZULTAT: " + ("TOTUL E PE ORA LOCALA" if not rau
                                else f"{rau} verificari GRESITE — vezi mai sus"))
        return 1 if rau else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
