import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:***REMOVED***@localhost:5432/flipradar")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY nu este setat. Defineste-l in fisierul .env inainte sa pornesti serverul."
    )
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY trebuie sa aiba minim 32 de caractere pentru a fi sigur."
    )

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# SMTP (optional) - lasati gol pentru a dezactiva trimiterea de emailuri
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@flipradar.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
