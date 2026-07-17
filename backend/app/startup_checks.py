import os
import sys

# Pe Windows consola foloseste implicit cp1252 si nu poate codifica diacriticele
# romanesti (ă/ț/ș) sau em-dash-ul (—). Cum startup_checks ruleaza primul, aici
# reconfiguram stdout/stderr la UTF-8 ca mesajele de mai jos — si restul printurilor
# cu diacritice din aplicatie — sa nu arunce UnicodeEncodeError la pornire.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Incarcam .env aici pentru ca validate_env() ruleaza ca prima linie din main.py,
# inainte de orice import din app (deci inainte ca app.config sa apeleze load_dotenv).
# Fara asta variabilele din .env nu ar fi inca vizibile si validarea ar esua fals.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv ar trebui sa existe; daca lipseste, ne bazam pe variabilele
    # deja prezente in mediu (ex. setate de Docker / systemd).
    pass

# PKG-DATA — DATABASE_URL si SECRET_KEY au acum default-uri (data dir /
# autogenerare), GROQ_API_KEY e optional; lista ramane pentru variabile viitoare
# cu adevarat obligatorii.
REQUIRED_VARS = []
OPTIONAL_VARS = ["GROQ_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                 "DISCORD_WEBHOOK_URL", "FACEBOOK_EMAIL", "FACEBOOK_PASSWORD",
                 "LOG_DB_PERSISTENCE"]


def validate_env() -> None:
    """Verifică variabilele de mediu obligatorii la pornirea aplicației.
    Oprește procesul cu exit code 1 dacă lipsește oricare dintre cele obligatorii.
    """
    missing = [k for k in REQUIRED_VARS if not os.getenv(k)]
    if missing:
        print(f"\n[FATAL] FlipRadar nu poate porni — variabile de mediu lipsă:")
        for k in missing:
            print(f"  • {k}")
        print("\nAsigură-te că fișierul .env este configurat corect și reîncearcă.\n")
        sys.exit(1)

    for k in OPTIONAL_VARS:
        if not os.getenv(k):
            print(f"[WARN] Variabila opțională {k} nu este setată — funcționalitate asociată dezactivată.")
