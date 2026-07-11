# -*- coding: utf-8 -*-
"""RP-2 FAZA 0 — sonda arborelui de categorii Vinted din /catalog (RSC __next_f).

READ-ONLY, 1 request (prin limiterul vinted_html). Pineaza forma EXACTA a nodului
(id/title/camp copii/code/url), numarul de radacini si titlurile. Salveaza un
subarbore reprezentativ in tests/fixtures/vinted_catalog_rsc.txt.
"""
import sys
import os
import re
import json
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
FIXTURES = os.path.join(BACKEND, "tests", "fixtures")
sys.path.insert(0, BACKEND)
os.makedirs(FIXTURES, exist_ok=True)

OUT_PATH = os.path.join(HERE, "rp2_sonda_output.txt")
_OUT_F = open(OUT_PATH, "w", encoding="utf-8")


def out(*parts):
    text = " ".join(str(p) for p in parts)
    _OUT_F.write(text + "\n")
    _OUT_F.flush()
    try:
        print(text, flush=True)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


out("RP-2 FAZA 0 — sonda arbore catalog Vinted")
out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

from app.services.radar import vinted_html  # noqa: E402

try:
    resp = vinted_html.get_html("https://www.vinted.ro/catalog", referer="https://www.vinted.ro/")
    out("GET /catalog -> HTTP", resp.status_code, "| len HTML:", len(resp.text or ""))
    html = resp.text or ""
    if resp.status_code != 200 or vinted_html._looks_blocked(resp.status_code, html):
        out("STOP catalog: pagina blocata/nereusita -> partea de catalog se opreste (regula 3)")
        _OUT_F.close()
        sys.exit(0)

    decoded = vinted_html.decode_next_f(html)
    out("RSC decodat len:", len(decoded))

    # ── numararea candidatilor pentru campul de copii ──
    for fld in ['"catalogs":[', '"children":[', '"subcatalogs":[', '"catalog_ids":[']:
        out(f"  ocurente {fld}: {decoded.count(fld)}")
    out("  ocurente '\"code\":':", decoded.count('"code":'))
    out("  ocurente '\"item_count\":':", decoded.count('"item_count"'))
    out("  ocurente 'catalogTree':", decoded.count("catalogTree"))
    out("  perechi id+title (regex):", len(re.findall(r'"id":\d+,"title":"', decoded)))

    # ── context in jurul primului 'catalogTree' (referinta/definitie) ──
    it = decoded.find("catalogTree")
    if it >= 0:
        out("--- context 'catalogTree' (±400) ---")
        out("   " + decoded[max(0, it - 120):it + 280].replace("\n", "\\n"))

    # ── forma exacta a unui nod: prima structura {id,title,...,camp_copii} ──
    m = re.search(r'\{"id":\d+,"title":"[^"]+"', decoded)
    if m:
        p = m.start()
        out("--- forma nod (±1500 in jurul primei structuri id+title) ---")
        out("   " + decoded[p:p + 1500].replace("\n", "\\n"))
    else:
        out("STOP: nicio structura {\"id\":..,\"title\":..} gasita in RSC")
        _OUT_F.close()
        sys.exit(0)

    # ── incearca sa localizezi arborele ca ARRAY JSON parsabil ──
    # Strategie: gaseste '"catalogTree":[' sau '"catalogs":[{"id"' de nivel radacina si
    # balance-match array-ul; parseaza defensiv (Flight poate avea refs "$..").
    def balanced_array(s, start):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, min(len(s), start + 9_000_000)):
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

    child_field = None
    for cand in ["catalogs", "children", "subcatalogs"]:
        if f'"{cand}":[' in decoded:
            child_field = cand
            break
    out("CAMP COPII detectat:", child_field)

    tree_json = None
    tree_src = None
    for marker in ['"catalogTree":[', f'"catalogs":[{{"id"' if child_field == "catalogs" else '"children":[{"id"']:
        mi = decoded.find(marker)
        if mi < 0:
            continue
        arr_start = decoded.find("[", mi)
        raw = balanced_array(decoded, arr_start)
        if not raw:
            continue
        try:
            tree_json = json.loads(raw)
            tree_src = marker
            break
        except Exception as e:
            out(f"  array la '{marker}' negparsabil direct: {str(e)[:80]}")
            # verifica daca contine refs Flight
            out("  contine refs '$'?:", '"$' in raw[:5000])

    if tree_json:
        out("ARBORE PARSAT direct din:", tree_src)
        roots = tree_json if isinstance(tree_json, list) else tree_json.get("catalogs")
        out("nr radacini:", len(roots))
        out("titluri radacina:", [r.get("title") for r in roots][:40])
        r0 = next((r for r in roots if r.get(child_field)), roots[0])
        out("chei nod radacina:", list(r0.keys()))
        out("primul nod cu copii: id=", r0.get("id"), "title=", r0.get("title"),
            "code=", r0.get("code"), "nr_copii=", len(r0.get(child_field) or []))
        ch = (r0.get(child_field) or [])
        if ch:
            c0 = ch[0]
            out("  copil[0]: chei=", list(c0.keys()), "| id=", c0.get("id"),
                "title=", c0.get("title"), "nr_nepoti=", len(c0.get(child_field) or []))
        # ── fixture: subarbore reprezentativ (radacini + 2 niveluri), <=200KB ──
        sample = []
        for r in roots:
            rc = {k: r.get(k) for k in ("id", "title", "code", "url") if k in r}
            kids = []
            for c in (r.get(child_field) or [])[:4]:
                cc = {k: c.get(k) for k in ("id", "title", "code", "url") if k in c}
                cc[child_field] = [{k: g.get(k) for k in ("id", "title", "code") if k in g}
                                   for g in (c.get(child_field) or [])[:4]]
                kids.append(cc)
            rc[child_field] = kids
            sample.append(rc)
        fx = os.path.join(FIXTURES, "vinted_catalog_rsc.txt")
        payload = json.dumps({"child_field": child_field, "catalogs": sample}, ensure_ascii=False, indent=1)
        with open(fx, "w", encoding="utf-8") as f:
            f.write(payload[:200_000])
        out("fixture salvat:", fx, "->", os.path.getsize(fx), "bytes")
        out("VERDICT F0: OK — arbore parsabil; camp copii =", child_field)
    else:
        out("STOP catalog: arborele nu se parseaza direct ca JSON (posibil Flight refs) —")
        out("  salvez o felie de ~200KB in jurul primei structuri pentru analiza ulterioara")
        fx = os.path.join(FIXTURES, "vinted_catalog_rsc.txt")
        with open(fx, "w", encoding="utf-8") as f:
            f.write(decoded[m.start():m.start() + 200_000])
        out("felie salvata:", fx, "->", os.path.getsize(fx), "bytes")
        out("VERDICT F0: PARTIAL — vezi forma nodului de mai sus pentru design parser")
except Exception as e:
    import traceback
    out("F0 EXCEPTIE:", "".join(traceback.format_exc())[:2000])

out("[RP-2 FAZA 0 terminat]")
_OUT_F.close()
