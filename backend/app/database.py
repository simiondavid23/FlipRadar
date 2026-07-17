from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# Create database engine
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # FastAPI + APScheduler folosesc thread-uri diferite pe aceeasi conexiune pool-uita.
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args
)

if engine.dialect.name == "sqlite":
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        # WAL: cititori si un scriitor concurent fara blocaj reciproc;
        # busy_timeout: scriitorii concurenti (scanuri paralele + HTTP)
        # asteapta lock-ul in loc sa esueze; foreign_keys: paritate cu
        # enforcement-ul FK din PostgreSQL (inclusiv ON DELETE declarat).
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db():
    """
    Dependency that provides a database session.
    Automatically closes the session when done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
