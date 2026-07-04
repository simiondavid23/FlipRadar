"""DEBUG TEMP — diagnosticare refresh_price_from_source pentru emag.ro & pcgarage.ro.

Fisier TEMPORAR de diagnosticare. NU scrie nimic in DB (doar citeste + apeleaza
functia, fara commit). De sters cand diagnosticarea e gata (grep "DEBUG TEMP").

Rulare (din folderul backend/, cu venv-ul proiectului):
    venv\\Scripts\\python.exe -m scripts.debug_price_refresh
sau echivalent:
    venv\\Scripts\\python.exe scripts\\debug_price_refresh.py

Interogheaza toate ProductSource cu source in ("emag.ro", "pcgarage.ro"),
apeleaza refresh_price_from_source(...) cu valorile reale din DB (source,
source_url, product_name, sku) si printeaza pretul nou returnat (sau None).
"""
import sys
from pathlib import Path

# Consola Windows: fortam UTF-8 ca sa nu pice pe diacritice romanesti.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# `import app...` sa mearga indiferent de cwd: adaugam backend/ pe sys.path...
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ...si incarcam .env-ul din backend/ inainte de app.config (are nevoie de SECRET_KEY).
from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND_DIR / ".env")

import importlib  # noqa: E402
import pkgutil  # noqa: E402
import app.models  # noqa: E402

# Inregistram TOATE modelele inainte de prima interogare: ProductSource.product ->
# Product, iar Product are relationship-uri catre User/Alert/PriceHistory/etc. SQLAlchemy
# configureaza toate mapper-ele odata, deci fiecare clasa trebuie sa fie importata intai.
for _mod in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_mod.name}")

from app.database import SessionLocal  # noqa: E402
from app.models.product_source import ProductSource  # noqa: E402
from app.services.scraper_service import refresh_price_from_source  # noqa: E402

_TARGET_SOURCES = ("emag.ro", "pcgarage.ro")


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(ProductSource)
            .filter(ProductSource.source.in_(_TARGET_SOURCES))
            .all()
        )
        print(f"[DEBUG TEMP] {len(rows)} surse gasite pentru {_TARGET_SOURCES}")
        for i, ps in enumerate(rows, 1):
            product = ps.product  # relationship -> Product (name, sku); doar SELECT
            product_name = getattr(product, "name", None)
            sku = getattr(product, "sku", None)
            print("=" * 72)
            print(f"[DEBUG TEMP] ({i}/{len(rows)}) sursa={ps.source!r}")
            print(f"[DEBUG TEMP]   produs  = {product_name!r}")
            print(f"[DEBUG TEMP]   sku     = {sku!r}")
            print(f"[DEBUG TEMP]   url     = {ps.source_url!r}")
            print(f"[DEBUG TEMP]   pret_db = {ps.current_price!r} {ps.currency}")
            new_price = refresh_price_from_source(
                source=ps.source,
                source_url=ps.source_url,
                product_name=product_name,
                sku=sku,
            )
            print(f"[DEBUG TEMP]   -> pret NOU returnat = {new_price!r}")

            # TEST-2: al doilea apel, IDENTIC dar cu sku=None explicit, doar pentru
            # randurile cu sku real pe Product (iPhone/mouse pe emag, iPhone pe pcgarage).
            # sku=None forteaza query = product_name in refresh_price_from_source.
            # Primul apel de mai sus ramane neschimbat — vrem ambele rezultate alaturi.
            if sku:
                print(f"[DEBUG TEMP] TEST-2 (fara sku, query=nume) pentru '{product.name[:50]}' ({ps.source})")
                rezultat_test2 = refresh_price_from_source(
                    source=ps.source,
                    source_url=ps.source_url,
                    product_name=product_name,
                    sku=None,
                )
                print(f"[DEBUG TEMP] TEST-2 -> pret NOU returnat = {rezultat_test2}")
        print("=" * 72)
        print("[DEBUG TEMP] Gata. (Niciun commit — DB neatinsa.)")
    finally:
        db.close()  # sesiune doar-citire; niciun commit nicaieri


if __name__ == "__main__":
    main()
