"""Fundatia de teste FlipRadar — pytest + PostgreSQL de test IZOLATA.

Reguli dure (nu ocoli):
- Testele ruleaza DOAR pe TEST_DATABASE_URL, niciodata pe baza reala (DATABASE_URL).
- Env-ul se pregateste ÎNAINTE de orice import din `app` (app/config.py valideaza
  DATABASE_URL + SECRET_KEY chiar la import; startup_checks cere si GROQ_API_KEY).
- O SINGURA suita pytest ruleaza pe baza de test la un moment dat (advisory lock,
  vezi guard-ul de mai jos). Motiv (H3, TI-1b): doua procese simultane pe aceeasi
  baza se distrug reciproc prin TRUNCATE-ul din clean_db — rândurile unuia dispar
  din testul celuilalt ("Could not refresh instance User" / 401 "Token invalid").
"""
import os
import sys
import uuid

import pytest
from dotenv import load_dotenv

# ── 1. Bootstrap env, ÎNAINTE de orice import din `app` ──────────────────────────
# backend/ pe sys.path ca `import app...` sa mearga indiferent de CWD / import-mode.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Nu suprascrie variabilele deja din mediu (override=False, default) — asa
# demonstratia guard-ului `TEST_DATABASE_URL= pytest` chiar goleste valoarea.
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
_REAL_DATABASE_URL = os.getenv("DATABASE_URL")

# Guard 1 — fara baza de test dedicata, refuzam sa rulam.
if not TEST_DATABASE_URL or not TEST_DATABASE_URL.strip():
    pytest.exit(
        "Seteaza TEST_DATABASE_URL in backend/.env — testele refuza sa ruleze fara "
        "baza dedicata (ex: postgresql://postgres:parola@localhost:5432/flipradar_test).",
        returncode=1,
    )

# Guard 2 — baza de test NU poate fi baza reala.
if _REAL_DATABASE_URL and TEST_DATABASE_URL.strip() == _REAL_DATABASE_URL.strip():
    pytest.exit(
        "Baza de test NU poate fi baza reala (TEST_DATABASE_URL == DATABASE_URL). "
        "Foloseste o baza separata, ex. flipradar_test.",
        returncode=1,
    )

# SECRET_KEY dummy stabil (>=32 caractere) daca nu e deja in mediu.
os.environ.setdefault("SECRET_KEY", "test-secret-key-pentru-pytest-0123456789abcdef")
# validate_env() (startup_checks.py) cere si GROQ_API_KEY; testele NU ating Groq.
os.environ.setdefault("GROQ_API_KEY", "test-dummy-groq-key")
# De acum, tot `app.*` vede DOAR baza de test.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Semnal ca rulam sub pytest: discord_service NU porneste worker-ul de fundal
# (ar accesa baza de test concurent cu suita). In productie variabila nu exista.
os.environ["FLIPRADAR_TESTING"] = "1"


# ── 2. Auto-creare baza de test daca lipseste ────────────────────────────────────
def _ensure_test_database() -> None:
    """Conectare la baza de mentenanta `postgres` cu credentialele din
    TEST_DATABASE_URL; daca baza de test nu exista -> CREATE DATABASE."""
    from urllib.parse import urlparse

    import psycopg2
    from psycopg2 import sql

    parsed = urlparse(TEST_DATABASE_URL)
    db_name = (parsed.path or "/").lstrip("/")
    if not db_name:
        pytest.exit("TEST_DATABASE_URL nu contine un nume de baza de date.", returncode=1)

    # Reconstruim DSN-ul catre baza de mentenanta `postgres` (fara a atinge parola).
    admin_dsn = f"{parsed.scheme}://{parsed.netloc}/postgres"
    try:
        conn = psycopg2.connect(admin_dsn)
    except Exception as exc:
        pytest.exit(
            f"[tests] Nu ma pot conecta la PostgreSQL ({parsed.hostname}:{parsed.port}): {exc}",
            returncode=1,
        )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
                print(f"\n[tests] Am creat baza {db_name}")
    finally:
        conn.close()


_ensure_test_database()


# ── 2b. Guard anti-concurenta: o SINGURA suita pytest pe baza de test ─────────────
# H3 (TI-1b, confirmat): doua procese pytest simultane pe aceeasi baza se distrug
# reciproc prin TRUNCATE-ul din clean_db. Nu suportam concurenta — o facem imposibila
# TACIT cu un advisory lock cluster-wide, tinut cat traieste procesul. E session-scoped
# in Postgres → se elibereaza automat inclusiv la crash/kill al procesului pytest.
# Cheia include numele bazei (hashtext(current_database())) fiindca advisory lock-urile
# NU sunt per-database, ci per-cluster.
def _acquire_session_guard():
    import psycopg2
    from urllib.parse import urlparse

    conn = psycopg2.connect(TEST_DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(current_database()), 424242)")
        got = cur.fetchone()[0]
    if not got:
        db_name = (urlparse(TEST_DATABASE_URL).path or "/").lstrip("/")
        conn.close()
        pytest.exit(
            f"O alta suita pytest ruleaza deja pe {db_name}. Suitele se ruleaza DOAR "
            f"secvential - asteapta sa se termine cealalta.",
            returncode=1,
        )
    return conn


# Pastrat la nivel de modul → conexiunea (si lock-ul) traiesc cat procesul pytest.
_SESSION_GUARD_CONN = _acquire_session_guard()


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


# ── 4. DB curat inainte de fiecare test (autouse) ────────────────────────────────
@pytest.fixture(autouse=True)
def clean_db(_schema):
    """TRUNCATE ... RESTART IDENTITY CASCADE pe toate tabelele din Base.metadata,
    ca fiecare test sa porneasca de la zero."""
    from sqlalchemy import text

    from app.database import Base, engine

    tables = [t.name for t in Base.metadata.sorted_tables]
    if tables:
        joined = ", ".join(f'"{name}"' for name in tables)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))
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
