import os
from dotenv import load_dotenv

load_dotenv()

# PKG-DATA — directorul de date scriibil al instantei (dev = cwd; sub
# PyInstaller = LOCALAPPDATA/XDG). Rezolvat dupa load_dotenv ca FLIPRADAR_DATA_DIR
# din .env sa fie vizibil.
from app.paths import get_data_dir, get_or_create_secret_key
DATA_DIR = get_data_dir()

# DATABASE_URL: env-ul are prioritate; altfel default SQLite in directorul de date.
DATABASE_URL = (os.getenv("DATABASE_URL")
                or f"sqlite:///{(DATA_DIR / 'flipradar.db').as_posix()}")

# SECRET_KEY: env-ul are prioritate; altfel o cheie autogenerata si persistata in
# data dir. Validarea de lungime se aplica ambelor surse.
SECRET_KEY = os.getenv("SECRET_KEY") or get_or_create_secret_key(DATA_DIR)
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY trebuie sa aiba minim 32 de caractere pentru a fi sigur."
    )

ALGORITHM = os.getenv("ALGORITHM", "HS256")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# SMTP (optional) - lasati gol pentru a dezactiva trimiterea de emailuri
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@flipradar.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

# Proxy (opțional) — citit în base_scraper.get_proxy_config()
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "false").lower() in ("1", "true", "yes")
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

# Web Push (VAPID)
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "flipradar@exemplu.ro")
