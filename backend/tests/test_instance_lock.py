"""LAUNCH-2 — lock-ul exclusiv care refuza a doua instanta pe aceeasi baza.

Testele lucreaza DOAR pe modul, nu prin `app.main`: importul lui ar lua lock-ul real
al bazei de test si ar interfera cu restul suitei (si cu xdist, unde mai multe procese
importa in paralel).
"""
import os
from pathlib import Path

from app import instance_lock


# ── T1: exclusivitatea ───────────────────────────────────────────────────────

def test_al_doilea_lock_pe_acelasi_fisier_esueaza(tmp_path):
    """Al doilea `ia_lock` pe acelasi fisier intoarce None, iar dupa eliberare
    fisierul redevine disponibil.

    Se testeaza din ACELASI proces, cu doua deschideri separate. Merge pe amandoua
    platformele si din acelasi proces: `msvcrt.locking` blocheaza o zona a fisierului
    pentru orice alt handle, iar `fcntl.flock` leaga lock-ul de descrierea de fisier
    deschis, iar doua `open()` produc descrieri diferite. Nu e nevoie de subprocess.
    """
    cale = tmp_path / "flipradar.db.lock"

    primul = instance_lock.ia_lock(cale)
    assert primul is not None, "primul lock trebuie sa reuseasca"
    try:
        assert instance_lock.ia_lock(cale) is None, "al doilea trebuie refuzat"
    finally:
        instance_lock.elibereaza_lock(primul)

    dupa = instance_lock.ia_lock(cale)
    assert dupa is not None, "dupa eliberare, lock-ul se poate lua din nou"
    instance_lock.elibereaza_lock(dupa)


def test_lock_ul_creeaza_fisierul_si_scrie_pid(tmp_path):
    """Fisierul se creeaza daca lipseste, iar PID-ul ajunge in el. PID-ul e
    INFORMATIV: nicio decizie nu se ia pe baza lui."""
    cale = tmp_path / "sub" / "director" / "flipradar.db.lock"
    assert not cale.exists()

    handle = instance_lock.ia_lock(cale)
    assert handle is not None
    # Pe Windows fisierul nu poate fi citit cat lock-ul e tinut, deci il eliberam
    # inainte de a-l inspecta.
    instance_lock.elibereaza_lock(handle)

    assert cale.exists()
    assert str(os.getpid()) in cale.read_text(encoding="utf-8")


def test_eliberarea_e_toleranta_la_none():
    """`elibereaza_lock(None)` nu ridica: e inregistrata in `atexit`, iar o exceptie
    acolo ar fi zgomot la o inchidere care oricum se termina."""
    instance_lock.elibereaza_lock(None)


# ── T2: unde cade fisierul de lock ───────────────────────────────────────────

def test_cale_lock_pentru_sqlite_e_langa_baza(tmp_path):
    """SQLite -> `<fisier-baza>.lock`, langa baza. Resursa aparata e BAZA: doua
    instante cu `DATA_DIR` diferit dar acelasi `DATABASE_URL` trebuie sa se loveasca."""
    db = tmp_path / "flipradar.db"
    url = "sqlite:///" + db.as_posix()

    assert (instance_lock.cale_lock(url, Path("/alt/director"))
            == Path(str(db) + ".lock"))


def test_cale_lock_sufixul_se_adauga_nu_se_inlocuieste(tmp_path):
    """`a.db` si `a.sql` din acelasi director dau lock-uri DIFERITE. Cu
    `with_suffix` ar fi dat amandoua `a.lock` si s-ar fi blocat reciproc."""
    unu = instance_lock.cale_lock("sqlite:///" + (tmp_path / "a.db").as_posix(), tmp_path)
    doi = instance_lock.cale_lock("sqlite:///" + (tmp_path / "a.sql").as_posix(), tmp_path)

    assert unu != doi
    assert unu.name == "a.db.lock" and doi.name == "a.sql.lock"


def test_cale_lock_pentru_alt_dialect_cade_in_data_dir(tmp_path):
    """Fara fisier de baza langa care sa stea, lock-ul merge in directorul de date."""
    assert (instance_lock.cale_lock("postgresql://user@host/flipradar", tmp_path)
            == tmp_path / "flipradar.lock")


# ── T3: comutatorul ──────────────────────────────────────────────────────────

def test_activ_e_false_sub_pytest(monkeypatch):
    """Suita ruleaza cu `FLIPRADAR_TESTING=1` si cu un fisier SQLite unic per proces,
    deci izolarea exista deja; sub xdist lock-ul ar bloca procesele intre ele."""
    monkeypatch.setenv("FLIPRADAR_TESTING", "1")
    assert instance_lock.activ() is False


def test_activ_e_false_cand_variabila_il_opreste(monkeypatch):
    monkeypatch.delenv("FLIPRADAR_TESTING", raising=False)
    for valoare in ("0", "false", "FALSE", "no", "off", "Off"):
        monkeypatch.setenv("FLIPRADAR_INSTANCE_LOCK", valoare)
        assert instance_lock.activ() is False, valoare


def test_activ_e_true_implicit(monkeypatch):
    """Fara nicio variabila, lock-ul e PORNIT: protectia nu trebuie sa depinda de o
    setare pe care cineva trebuie sa-si aminteasca s-o puna."""
    monkeypatch.delenv("FLIPRADAR_TESTING", raising=False)
    monkeypatch.delenv("FLIPRADAR_INSTANCE_LOCK", raising=False)
    assert instance_lock.activ() is True

    monkeypatch.setenv("FLIPRADAR_INSTANCE_LOCK", "1")
    assert instance_lock.activ() is True


# ── T4: apelul de la import, sub pytest ──────────────────────────────────────

def test_asigura_instanta_unica_e_no_op_sub_pytest(tmp_path, monkeypatch):
    """Sub `FLIPRADAR_TESTING=1` nu ridica si nu atinge discul — altfel fiecare
    import de `app.main` din suita ar fi lasat in urma un fisier de lock."""
    monkeypatch.setenv("FLIPRADAR_TESTING", "1")
    monkeypatch.chdir(tmp_path)

    instance_lock.asigura_instanta_unica()

    assert list(tmp_path.iterdir()) == [], "niciun fisier creat"
