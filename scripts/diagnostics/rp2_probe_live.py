# -*- coding: utf-8 -*-
"""RP-2-probe — validare LIVE a arborelui de categorii Vinted. UN SINGUR request.

Buget strict: 1 request HTTP total (vinted_html.get_html pe /catalog). Daca 403/blocat:
STOP + raport, NICIO reincercare. Toti pasii de dupa fetch lucreaza pe fisierul salvat.
Foloseste functiile REALE din vinted_catalog_service (nu reimplementa). Scrie in DB-ul
REAL doar daca gate-ul de plauzibilitate trece. Precondinte: backend local OPRIT.
"""
import sys
import os
import json
import copy
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
FIXTURES = os.path.join(BACKEND, "tests", "fixtures")
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("GROQ_API_KEY", "x")

HTML_PATH = os.path.join(HERE, "_vinted_catalog_live.html")
EVID_PATH = os.path.join(HERE, "rp2_probe_evidence.txt")
REPORT_PATH = os.path.join(HERE, "rp2_probe_raport.txt")
FIX_PATH = os.path.join(FIXTURES, "vinted_catalog_roots_real.json")

_RF = open(REPORT_PATH, "w", encoding="utf-8")


def out(*parts):
    text = " ".join(str(p) for p in parts)
    _RF.write(text + "\n")
    _RF.flush()
    try:
        print(text, flush=True)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def stop(reason):
    out("")
    out(f"STOP: {reason}")
    out("DB NEATINS.")
    out("[RP-2-probe terminat]")
    _RF.close()
    sys.exit(0)


from app.services.radar import vinted_html  # noqa: E402
from app.services.radar.vinted_catalog_service import (  # noqa: E402
    _extract_catalog_roots, build_catalog_nodes, get_children, search_catalogs,
)
from app.services.radar.exclusion_engine import normalize  # noqa: E402

out("RP-2-probe — validare LIVE arbore Vinted")
out(f"timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ── 1a) fetch O SINGURA DATA + salvare HTML ─────────────────────────────────
try:
    resp = vinted_html.get_html("https://www.vinted.ro/catalog", referer="https://www.vinted.ro/")
except Exception as e:
    out("Fetch EXCEPTIE:", str(e)[:200])
    stop("eroare la fetch /catalog")

status = resp.status_code
body = resp.text or ""
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(body)

# de aici, lucram pe fisierul salvat
body = open(HTML_PATH, encoding="utf-8").read()

# ── 1b) verdicte ────────────────────────────────────────────────────────────
out("")
out("=== 1b) fetch ===")
blocked = vinted_html._looks_blocked(status, body)
decoded = vinted_html.decode_next_f(body)
has_ct = '"catalogTree":[' in decoded
out("status HTTP:", status)
out("len(body):", len(body))
out("_looks_blocked:", blocked)
out("decoded len:", len(decoded))
out("'\"catalogTree\":[' in decodat:", has_ct)

if blocked or status != 200:
    stop(f"pagina blocata/nereusita (HTTP {status}, blocked={blocked}) — nicio reincercare")

# ── 1c) parse cu functiile REALE ────────────────────────────────────────────
out("")
out("=== 1c) parse arbore (functii reale vinted_catalog_service) ===")
roots, child_field = _extract_catalog_roots(decoded)


def write_evidence(reason):
    lines = [f"MOTIV: {reason}", ""]
    anchors = ['"catalogTree":[', '"catalogs":[{"id"', '"children":[{"id"', '"catalogs":[', '"children":[']
    lines.append("ANCORE-CANDIDAT:")
    for a in anchors:
        idx = decoded.find(a)
        if idx >= 0:
            lines.append(f"  {a!r} @ {idx}: {decoded[idx:idx+120]!r}")
        else:
            lines.append(f"  {a!r}: absent")
    pick = decoded.find('"catalogTree":[')
    if pick < 0 and child_field:
        pick = decoded.find(f'"{child_field}":[')
    lines.append("")
    lines.append(f"±2000 in jurul array-ului ales (@ {pick}):")
    lines.append(decoded[max(0, pick - 2000): pick + 2000] if pick >= 0 else "<niciun array gasit>")
    with open(EVID_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    out("evidenta salvata:", EVID_PATH)


if not roots:
    write_evidence("_extract_catalog_roots a intors None (arbore neparsabil)")
    stop("arbore neparsabil in RSC")

nodes = build_catalog_nodes(roots, child_field)
root_titles = [r.get("title") for r in roots]
out("child_field:", child_field)
out("total noduri:", len(nodes))
out("nr radacini:", len(roots))
out("TITLURI RADACINA (toate):", root_titles)

depth_dist = {}
for n in nodes:
    depth_dist[n["depth"]] = depth_dist.get(n["depth"], 0) + 1
out("distributie pe depth (0-3):", {d: depth_dist.get(d, 0) for d in range(4)},
    "| >3:", sum(v for d, v in depth_dist.items() if d > 3))

deep = [n for n in nodes if n["depth"] >= 2]
phone = [n for n in deep if "telefoane" in normalize(n["path"]) or "iphone" in normalize(n["path"])]
sample = (phone[:1] + [n for n in deep if n not in phone])[:5]
out("5 cai depth>=2 (macar una Telefoane/iPhone daca exista):")
for n in sample:
    out(f"   [{n['id']}] d{n['depth']} {n['path']}")

# ── 1d) plauzibilitate ──────────────────────────────────────────────────────
out("")
out("=== 1d) plauzibilitate ===")
TARGETS = {"femei", "barbati", "copii", "casa", "electronice"}
root_norm = [normalize(t) for t in root_titles]
hits = sorted({t for t in TARGETS if any(t in rn for rn in root_norm)})
count_ok = len(nodes) >= 1000
out("noduri >= 1000:", count_ok, f"({len(nodes)})")
out("radacini-tinta gasite:", hits, f"(>=2 necesar: {len(hits) >= 2})")
plausible = count_ok and len(hits) >= 2
out("PLAUZIBIL:", plausible)

if not plausible:
    write_evidence(f"plauzibilitate esuata (noduri={len(nodes)}, tinte={hits})")
    stop("gate de plauzibilitate esuat — DB neatins")

# ── 1e) scriere in DB REAL (pattern refresh_catalog_tree) + verificare ──────
out("")
out("=== 1e) scriere in DB real + verificare ===")
from app.database import SessionLocal, engine  # noqa: E402
from app.models.vinted_catalog import VintedCatalog  # noqa: E402

# asigura tabelul (idempotent) — backend-ul poate sa nu fi rulat migratia pe DB real
try:
    VintedCatalog.__table__.create(bind=engine, checkfirst=True)
except Exception as e:
    out("create table (checkfirst) nota:", str(e)[:120])

db = SessionLocal()
now = datetime.now(timezone.utc)
written = 0
try:
    db.query(VintedCatalog).delete()
    db.bulk_insert_mappings(VintedCatalog, [{**n, "updated_at": now} for n in nodes])
    db.commit()
    written = len(nodes)
    out("scris in DB:", written, "noduri (delete + bulk_insert + commit)")
except Exception as e:
    db.rollback()
    out("scriere DB EXCEPTIE (rollback):", str(e)[:200])
    db.close()
    stop("eroare la scrierea in DB — rollback, datele vechi pastrate")

# verificare din DB
db_children = get_children(db, None)
db_titles = [c["title"] for c in db_children]
out("get_children(None) titluri:", db_titles)
out("coincid cu radacinile printate:", set(db_titles) == set(root_titles))
sr = search_catalogs(db, "iphone")
out(f"search_catalogs('iphone'): {len(sr)} rezultate")
for r in sr[:10]:
    out(f"   [{r['id']}] {r['path']}")
db.close()

# ── 2) fixture REAL ─────────────────────────────────────────────────────────
out("")
out("=== 2) fixture real ===")


def empty_beyond(node, cf, max_depth, cur=0):
    if cur >= max_depth:
        node[cf] = []
    else:
        for ch in node.get(cf, []) or []:
            empty_beyond(ch, cf, max_depth, cur + 1)


def build_fixture(max_depth=None):
    trunc = []
    for i, r in enumerate(roots):
        rc = copy.deepcopy(r)
        if i >= 2:
            rc[child_field] = []
        elif max_depth is not None:
            empty_beyond(rc, child_field, max_depth)
        trunc.append(rc)
    return json.dumps({"child_field": child_field, "roots": trunc}, ensure_ascii=False)


payload = build_fixture()
# tinta <=300KB: daca primele 2 radacini complete depasesc, limitam adancimea
for md in (None, 5, 4, 3):
    payload = build_fixture(md)
    if len(payload.encode("utf-8")) <= 300_000:
        break
with open(FIX_PATH, "w", encoding="utf-8") as f:
    f.write(payload)
out("fixture salvat:", FIX_PATH, "->", os.path.getsize(FIX_PATH), "bytes")
# sanity: cate noduri produce fixture-ul
_fx = json.loads(payload)
_fx_nodes = build_catalog_nodes(_fx["roots"], _fx["child_field"])
out("noduri in fixture:", len(_fx_nodes), "| radacini:", len(_fx["roots"]))

out("")
out("[RP-2-probe: 1a-2 OK — DB REAL populat]")
_RF.close()
