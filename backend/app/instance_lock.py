"""LAUNCH-2 — o singura instanta FlipRadar pe aceeasi baza de date.

INCIDENTUL. Pe 01.09, sub contentie SQLite, proba de sanatate a launcher-ului
(`_flipradar_at`, timeout 1s, care atinge DB-ul prin `/api/health`) a expirat.
`_choose_port` a citit de aici „la 8000 nu e FlipRadar" si a pornit un AL DOILEA
server pe 8001, peste acelasi `flipradar.db`. Al doilea scriitor a agravat exact
contentia care il pornise, si „database is locked" a cazut in lant peste scannere,
coada Discord si `/api/health`.

LAUNCH-1 a inchis calea prin shortcut (`--viewer` nu mai porneste server niciodata).
Ramaneau doua: `launcher.py` fara `--viewer`, si `uvicorn` pornit de mana cu
`DATABASE_URL`/`FLIPRADAR_DATA_DIR` catre productie. Nicio verificare de port nu le
prinde pe amandoua — a doua nici macar nu se leaga de acelasi port.

DE CE UN LOCK DE OS, NU UN FISIER CU PID. Un PID-file trebuie curatat de cineva:
daca procesul moare urat (kill, pana de curent, crash), ramane pe disc si urmatoarea
pornire fie e blocata gresit, fie trebuie sa verifice daca PID-ul mai traieste — o
verificare care se insala la reciclarea PID-urilor. Un lock exclusiv de OS se
elibereaza SINGUR cand procesul moare, oricum ar muri. Nu exista stare de curatat.

DE CE LANGA BAZA DE DATE. Resursa aparata e DB-ul, nu directorul de date: doua
instante cu `FLIPRADAR_DATA_DIR` diferit dar acelasi `DATABASE_URL` se lovesc corect,
iar doua instante pe baze diferite nu se deranjeaza — ceea ce e exact ce vrem cand
dezvoltarea ruleaza langa productie.

DE CE LA IMPORT, NU IN LIFESPAN. `main.py` ruleaza `create_all()` si
`run_migrations()` LA IMPORT, deci pana la lifespan al doilea proces a scris deja in
baza. Lock-ul trebuie luat inaintea lor.

PE WINDOWS, `msvcrt.locking` blocheaza octetul 0 pentru ORICE alt handle: cat timp
lock-ul e tinut, fisierul nu poate fi nici citit, nici sters din afara (verificat).
E chiar comportamentul dorit — sfatul tiparit mai jos, de a sterge fisierul, merge
doar cand nu-l mai tine nimeni, adica exact cand e sigur de facut.

DE CE SE SARE IN TESTE. Suita ruleaza cu `FLIPRADAR_TESTING=1` si cu un fisier SQLite
unic per proces (uuid in nume), deci izolarea exista deja; sub xdist, mai multe
procese importa `app.main` in paralel si s-ar bloca reciproc degeaba.
"""
import atexit
import os
from pathlib import Path

# Handle-ul se tine intr-o variabila de MODUL, nu local: lock-ul traieste cat fisierul
# ramane deschis, deci un handle care iese din scope si e colectat ar ridica lock-ul in
# tacere, la un moment imprevizibil.
_handle = None


def cale_lock(database_url: str, data_dir) -> Path:
    """Fisierul de lock pentru o configuratie data.

    Pentru SQLite, langa fisierul bazei (`<db>.lock`), rezolvat absolut: URL-ul poate
    fi relativ (`sqlite:///./flipradar.db`), iar lock-ul trebuie sa cada langa acelasi
    fisier pe care il va deschide si SQLAlchemy. Pentru orice alt dialect nu exista un
    fisier langa care sa stea, deci cade in directorul de date.
    """
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        fisier = Path(database_url[len(prefix):]).expanduser().resolve()
        # Sufix ADAUGAT, nu inlocuit: `with_suffix` ar transforma `flipradar.db` in
        # `flipradar.lock` si doua baze diferite din acelasi director (`a.db`, `a.sql`)
        # ar ajunge sa se bata pe acelasi lock.
        return Path(str(fisier) + ".lock")
    return Path(data_dir) / "flipradar.lock"


def ia_lock(cale: Path):
    """Handle-ul unui lock exclusiv NEBLOCANT pe `cale`, sau None daca e deja luat.

    Deschiderea e `a+`: creeaza fisierul daca lipseste si NU trunchiaza unul existent
    (trunchierea ar sterge PID-ul instantei care chiar detine lock-ul).
    """
    try:
        Path(cale).parent.mkdir(parents=True, exist_ok=True)
        handle = open(cale, "a+", encoding="utf-8")
    except OSError:
        return None

    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, PermissionError):
        handle.close()
        return None

    # PID-ul e INFORMATIV — pentru cine se uita in fisier cand ceva nu merge. Nicio
    # decizie nu se ia pe baza lui; lock-ul insusi e singurul arbitru.
    try:
        handle.seek(0, os.SEEK_END)
        handle.write("%d\n" % os.getpid())
        handle.flush()
    except OSError:
        pass
    return handle


def elibereaza_lock(handle) -> None:
    """Ridica lock-ul si inchide fisierul. Tolerant: rulat din `atexit`, o exceptie
    aici ar fi zgomot la o inchidere care oricum se termina."""
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (OSError, PermissionError, ValueError):
        pass
    try:
        handle.close()
    except OSError:
        pass


def activ() -> bool:
    """False sub pytest sau cand `FLIPRADAR_INSTANCE_LOCK` il opreste explicit."""
    if os.getenv("FLIPRADAR_TESTING") == "1":
        return False
    return (os.getenv("FLIPRADAR_INSTANCE_LOCK") or "1").strip().lower() not in (
        "0", "false", "no", "off")


def asigura_instanta_unica() -> None:
    """Ia lock-ul sau opreste procesul. Se apeleaza din `main.py`, la import."""
    global _handle
    if not activ():
        return

    from app.config import DATA_DIR, DATABASE_URL

    cale = cale_lock(DATABASE_URL, DATA_DIR)
    handle = ia_lock(cale)
    if handle is None:
        print("[Instanta] O alta instanta FlipRadar ruleaza deja pe aceeasi baza de "
              f"date ({cale}). Opresc pornirea. Daca esti sigur ca nu ruleaza nimic, "
              "sterge fisierul .lock.")
        raise SystemExit(3)

    _handle = handle
    atexit.register(elibereaza_lock, handle)
