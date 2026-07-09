"""RP-2 — serviciul de arbore de categorii Vinted.

Sursa unica: pagina https://www.vinted.ro/catalog (200, Next.js App Router), unde
intregul arbore e embedded in chunk-urile RSC `__next_f` (dovedit RP-DIAG-2:
campul de copii `catalogs` domina — 29018 vs 536 `children`; ~11.581 noduri id+title;
camp `code` frecvent). Endpointurile `/api/v2/catalogs` + `/catalog/initializers` dau 404.

Refoloseste `vinted_html` (sesiune chrome131 singleton + limiter + decode_next_f) — NU
cream alt client/decodor. Parserul e defensiv (Flight poate presara refs `$..`): sarim
orice intrare care nu e dict-nod valid.
"""
import json
from datetime import datetime, timezone

from app.services.radar import vinted_html
from app.services.radar.exclusion_engine import normalize
from app.services.log_manager import log_manager
from app.models.vinted_catalog import VintedCatalog


_CATALOG_URL = "https://www.vinted.ro/catalog"
_MIN_NODES = 1000  # sanity: sub atat -> consideram refresh esuat, NU stergem datele vechi


def _balanced_array(s: str, start: int) -> str | None:
    """Sub-string-ul `[...]` echilibrat care incepe la `start` (s[start]='['),
    respectand string-urile/escape-urile. None daca nu se inchide."""
    if start < 0 or start >= len(s) or s[start] != "[":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None


def _looks_like_catalog_list(data, child_field: str) -> bool:
    if not isinstance(data, list):
        return False
    good = [x for x in data if isinstance(x, dict) and "id" in x and "title" in x]
    return len(good) >= 2


def _extract_catalog_roots(decoded: str):
    """(roots_list, child_field). Localizeaza array-ul de radacini in RSC-ul decodat.
    Intai proprietatea `catalogTree`, apoi cea mai mare array `<child_field>:[...]`."""
    child_field = "catalogs" if '"catalogs":[' in decoded else (
        "children" if '"children":[' in decoded else "catalogs")

    # 1) proprietatea catalogTree (array direct de radacini)
    i = decoded.find('"catalogTree":[')
    while i >= 0:
        raw = _balanced_array(decoded, decoded.find("[", i))
        if raw:
            try:
                data = json.loads(raw)
                if _looks_like_catalog_list(data, child_field):
                    return data, child_field
            except Exception:
                pass
        i = decoded.find('"catalogTree":[', i + 1)

    # 2) fallback: cea mai mare array "<child_field>":[{"id"...}] parsabila
    best = None
    anchor = f'"{child_field}":[{{"id"'
    i = decoded.find(anchor)
    scanned = 0
    while i >= 0 and scanned < 60:
        scanned += 1
        raw = _balanced_array(decoded, decoded.find("[", i))
        if raw and (best is None or len(raw) > len(best[0])):
            try:
                data = json.loads(raw)
                if _looks_like_catalog_list(data, child_field):
                    best = (raw, data)
            except Exception:
                pass
        i = decoded.find(anchor, i + len(raw or anchor))
    return (best[1] if best else None), child_field


def build_catalog_nodes(roots, child_field: str = "catalogs") -> list[dict]:
    """Arbore -> lista plata de noduri {id, parent_id, title, code, path, depth}.
    Functie PURA (testabila pe fixture). Sare nodurile fara id/title. Dedup pe id."""
    nodes: list[dict] = []
    seen: set = set()

    def walk(node, parent_id, parent_path, depth):
        if not isinstance(node, dict):
            return
        cid = node.get("id")
        title = node.get("title")
        if cid is None or not title:
            return
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            return
        if cid in seen:
            return
        seen.add(cid)
        path = f"{parent_path} > {title}" if parent_path else str(title)
        nodes.append({
            "id": cid,
            "parent_id": parent_id,
            "title": str(title),
            "code": node.get("code"),
            "path": path,
            "depth": depth,
        })
        for child in (node.get(child_field) or []):
            walk(child, cid, path, depth + 1)

    for r in (roots or []):
        walk(r, None, "", 0)
    return nodes


def refresh_catalog_tree(db) -> dict:
    """Reconstruieste tabelul `vinted_catalogs` din /catalog. La orice esec (block,
    arbore neparsabil, < _MIN_NODES) NU sterge datele vechi si logheaza WARN."""
    try:
        resp = vinted_html.get_html(_CATALOG_URL, referer="https://www.vinted.ro/")
    except Exception as exc:
        log_manager.emit("radar", "WARN", f"Catalog Vinted: eroare fetch /catalog: {str(exc)[:100]}")
        return {"ok": False, "reason": "fetch_error", "count": 0}

    html = resp.text or ""
    if resp.status_code != 200 or vinted_html._looks_blocked(resp.status_code, html):
        log_manager.emit("radar", "WARN",
            f"Catalog Vinted: /catalog inaccesibil (HTTP {resp.status_code}) — pastrez datele vechi")
        return {"ok": False, "reason": f"http_{resp.status_code}", "count": 0}

    decoded = vinted_html.decode_next_f(html)
    roots, child_field = _extract_catalog_roots(decoded)
    if not roots:
        log_manager.emit("radar", "WARN", "Catalog Vinted: arbore neparsabil in RSC — pastrez datele vechi")
        return {"ok": False, "reason": "unparsable", "count": 0}

    nodes = build_catalog_nodes(roots, child_field)
    if len(nodes) < _MIN_NODES:
        log_manager.emit("radar", "WARN",
            f"Catalog Vinted: doar {len(nodes)} noduri (<{_MIN_NODES}) — esec, NU sterg datele vechi")
        return {"ok": False, "reason": "too_few", "count": len(nodes)}

    now = datetime.now(timezone.utc)
    try:
        db.query(VintedCatalog).delete()
        db.bulk_insert_mappings(VintedCatalog, [{**n, "updated_at": now} for n in nodes])
        db.commit()
    except Exception as exc:
        db.rollback()
        log_manager.emit("radar", "ERR", f"Catalog Vinted: eroare la scriere: {str(exc)[:100]}")
        return {"ok": False, "reason": "db_error", "count": 0}

    roots_n = sum(1 for n in nodes if n["parent_id"] is None)
    log_manager.emit("radar", "OK",
        f"Catalog Vinted: {len(nodes)} noduri reconstruite ({roots_n} rădăcini, camp copii='{child_field}')")
    return {"ok": True, "count": len(nodes), "roots": roots_n, "child_field": child_field}


# ── interogari pentru endpointuri ───────────────────────────────────────────────
def get_children(db, parent_id) -> list[dict]:
    """Copiii nodului (parent_id None = radacini): [{id, title, has_children}]."""
    q = db.query(VintedCatalog)
    q = q.filter(VintedCatalog.parent_id.is_(None)) if parent_id is None \
        else q.filter(VintedCatalog.parent_id == parent_id)
    rows = q.order_by(VintedCatalog.title).all()
    parents = {p for (p,) in db.query(VintedCatalog.parent_id).distinct().all() if p is not None}
    return [{"id": r.id, "title": r.title, "has_children": r.id in parents} for r in rows]


def find_catalog_id_by_titles(db, category, subcategory):
    """Rezolvare din tabelul dinamic pentru resolver (RP-2, pasul 2): id-ul nodului al
    cărui TITLU normalizat == subcategoria (sau ultimul segment din category), preferând
    potrivirea care are și categoria în path. None dacă nimic / tabel gol."""
    want = normalize(subcategory) or normalize((category or "").split(">")[-1])
    if not want:
        return None
    cat_ctx = normalize((category or "").split(">")[-1]) if category else ""
    rows = db.query(VintedCatalog.id, VintedCatalog.title, VintedCatalog.path).all()
    fallback = None
    for rid, title, path in rows:
        if normalize(title) == want:
            if not cat_ctx or cat_ctx == want or cat_ctx in normalize(path or ""):
                return rid
            if fallback is None:
                fallback = rid
    return fallback


def search_catalogs(db, q: str, limit: int = 20) -> list[dict]:
    """Max `limit` potriviri pe `path`, diacritics-insensitive: [{id, title, path}].
    Prioritizeaza potrivirile in ultimul segment (titlu) + caile scurte."""
    qn = normalize(q)
    if not qn:
        return []
    rows = db.query(VintedCatalog.id, VintedCatalog.title, VintedCatalog.path).all()
    matches = [(rid, title, path) for (rid, title, path) in rows if qn in normalize(path)]
    matches.sort(key=lambda m: (qn not in normalize(m[1]), len(m[2] or "")))
    return [{"id": r[0], "title": r[1], "path": r[2]} for r in matches[:limit]]
