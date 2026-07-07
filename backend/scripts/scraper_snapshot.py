"""FlipRadar — snapshot / health-check pentru scraperele neautentificate.

Ruleaza AS-IS functiile publice de cautare (fara login) cu interogari fixe si
raporteaza cate rezultate intoarce fiecare platforma. Scop: verificare rapida
inainte de demo + referinta de comportament pentru refactorul de dupa licenta.

NU modifica scraperele. O eroare la o platforma (import sau runtime) este prinsa
si raportata ca FAIL — NU opreste restul snapshot-ului. Rezultatele complete se
salveaza ca JSON in scripts/snapshot_out/<yyyy-mm-dd>/<nume>.json.

EXCLUSE prin design:
  - Facebook (marketplace / auto / imobiliare): necesita sesiune autentificata.
  - Mobile.de: blocaj Imperva (nu trece cookieless din datacenter).

Rulare (din backend/):
    venv\\Scripts\\python.exe scripts\\scraper_snapshot.py
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# --- sys.path + .env: scriptul e in backend/scripts/, codul in backend/app/ ---
BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

# app.config cere SECRET_KEY + DATABASE_URL; le incarcam explicit din backend/.env
# ca scriptul sa mearga indiferent de directorul din care e rulat.
load_dotenv(BACKEND_DIR / ".env")

# Consola Windows: fortam UTF-8 ca diacriticele romanesti sa nu crape la print.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# --- Interogari fixe (health-check) ------------------------------------------
# Valorile marcate `# VERIFY` sunt alegeri proprii ale scriptului (praguri de
# pret / keyword auto), NU parametri citit din semnaturi. Se pot ajusta liber,
# nu ating scraperele. Cheile de filtru si pozitiile argumentelor sunt citite
# din codul scraperelor.
QUERY_ELECTRONICS = "iphone 13"     # marketplace + radar (electronice)
PRICE_MAX_ELECTRONICS = 10000       # RON  # VERIFY (limita generoasa, sa vina rezultate)
AUTO_MAKE = "bmw"                   # auto listings + radar autovit
AUTO_MODEL = "seria 3"             # auto listings
PRICE_MAX_AUTO = 100000             # RON  # VERIFY
RE_CITY = "Cluj-Napoca"            # imobiliare — cheia de filtru confirmata: filters["locatie"]


@dataclass
class Probe:
    grup: str
    platforma: str
    module_path: str
    func_name: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        base = f"{self.grup}_{self.platforma}".lower()
        return "".join(c if c.isalnum() else "_" for c in base).strip("_")


# Semnaturile reale (citite din cod), pe grupe:
#   marketplace (async): search_*(query, [category/category_id], filters={})
#   radar (sync):        search_*(keyword, max_price[, ...])
#   auto listings (async): make/model sau query, filters={}, page=1
#   real estate (async): filters={} cu cheia "locatie"
PROBES: list[Probe] = [
    # ---- Marketplace (async) — query fix "iphone 13" ----
    Probe("marketplace", "OLX", "app.scrapers.marketplace.olx_general", "search_olx_general", (QUERY_ELECTRONICS,)),
    Probe("marketplace", "Okazii", "app.scrapers.marketplace.okazii_scraper", "search_okazii", (QUERY_ELECTRONICS,)),
    Probe("marketplace", "LaJumate", "app.scrapers.marketplace.lajumate_scraper", "search_lajumate", (QUERY_ELECTRONICS,)),
    Probe("marketplace", "Publi24", "app.scrapers.marketplace.publi24_scraper", "search_publi24", (QUERY_ELECTRONICS,)),
    Probe("marketplace", "Vinted", "app.scrapers.marketplace.vinted_scraper", "search_vinted", (QUERY_ELECTRONICS,)),
    Probe("marketplace", "Kleinanzeigen", "app.scrapers.marketplace.kleinanzeigen_scraper", "search_kleinanzeigen", (QUERY_ELECTRONICS,)),

    # ---- Radar (sync) — keyword + max_price (arg 2, obligatoriu la olx/publi24/vinted/autovit) ----
    Probe("radar", "OLX", "app.services.radar.olx_scraper", "search_olx", (QUERY_ELECTRONICS,), {"max_price": PRICE_MAX_ELECTRONICS}),
    Probe("radar", "Okazii", "app.services.radar.okazii_scraper", "search_okazii", (QUERY_ELECTRONICS,), {"max_price": PRICE_MAX_ELECTRONICS}),
    Probe("radar", "LaJumate", "app.services.radar.lajumate_scraper", "search_lajumate", (QUERY_ELECTRONICS,), {"max_price": PRICE_MAX_ELECTRONICS}),
    Probe("radar", "Publi24", "app.services.radar.publi24_scraper", "search_publi24", (QUERY_ELECTRONICS,), {"max_price": PRICE_MAX_ELECTRONICS}),
    Probe("radar", "Vinted", "app.services.radar.vinted_scraper", "search_vinted", (QUERY_ELECTRONICS,), {"max_price": PRICE_MAX_ELECTRONICS}),
    Probe("radar", "Autovit", "app.services.radar.autovit_scraper", "search_autovit", (AUTO_MAKE,), {"max_price": PRICE_MAX_AUTO}),  # VERIFY keyword auto

    # ---- Auto listings (async) — make/model "bmw" / "seria 3" ----
    Probe("auto", "Autovit", "app.scrapers.auto.listings.autovit_scraper", "search_autovit", (), {"make": AUTO_MAKE, "model": AUTO_MODEL}),
    Probe("auto", "AutoScout24", "app.scrapers.auto.listings.autoscout24_scraper", "search_autoscout24", (), {"make": AUTO_MAKE, "model": AUTO_MODEL}),
    Probe("auto", "OLX Auto", "app.scrapers.auto.listings.olx_auto", "search_olx_auto", (), {"query": f"{AUTO_MAKE} {AUTO_MODEL}"}),  # olx_auto ia `query`, nu make/model
    Probe("auto", "Kleinanzeigen Auto", "app.scrapers.auto.listings.kleinanzeigen_auto", "search_kleinanzeigen_auto", (), {"make": AUTO_MAKE, "model": AUTO_MODEL}),

    # ---- Real estate (async) — oras "Cluj-Napoca" via filters["locatie"] ----
    Probe("imobiliare", "OLX", "app.scrapers.real_estate.olx_real_estate", "search_olx_real_estate", (), {"filters": {"locatie": RE_CITY}}),
    Probe("imobiliare", "Storia", "app.scrapers.real_estate.storia_scraper", "search_storia", (), {"filters": {"locatie": RE_CITY}}),
    Probe("imobiliare", "Imobiliare.ro", "app.scrapers.real_estate.imobiliare_ro_scraper", "search_imobiliare_ro", (), {"filters": {"locatie": RE_CITY}}),
]


@dataclass
class Result:
    probe: Probe
    count: int
    status: str          # "OK" | "GOL" | "FAIL"
    error: str = ""
    payload: Any = None


def _call_probe(probe: Probe) -> Result:
    """Importa si apeleaza o functie de cautare. Detecteaza automat sync vs async
    (inspect.iscoroutinefunction). Orice exceptie -> FAIL, fara sa opreasca restul."""
    try:
        module = importlib.import_module(probe.module_path)
        fn = getattr(module, probe.func_name)
        if inspect.iscoroutinefunction(fn):
            data = asyncio.run(fn(*probe.args, **probe.kwargs))
        else:
            data = fn(*probe.args, **probe.kwargs)
        items = list(data) if data is not None else []
        status = "OK" if items else "GOL"
        return Result(probe, len(items), status, payload=items)
    except Exception as exc:
        return Result(probe, 0, "FAIL", error=f"{type(exc).__name__}: {exc}")


def _save_json(out_dir: Path, res: Result) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{res.probe.slug}.json"
    if res.status == "FAIL":
        body: dict = {
            "status": "FAIL", "grup": res.probe.grup, "platforma": res.probe.platforma,
            "functie": res.probe.func_name, "error": res.error,
        }
    else:
        body = {
            "status": res.status, "grup": res.probe.grup, "platforma": res.probe.platforma,
            "functie": res.probe.func_name, "count": res.count, "results": res.payload,
        }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _print_table(results: list[Result]) -> None:
    plat_vals = [f"{r.probe.grup}/{r.probe.platforma}" for r in results]
    plat_w = max(len("Platformă"), *(len(v) for v in plat_vals))
    func_w = max(len("Funcție"), *(len(r.probe.func_name) for r in results))
    print(f"| {'Platformă':<{plat_w}} | {'Funcție':<{func_w}} | {'Nr. rezultate':>13} | {'Status':<6} |")
    print(f"|{'-' * (plat_w + 2)}|{'-' * (func_w + 2)}|{'-' * 15}|{'-' * 8}|")
    for r, plat in zip(results, plat_vals):
        cnt = "-" if r.status == "FAIL" else str(r.count)
        print(f"| {plat:<{plat_w}} | {r.probe.func_name:<{func_w}} | {cnt:>13} | {r.status:<6} |")


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "snapshot_out" / date.today().isoformat()
    print(f"FlipRadar scraper snapshot — {date.today().isoformat()}")
    print(f"Output JSON: {out_dir}\n")

    results: list[Result] = []
    for probe in PROBES:
        print(f"  … {probe.grup}/{probe.platforma} ({probe.func_name})", flush=True)
        res = _call_probe(probe)
        _save_json(out_dir, res)
        results.append(res)

    print()
    _print_table(results)

    fails = [r for r in results if r.status == "FAIL"]
    if fails:
        print("\nErori (FAIL) — scraperele NU se repara aici, doar se raporteaza:")
        for r in fails:
            print(f"  - {r.probe.grup}/{r.probe.platforma}: {r.error}")

    ok = sum(1 for r in results if r.status == "OK")
    gol = sum(1 for r in results if r.status == "GOL")
    print(f"\nTotal: {len(results)} platforme — {ok} OK, {gol} GOL (0 rezultate), {len(fails)} FAIL.")
    print(f"JSON complet salvat in: {out_dir}")


if __name__ == "__main__":
    main()
