# -*- coding: utf-8 -*-
"""RP-2 FAZA 8 — verificare (necomis). <=2 requesturi (1 refresh live).

Vinted e blocat DataDome pe IP-ul de datacenter azi -> refresh_catalog_tree întoarce
403 (gestionat: NU șterge datele vechi). Demonstrez atunci pipeline-ul parserului pe
fixture (0 requesturi) + engine-ul de excluderi + resolverul.
"""
import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BACKEND = r"C:\licenta\flipRadar\backend"
FIX = os.path.join(BACKEND, "tests", "fixtures", "vinted_catalog_rsc.txt")
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("GROQ_API_KEY", "x")


def hdr(t):
    print("\n" + "=" * 90)
    print(t)
    print("=" * 90)


# ── 1) refresh_catalog_tree LIVE (1 request) ────────────────────────────────
hdr("1) refresh_catalog_tree LIVE (1 request prin limiterul vinted_html)")
try:
    from app.database import SessionLocal
    from app.services.radar.vinted_catalog_service import refresh_catalog_tree
    db = SessionLocal()
    try:
        res = refresh_catalog_tree(db)
    finally:
        db.close()
    print("rezultat:", res)
    if not res.get("ok"):
        print("-> Vinted blocat/indisponibil acum (asteptat). Datele vechi NU au fost sterse.")
except Exception as e:
    import traceback
    print("refresh EXCEPTIE:", "".join(traceback.format_exc())[:800])

# ── 2) pipeline parser pe fixture (0 requesturi) ────────────────────────────
hdr("2) Parser arbore pe fixture (dovada pipeline: extract -> build -> noduri)")
try:
    from app.services.radar.vinted_catalog_service import _extract_catalog_roots, build_catalog_nodes
    txt = open(FIX, encoding="utf-8").read()
    roots, cf = _extract_catalog_roots(txt)
    nodes = build_catalog_nodes(roots, cf)
    print(f"camp copii: {cf} | radacini: {len(roots)} | total noduri: {len(nodes)}")
    print("titluri radacina:", [r["title"] for r in roots])
    print("3 cai de adancime max (sample):")
    for n in [x for x in nodes if x["depth"] == 2][:3]:
        print(f"   [{n['id']}] {n['path']}  (parent={n['parent_id']}, depth={n['depth']})")
except Exception as e:
    print("parser EXCEPTIE:", str(e)[:300])

# ── 3) engine de excluderi pe 6 cazuri ──────────────────────────────────────
hdr("3) Engine de excluderi v2 — 6 cazuri")
try:
    from app.services.radar.exclusion_engine import check_exclusion
    CASES = [
        ("Husă iPhone 12", None, ["husa"], None, None),                       # diacritice -> exclus
        ("iPhone 12 Deblocat", None, ["blocat"], None, None),                 # boundary -> trece
        ("Ofer la schimb", None, ["schimb"], None, None),                     # cuvant intreg -> exclus
        ("Schimbător viteze", None, ["schimb"], None, None),                  # boundary -> trece
        ("telefon fara defecte", None, ["defect"], None, None),               # exceptie -> trece
        ("iPhone 12", "vand pentru piese", [], ["pentru piese"], None),       # fraza pe descriere -> exclus
    ]
    for title, desc, ew, edw, exc in CASES:
        excluded, rule = check_exclusion(title, desc, ew, edw, exc)
        tag = "EXCLUS " if excluded else "trece  "
        print(f"  [{tag}] title={title!r:38} desc={str(desc)!r:20} -> {rule or 'OK'}")
except Exception as e:
    print("engine EXCEPTIE:", str(e)[:300])

# ── 4) resolver precedenta ──────────────────────────────────────────────────
hdr("4) Resolver Vinted — precedenta config > db > map")
try:
    from app.services.radar.vinted_scraper import _resolve_vinted_catalog_id
    print("  config:", _resolve_vinted_catalog_id("Femei > Haine", "Rochii", db=None, marketplace_config={"vinted_catalog_id": 999}))
    print("  map   :", _resolve_vinted_catalog_id("Femei > Haine", "Rochii", db=None, marketplace_config=None))
except Exception as e:
    print("resolver EXCEPTIE:", str(e)[:300])

print("\n[RP-2 verify terminat]")
