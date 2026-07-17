"""Fundatia de teste FlipRadar — pytest pe fisier SQLite temporar, IZOLAT per rulare.

Reguli dure (nu ocoli):
- Testele ruleaza pe un fisier SQLite temporar unic per proces (nume cu uuid),
  niciodata pe baza reala (DATABASE_URL din .env).
- Env-ul se pregateste ÎNAINTE de orice import din `app` (app/config.py valideaza
  DATABASE_URL + SECRET_KEY chiar la import; startup_checks cere si GROQ_API_KEY).
- Izolarea intre suite concurente e structurala: fiecare proces are propriul fisier,
  deci nu se mai pot distruge reciproc prin clean_db (motivul vechiului lock, TI-1b).
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

# ── 1. Bootstrap env, ÎNAINTE de orice import din `app` ──────────────────────────
# backend/ pe sys.path ca `import app...` sa mearga indiferent de CWD / import-mode.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Nu suprascrie variabilele deja din mediu (override=False, default), ca SECRET_KEY
# / GROQ_API_KEY din .env sa fie disponibile fara sa strice env-ul deja setat.
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

# SQLITE-1: fiecare rulare pytest primeste propriul fisier SQLite temporar (nume
# unic prin uuid), creat la prima conectare — izolare totala fara baza dedicata.
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"flipradar_test_{uuid.uuid4().hex}.db"
TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

# SECRET_KEY dummy stabil (>=32 caractere) daca nu e deja in mediu.
os.environ.setdefault("SECRET_KEY", "test-secret-key-pentru-pytest-0123456789abcdef")
# validate_env() (startup_checks.py) cere si GROQ_API_KEY; testele NU ating Groq.
os.environ.setdefault("GROQ_API_KEY", "test-dummy-groq-key")
# De acum, tot `app.*` vede DOAR baza de test.
os.environ["DATABASE_URL"] = TEST_DB_URL
# Semnal ca rulam sub pytest: discord_service NU porneste worker-ul de fundal
# (ar accesa baza de test concurent cu suita). In productie variabila nu exista.
os.environ["FLIPRADAR_TESTING"] = "1"


# SQLITE-1: izolarea vine acum din fisierul SQLite unic per proces (uuid in
# _TEST_DB_PATH) — doua suite simultane ruleaza pe baze diferite, deci concurenta
# pe aceeasi baza (care se distrugea reciproc prin golirea din clean_db, vezi TI-1b) e imposibila structural.


# ── 3. Schema pe baza de test (session, autouse) ─────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Importa app.main -> declanseaza Base.metadata.create_all + run_migrations()
    pe baza de test (exact fluxul de productie) si dezactiveaza rate limiter-ul."""
    import app.main as main

    # slowapi: atributul `enabled` (verificat in slowapi/extension.py, default True);
    # False dezactiveaza complet rate limiting-ul, altfel register/login pica pe 429.
    main.app.state.limiter.enabled = False
    yield

    from app.database import engine
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(str(_TEST_DB_PATH) + suffix).unlink(missing_ok=True)


# ── 4. DB curat inainte de fiecare test (autouse) ────────────────────────────────
@pytest.fixture(autouse=True)
def clean_db(_schema):
    """Goleste toate tabelele inainte de fiecare test, in ordine inversa FK (ca sa
    nu incalce constrangerile). Fara AUTOINCREMENT explicit, rowid-ul reporneste de
    la 1 pe tabela goala — echivalentul RESTART IDENTITY din PostgreSQL."""
    from app.database import Base, engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


# ── 5. TestClient FARA context manager (lifespan off) ────────────────────────────
@pytest.fixture
def client():
    """TestClient fara `with` -> lifespan NU ruleaza (fara scheduler, fara playwright)."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ── 6. Client autentificat (register + login, email unic per test) ───────────────
@pytest.fixture
def auth_client(client):
    """Inregistreaza un user nou (email/username unic) + login; intoarce clientul
    cu cookie-urile httpOnly de sesiune setate in jar."""
    uniq = uuid.uuid4().hex[:12]
    payload = {
        "email": f"test_{uniq}@example.com",
        "username": f"user_{uniq}",
        "password": "testpass123",
        "full_name": "Test User",
        "security_question": "Care e culoarea preferata?",
        "security_answer": "albastru",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200, f"register a esuat: {r.status_code} {r.text}"
    r = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert r.status_code == 200, f"login a esuat: {r.status_code} {r.text}"
    return client
