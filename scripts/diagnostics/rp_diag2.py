# -*- coding: utf-8 -*-
"""RP-DIAG-2 — probe tintite READ-ONLY dupa rezultatele RP-DIAG.

STRICT DIAGNOSTIC. Nu modifica niciun fisier existent (backend/, frontend/,
rp_diag.py). Singurele fisiere noi: acest script + rp_diag2_output.txt (NECOMISE).
Nu ruleaza git add/commit/push. Nu printeaza cookie-uri/tokeni/headere de auth/
continut de sesiune. Nu printeaza HTML masiv — doar inventare + extrase tintite.

Ruleaza cu venv-ul backend-ului, din radacina repo-ului:
    backend/venv/Scripts/python.exe scripts/diagnostics/rp_diag2.py
"""
import sys
import os
import json
import re
import time
import glob
import subprocess
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND)

OUT_PATH = os.path.join(HERE, "rp_diag2_output.txt")
# Mod "v12" = re-rulare TINTITA doar a V1+V2 cu euristica de block corectata
# (paginile legitime includ SDK-ul DataDome -> nu inseamna block). Append, nu re-scrie.
_V12 = len(sys.argv) > 1 and sys.argv[1] == "v12"
_V3P = len(sys.argv) > 1 and sys.argv[1] == "v3probe"
_OUT_F = open(OUT_PATH, "a" if (_V12 or _V3P) else "w", encoding="utf-8")

REQ = {"n": 0}  # contor global de requesturi HTTP


def out(*parts):
    text = " ".join(str(p) for p in parts)
    _OUT_F.write(text + "\n")
    _OUT_F.flush()
    try:
        print(text, flush=True)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


_VERDICTS = []


def verdict(step, status, concl, detail=None):
    out(f"VERDICT {step}: {status} — {detail if detail else concl}")
    safe = re.sub(r"\s+", " ", concl).replace("|", "/").strip()
    _VERDICTS.append((step, status, safe[:120]))


_SENSITIVE = re.compile(
    r"(e[-_]?mail|token|msisdn|phone|telefon|password|passwd|secret|cookie|"
    r"session|access_token|refresh|api[_-]?key|apikey|authenticity|csrf|bearer)",
    re.I,
)


def scrub(obj, _depth=0):
    if _depth > 12:
        return "…"
    if isinstance(obj, dict):
        c = {}
        for k, v in obj.items():
            c[k] = "<redacted>" if (isinstance(k, str) and _SENSITIVE.search(k)) else scrub(v, _depth + 1)
        return c
    if isinstance(obj, list):
        return [scrub(x, _depth + 1) for x in obj]
    return obj


def jdump(obj, limit=1500):
    try:
        s = json.dumps(scrub(obj), indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        s = f"<json dump error: {e}> repr={repr(obj)[:limit]}"
    if len(s) > limit:
        s = s[:limit] + f"\n… [trunchiat la {limit}]"
    return s


def keys_of(d):
    return list(d.keys()) if isinstance(d, dict) else f"<not dict: {type(d).__name__}>"


def find_paths(obj, tokens, path="root", acc=None, seen=None, _depth=0):
    if acc is None:
        acc = []
    if seen is None:
        seen = set()
    if _depth > 16:
        return acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(t in kl for t in tokens):
                key = f"{path}.{k}"
                if key not in seen:
                    seen.add(key)
                    acc.append((key, v))
            find_paths(v, tokens, f"{path}.{k}", acc, seen, _depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_paths(v, tokens, f"{path}[{i}]", acc, seen, _depth + 1)
    return acc


def ctx_all(haystack, needle, radius=300, max_hits=4):
    """Context brut (spatii normalizate) in jurul fiecarei aparitii a needle."""
    low = haystack.lower()
    nl = needle.lower()
    idx = 0
    hits = 0
    while hits < max_hits:
        p = low.find(nl, idx)
        if p < 0:
            break
        seg = haystack[max(0, p - radius): p + len(needle) + radius]
        seg = re.sub(r"\s+", " ", seg).strip()
        out(f"  [ctx '{needle}' @ {p}]: …{seg}…")
        idx = p + len(needle)
        hits += 1
    if hits == 0:
        out(f"  '{needle}': ABSENT")
    return hits


def find_tree(obj, path="root", _depth=0, best=None):
    """Cauta o lista de obiecte {id,title,...} cu copii recursivi (acelasi shape)."""
    if best is None:
        best = {"path": None, "count": 0, "node": None}
    if _depth > 16:
        return best
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        shaped = [x for x in obj if ("id" in x and ("title" in x or "name" in x))]
        if len(shaped) >= 2:
            def has_child_list(n):
                for kk, vv in n.items():
                    if isinstance(vv, list) and vv and all(isinstance(z, dict) and "id" in z for z in vv):
                        return kk
                return None
            child_keys = [has_child_list(n) for n in shaped]
            if any(child_keys) and len(shaped) > best["count"]:
                best = {"path": path, "count": len(shaped), "node": shaped,
                        "child_key": next((c for c in child_keys if c), None)}
    if isinstance(obj, dict):
        for k, v in obj.items():
            best = find_tree(v, f"{path}.{k}", _depth + 1, best)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            best = find_tree(v, f"{path}[{i}]", _depth + 1, best)
    return best


def try_parse(content, typ=""):
    c = (content or "").strip()
    if not c:
        return None
    if "json" in (typ or "").lower():
        try:
            return json.loads(c)
        except Exception:
            pass
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", c, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    if c[:1] in "{[":
        try:
            return json.loads(c)
        except Exception:
            pass
    return None


def banner(step, title):
    out("")
    out("=" * 78)
    out(f"==={step}===  {title}")
    out("=" * 78)


out("RP-DIAG-2 — probe tintite read-only Radar Piata")
out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
out(f"repo_root: {REPO_ROOT}")
out("NOTA: fisier NECOMIS. Fara git add/commit/push. Fara cookie-uri/tokeni.")

from bs4 import BeautifulSoup  # noqa: E402
from curl_cffi import requests as curl_requests  # noqa: E402


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ RE-RUN GATED V1+V2 (python rp_diag2.py v12) — euristica de block corectata ║
# ╚══════════════════════════════════════════════════════════════════════════╝
if _V12:
    out("")
    out("#" * 78)
    out("=== RE-RUN CORECTAT V1+V2 (euristica block DataDome reparata) ===")
    out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out("Motiv: pagina item + /catalog au raspuns 200 cu HTML real mare; substringul")
    out("'datadome' e DOAR SDK-ul client (prezent pe orice pagina legitima), NU un block.")
    out("#" * 78)

    def is_blocked(status, body):
        low = (body or "").lower()
        if status == 403:
            return True, "HTTP 403"
        if status == 200 and len(body) < 40000 and (
                "captcha-delivery" in low or ("datadome" in low and "captcha" in low)):
            return True, f"interstitial mic ({len(body)}B) cu markeri challenge"
        return False, f"HTTP {status}, {len(body)}B (SDK datadome = normal, nu block)"

    S2 = None
    IMP2 = None
    for cand in ["chrome131", "chrome124", "chrome120", "chrome110"]:
        try:
            S2 = curl_requests.Session(impersonate=cand, timeout=20, allow_redirects=True)
            IMP2 = cand
            break
        except Exception:
            continue
    _ACL = {"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}
    _RQ = {"n": 0}

    def g(url):
        _RQ["n"] += 1
        return S2.get(url, headers=_ACL)

    def inv_scripts(soup, body):
        out("--- markere ---")
        for mk in ["__NEXT_DATA__", "react-on-rails", "data-js-react-on-rails-store", "__PRELOADED_STATE__"]:
            out(f"  '{mk}' prezent:", mk in body)
        out("--- inventar <script> (json/data-*) ---")
        blobs = []
        for i, sc in enumerate(soup.find_all("script")):
            typ = sc.get("type") or ""
            attrs = {k: v for k, v in sc.attrs.items() if k != "nonce"}
            content = sc.string or sc.text or ""
            if ("json" in typ.lower() or "data-js-react-on-rails-store" in sc.attrs
                    or any(str(k).startswith("data-") for k in sc.attrs)):
                out(f"  script[{i}] type={typ!r} id={sc.get('id')!r} attrs={list(attrs.keys())} len={len(content)}")
            label = (attrs.get("data-js-react-on-rails-store") or sc.get("id")
                     or (typ if "json" in typ.lower() else f"script{i}"))
            blobs.append((f"script[{i}]:{label}", typ, content))
        return blobs

    # ── V1b ──
    out("")
    out("===V1b===  Vinted item HTML (corectat)")
    tokens = ["descript", "feedback", "attribut", "battery", "capac", "model",
              "sim", "storage", "colour", "color", "created", "timestamp", "login"]
    try:
        url1 = "https://www.vinted.ro/items/9361761602-iphone-12-promax"
        item_id = "9361761602"
        r = g(url1)
        blk, why = is_blocked(r.status_code, r.text or "")
        out(f"GET {url1} -> {why}; blocat={blk}")
        if blk:
            verdict("V1b", "NU", f"item blocat real: {why}")
        else:
            body = r.text or ""
            soup = BeautifulSoup(body, "html.parser")
            blobs = inv_scripts(soup, body)
            summary = {"descriere": None, "atribute": None, "feedback": None, "data": None, "login": None}
            any_struct = False
            for label, typ, content in blobs:
                if item_id not in content:
                    continue
                parsed = try_parse(content, typ)
                if parsed is None:
                    continue
                any_struct = True
                out(f"--- blob PARSAT: {label} (len={len(content)}) ---")
                hits = find_paths(parsed, tokens, label.split(":")[-1] or "next")
                out(f"  hits: {len(hits)} (max 60)")
                for pth, val in hits[:60]:
                    pl = pth.lower()
                    if summary["descriere"] is None and "descript" in pl:
                        summary["descriere"] = pth
                    if summary["atribute"] is None and any(t in pl for t in ["attribut", "battery", "storage", "capac"]):
                        summary["atribute"] = pth
                    if summary["feedback"] is None and "feedback" in pl:
                        summary["feedback"] = pth
                    if summary["data"] is None and ("created" in pl or "timestamp" in pl):
                        summary["data"] = pth
                    if summary["login"] is None and "login" in pl:
                        summary["login"] = pth
                    if isinstance(val, (str, int, float, bool)) or val is None:
                        out(f"    {pth} = {str(val)[:300]}")
                    else:
                        out(f"    {pth}:")
                        out("      " + jdump(val, 1200).replace("\n", "\n      "))
            if not any_struct:
                out("--- fara blob JSON cu item_id: fallback DOM ---")
                og = soup.find("meta", attrs={"property": "og:description"})
                out("  og:description:", (og.get("content")[:300] if og and og.get("content") else "ABSENT"))
                for ip in soup.find_all(attrs={"itemprop": True})[:25]:
                    out(f"    <{ip.name} itemprop={ip.get('itemprop')!r}> = {ip.get_text(' ', strip=True)[:120]}")
                for needle in ["Sănătatea bateriei", "Capacitate de stocare", "Sanatatea bateriei"]:
                    ctx_all(body, needle, radius=600, max_hits=2)
            verdict("V1b", "OK",
                    f"item accesibil cu {IMP2}; sursa={'JSON blob' if any_struct else 'DOM'}; "
                    f"cai: descriere={summary['descriere']} atribute={summary['atribute']} "
                    f"feedback={summary['feedback']} data={summary['data']} login={summary['login']}")
    except Exception as e:
        out("V1b EXCEPTIE:", "".join(traceback.format_exc())[:1500])
        verdict("V1b", "FAIL", f"eroare V1b: {str(e)[:120]}")

    # ── V2b ──
    out("")
    out("===V2b===  Vinted /catalog arbore (corectat)")
    try:
        time.sleep(5)
        r = g("https://www.vinted.ro/catalog")
        blk, why = is_blocked(r.status_code, r.text or "")
        out(f"GET /catalog -> {why}; blocat={blk}")
        body = r.text or ""
        if blk:
            verdict("V2b", "NU", f"catalog blocat real: {why}")
        else:
            soup = BeautifulSoup(body, "html.parser")
            inv_scripts(soup, body)
            best = {"path": None, "count": 0, "node": None}
            n_parsed = 0
            for i, sc in enumerate(soup.find_all("script")):
                typ = sc.get("type") or ""
                content = sc.string or sc.text or ""
                if "catalog" not in content.lower():
                    continue
                parsed = try_parse(content, typ)
                if parsed is None:
                    continue
                n_parsed += 1
                cat_hits = find_paths(parsed, ["catalog"], f"s{i}")
                if cat_hits:
                    out(f"  script[{i}] id={sc.get('id')!r}: {len(cat_hits)} chei 'catalog' (ex {[h[0] for h in cat_hits[:6]]})")
                b = find_tree(parsed, f"script{i}")
                if b["count"] > best["count"]:
                    best = b
            out(f"bloburi cu 'catalog' parsate: {n_parsed}")
            if best["node"]:
                nodes = best["node"]
                ck = best.get("child_key")
                out("arbore la:", best["path"], "| child_key:", ck, "| nr radacini:", len(nodes))
                out("titluri radacina:", [n.get("title") or n.get("name") for n in nodes][:40])
                first2 = next((n for n in nodes if isinstance(n.get(ck), list) and len(n.get(ck)) >= 2), None) if ck else None
                if first2:
                    out("primul nod cu >=2 copii: id=", first2.get("id"), "title=", first2.get("title") or first2.get("name"))
                    for chn in (first2.get(ck) or [])[:2]:
                        gk = next((kk for kk, vv in chn.items() if isinstance(vv, list) and vv and all(isinstance(z, dict) and "id" in z for z in vv)), None)
                        out("   copil: id=", chn.get("id"), "title=", chn.get("title") or chn.get("name"),
                            "nr_copii=", len(chn.get(gk) or []) if gk else 0)
            else:
                out("nu am gasit arbore {id,title,children[]} in bloburi")
            # endpoint real
            found_ep = set(re.findall(r"api/v2/catalog[\w/.-]*", body))
            for ep in sorted(found_ep)[:10]:
                p = body.find(ep)
                out(f"  [HTML] {ep}: …{re.sub(chr(92)+'s+',' ', body[max(0,p-80):p+len(ep)+80])}…")
            bundles = [s.get("src") for s in soup.find_all("script", src=True) if "catalog" in (s.get("src") or "").lower()]
            out("bundle-uri JS cu 'catalog' in nume:", bundles[:5])
            for src in bundles[:2]:
                if _RQ["n"] >= 5:
                    out("  (buget atins -> nu descarc bundle)")
                    break
                bsrc = src if src.startswith("http") else ("https://www.vinted.ro" + src if src.startswith("/") else "https:" + src)
                time.sleep(4)
                rb = g(bsrc)
                out(f"  bundle {bsrc[:90]} -> HTTP {rb.status_code} len={len(rb.text or '')}")
                if rb.status_code == 200:
                    for ep in sorted(set(re.findall(r"api/v2/catalog[\w/.-]*", rb.text)))[:10]:
                        pp = rb.text.find(ep)
                        out(f"    [JS] {ep}: …{re.sub(chr(92)+'s+',' ', rb.text[max(0,pp-80):pp+len(ep)+80])}…")
                        found_ep.add(ep)
            verdict("V2b", "OK" if (best["node"] or found_ep) else "NU",
                    f"arbore in HTML={'DA @'+str(best['path']) if best['node'] else 'NU'}; endpointuri={sorted(found_ep)[:6]}")
    except Exception as e:
        out("V2b EXCEPTIE:", "".join(traceback.format_exc())[:1500])
        verdict("V2b", "FAIL", f"eroare V2b: {str(e)[:120]}")

    out("")
    out(f"requesturi in re-run v12 (aprox): {_RQ['n']}")
    out("### TABEL SUPLIMENTAR (corectat)")
    out("| Pas | Verdict | Concluzie |")
    out("|-----|---------|-----------|")
    for step, status, concl in _VERDICTS:
        out(f"| {step} | {status} | {concl} |")
    out("[RP-DIAG-2 v12 terminat]")
    _OUT_F.close()
    sys.exit(0)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ PROBE 3 (python rp_diag2.py v3probe) — continut RSC __next_f (App Router)  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
if _V3P:
    out("")
    out("#" * 78)
    out("=== PROBE 3: continut RSC __next_f (Next.js App Router) pe item + /catalog ===")
    out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out("Motiv: paginile Vinted sunt Next.js App Router (fara __NEXT_DATA__); datele SSR")
    out("stau in chunk-uri self.__next_f.push([...]). Verific daca seller/atribute/arbore")
    out("catalog sunt embedded (regex-abile) sau doar client-side (API-ul 403).")
    out("#" * 78)

    S3 = None
    for cand in ["chrome131", "chrome124", "chrome120", "chrome110"]:
        try:
            S3 = curl_requests.Session(impersonate=cand, timeout=20, allow_redirects=True)
            break
        except Exception:
            continue
    _ACL = {"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}
    _RQ = {"n": 0}

    def g3(url):
        _RQ["n"] += 1
        return S3.get(url, headers=_ACL)

    def analyze_next_f(body, needles, radius=180, max_hits=2):
        present = "__next_f" in body
        pushes = len(re.findall(r"__next_f\.push\(", body))
        out(f"  __next_f prezent: {present}; nr push(): {pushes}")
        counts = {}
        for nd in needles:
            counts[nd] = body.lower().count(nd.lower())
        out("  ocurente substring (raw body):", {k: v for k, v in counts.items() if v})
        return present, pushes, counts

    # ---- item ----
    out("")
    out("===V1c===  RSC __next_f pe pagina item")
    try:
        url1 = "https://www.vinted.ro/items/9361761602-iphone-12-promax"
        r = g3(url1)
        body = r.text or ""
        out(f"item -> HTTP {r.status_code}, {len(body)}B")
        soup = BeautifulSoup(body, "html.parser")
        for sc in soup.find_all("script", type="application/ld+json"):
            try:
                out("ld+json integral:")
                out(jdump(json.loads(sc.string or "{}"), 1500))
            except Exception:
                out("  <ld+json neparsabil>")
        item_needles = ["__next_f", "iruyry", "\"login\"", "feedback", "feedback_count",
                        "reputation", "Sănătatea", "Sanatatea", "Capacitate", "stocare",
                        "\"attributes\"", "\"brand", "\"status\"", "created_at", "api/v2/"]
        present, pushes, counts = analyze_next_f(body, item_needles)
        for nd in ["iruyry", "feedback", "Sănătatea", "Capacitate", "\"attributes\"", "api/v2/"]:
            if counts.get(nd):
                ctx_all(body, nd, radius=180, max_hits=1)
        seller_embedded = counts.get("iruyry", 0) > 0 or counts.get("feedback", 0) > 0
        attr_embedded = counts.get("\"attributes\"", 0) > 0 or counts.get("Capacitate", 0) > 0 or counts.get("Sănătatea", 0) > 0
        verdict("V1c", "OK",
                f"item CSR App Router; ld+json = descriere+color; seller in HTML={seller_embedded}; "
                f"atribute in HTML={attr_embedded}; api/v2 refs in HTML={counts.get('api/v2/',0)}")
    except Exception as e:
        out("V1c EXCEPTIE:", "".join(traceback.format_exc())[:1200])
        verdict("V1c", "FAIL", f"eroare V1c: {str(e)[:120]}")

    # ---- catalog ----
    out("")
    out("===V2c===  RSC __next_f pe /catalog")
    try:
        time.sleep(5)
        r = g3("https://www.vinted.ro/catalog")
        body = r.text or ""
        out(f"catalog -> HTTP {r.status_code}, {len(body)}B")
        cat_needles = ["__next_f", "\"catalog", "api/v2/catalog", "\"title\"", "\"code\"",
                       "\"unisex", "children", "\"catalogs\""]
        present, pushes, counts = analyze_next_f(body, cat_needles)
        eps = sorted(set(re.findall(r"api/v2/catalog[\w/.-]*", body)))
        out("endpointuri catalog in body:", eps[:10])
        # semnal de arbore embedded: multe perechi id/title/code
        id_title = len(re.findall(r'\\?"id\\?":\d+,\\?"title\\?"', body))
        code_fields = body.count('"code"') + body.count('\\"code\\"')
        out(f"perechi id+title (regex, incl. escaped): {id_title}; campuri 'code': {code_fields}")
        tree_signal = id_title > 20 or counts.get("\"catalogs\"", 0) > 0
        verdict("V2c", "OK" if (tree_signal or eps) else "NU",
                f"catalog CSR App Router; arbore embedded in __next_f probabil={tree_signal} "
                f"(id+title={id_title}); endpointuri api/v2/catalog={eps[:4]}")
    except Exception as e:
        out("V2c EXCEPTIE:", "".join(traceback.format_exc())[:1200])
        verdict("V2c", "FAIL", f"eroare V2c: {str(e)[:120]}")

    out("")
    out(f"requesturi in probe3 (aprox): {_RQ['n']}")
    out("### TABEL PROBE 3")
    out("| Pas | Verdict | Concluzie |")
    out("|-----|---------|-----------|")
    for step, status, concl in _VERDICTS:
        out(f"| {step} | {status} | {concl} |")
    out("[RP-DIAG-2 v3probe terminat]")
    _OUT_F.close()
    sys.exit(0)


# ╔════════════════════════ V0 ════════════════════════╗
SESSION = None
IMP = "chrome131"
try:
    banner("V0", "Clientul de test (curl_cffi, fingerprint de browser)")
    import curl_cffi
    out("curl_cffi version:", curl_cffi.__version__)
    for cand in ["chrome131", "chrome124", "chrome120", "chrome110"]:
        try:
            SESSION = curl_requests.Session(impersonate=cand, timeout=20, allow_redirects=True)
            IMP = cand
            break
        except Exception as e:
            out(f"  impersonate={cand} indisponibil: {str(e)[:80]}")
    if SESSION is None:
        verdict("V0", "FAIL", "nu am putut construi o sesiune curl_cffi")
    else:
        out(f"sesiune construita: impersonate={IMP}, timeout=20, allow_redirects=True")
        out("headere: DOAR Accept-Language adaugat (UA = cel al impersonarii, neatins)")
        verdict("V0", "OK", f"curl_cffi {curl_cffi.__version__}; impersonate={IMP}; fara UA custom")
except Exception as e:
    out("V0 EXCEPTIE:", "".join(traceback.format_exc())[:1200])
    verdict("V0", "FAIL", f"eroare V0: {str(e)[:120]}")

_ACLANG = {"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}


def vget(url):
    REQ["n"] += 1
    return SESSION.get(url, headers=_ACLANG)


# ╔════════════════════════ V1 ════════════════════════╗
try:
    banner("V1", "Vinted: pagina HTML a unui item (tinta principala)")
    if SESSION is None:
        verdict("V1", "FAIL", "fara sesiune curl_cffi (V0 esuat)")
    else:
        candidates = [
            "https://www.vinted.ro/items/9361761602-iphone-12-promax",
            "https://www.vinted.ro/items/9361771979-etui-na-telefon-iphone-12-pro",
        ]
        item_url = None
        item_id = None
        resp = None
        for c in candidates:
            r = vget(c)
            out(f"candidat {c} -> HTTP {r.status_code}")
            if r.status_code == 200:
                item_url = c
                resp = r
                mid = re.search(r"/items/(\d+)", c)
                item_id = mid.group(1) if mid else None
                break
            time.sleep(4)
        if item_url is None:
            out("ambii candidati non-200 -> caut un item nou prin VintedWrapper")
            try:
                from vinted_scraper import VintedWrapper
                w = None
                for a in range(2):
                    try:
                        w = VintedWrapper("https://www.vinted.ro")
                        break
                    except Exception as e:
                        out(f"  wrapper attempt {a+1}/2: {str(e)[:90]}")
                        time.sleep(6)
                if w:
                    REQ["n"] += 2  # cookie + search (aprox)
                    s = w.search({"search_text": "iphone 12 pro", "order": "newest_first", "per_page": 20})
                    for it in (s.get("items") or []):
                        if "iphone" in (it.get("title") or "").lower():
                            item_id = str(it.get("id"))
                            item_url = it.get("url") or f"https://www.vinted.ro/items/{item_id}"
                            break
                    if item_url:
                        time.sleep(5)
                        resp = vget(item_url)
                        out(f"item nou {item_url} -> HTTP {resp.status_code}")
            except Exception as e:
                out("  fallback search esuat:", str(e)[:120])

        if resp is None or item_url is None:
            verdict("V1", "NU", "niciun item accesibil (candidati 404 + fallback esuat)")
        else:
            body = resp.text or ""
            out("status HTTP:", resp.status_code)
            out("primele 300 caractere body:", re.sub(r"\s+", " ", body[:300]))
            low = body.lower()
            if resp.status_code == 403 or "datadome" in low or "captcha" in low:
                out("EVIDENTA NEGATIVA: status 403 sau body contine datadome/captcha")
                verdict("V1", "NU", f"pagina item blocata (HTTP {resp.status_code}, datadome/captcha in body)")
            else:
                soup = BeautifulSoup(body, "html.parser")
                out("--- markere ---")
                for mk in ["__NEXT_DATA__", "react-on-rails", "data-js-react-on-rails-store", "__PRELOADED_STATE__"]:
                    out(f"  '{mk}' prezent in HTML:", mk in body)
                out("--- inventar <script> (json / data-*) ---")
                blobs = []
                for i, sc in enumerate(soup.find_all("script")):
                    typ = sc.get("type") or ""
                    attrs = {k: v for k, v in sc.attrs.items() if k != "nonce"}
                    content = sc.string or sc.text or ""
                    interesting = ("json" in typ.lower()
                                   or "data-js-react-on-rails-store" in sc.attrs
                                   or any(str(k).startswith("data-") for k in sc.attrs))
                    if interesting:
                        out(f"  script[{i}] type={typ!r} attrs={list(attrs.keys())} len={len(content)}")
                    label = (attrs.get("data-js-react-on-rails-store")
                             or attrs.get("id") or (typ if "json" in typ.lower() else f"script{i}"))
                    blobs.append((f"script[{i}]:{label}", typ, content))

                tokens = ["descript", "feedback", "attribut", "battery", "capac", "model",
                          "sim", "storage", "colour", "color", "created", "timestamp", "login"]
                any_struct = False
                paths_summary = {"descriere": None, "atribute": None, "feedback": None, "data": None}
                for label, typ, content in blobs:
                    if item_id and str(item_id) not in content:
                        continue
                    parsed = try_parse(content, typ)
                    if parsed is None:
                        continue
                    any_struct = True
                    out(f"--- blob PARSAT: {label} (len={len(content)}) ---")
                    hits = find_paths(parsed, tokens, label.split(":")[-1] or "store")
                    out(f"  hits chei relevante: {len(hits)} (afisez max 50)")
                    for pth, val in hits[:50]:
                        pl = pth.lower()
                        if paths_summary["descriere"] is None and "descript" in pl:
                            paths_summary["descriere"] = pth
                        if paths_summary["atribute"] is None and ("attribut" in pl or "battery" in pl or "storage" in pl or "capac" in pl):
                            paths_summary["atribute"] = pth
                        if paths_summary["feedback"] is None and "feedback" in pl:
                            paths_summary["feedback"] = pth
                        if paths_summary["data"] is None and ("created" in pl or "timestamp" in pl):
                            paths_summary["data"] = pth
                        if isinstance(val, (str, int, float, bool)) or val is None:
                            out(f"    {pth} = {str(val)[:300]}")
                        else:
                            out(f"    {pth}:")
                            out("      " + jdump(val, 1500).replace("\n", "\n      "))

                if not any_struct:
                    out("--- FARA blob JSON parsabil: fallback DOM ---")
                    og = soup.find("meta", attrs={"property": "og:description"})
                    out("  og:description:", (og.get("content")[:300] if og and og.get("content") else "ABSENT"))
                    itemprops = soup.find_all(attrs={"itemprop": True})
                    out(f"  itemprop taguri: {len(itemprops)}")
                    for ip in itemprops[:25]:
                        out(f"    <{ip.name} itemprop={ip.get('itemprop')!r}> = {ip.get_text(' ', strip=True)[:120]}")
                    for needle in ["Sănătatea bateriei", "Capacitate de stocare", "Sanatatea bateriei"]:
                        ctx_all(body, needle, radius=600, max_hits=2)

                verdict(
                    "V1",
                    "OK" if (any_struct or resp.status_code == 200) else "NU",
                    f"pagina accesibila cu {IMP}=DA; sursa={'blob JSON' if any_struct else 'DOM fallback'}; "
                    f"cai: descriere={paths_summary['descriere']} atribute={paths_summary['atribute']} "
                    f"feedback={paths_summary['feedback']} data={paths_summary['data']}",
                )
except Exception as e:
    out("V1 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("V1", "FAIL", f"eroare V1: {str(e)[:120]}")


# ╔════════════════════════ V2 ════════════════════════╗
try:
    banner("V2", "Vinted: arborele de categorii din pagina /catalog")
    if SESSION is None:
        verdict("V2", "FAIL", "fara sesiune curl_cffi")
    else:
        time.sleep(5)
        r = vget("https://www.vinted.ro/catalog")
        out("GET /catalog -> HTTP", r.status_code, "| len body:", len(r.text or ""))
        body = r.text or ""
        if r.status_code != 200 or len(body) < 2000:
            out("  /catalog neutil -> incerc homepage")
            time.sleep(5)
            r = vget("https://www.vinted.ro/")
            out("GET / -> HTTP", r.status_code, "| len body:", len(r.text or ""))
            body = r.text or ""
        low = body.lower()
        if r.status_code == 403 or "datadome" in low or "captcha" in low:
            out("EVIDENTA NEGATIVA: 403 / datadome / captcha")
            verdict("V2", "NU", f"pagina catalog blocata (HTTP {r.status_code})")
        else:
            soup = BeautifulSoup(body, "html.parser")
            best = {"path": None, "count": 0, "node": None}
            n_parsed = 0
            for i, sc in enumerate(soup.find_all("script")):
                typ = sc.get("type") or ""
                content = sc.string or sc.text or ""
                if "catalog" not in content.lower():
                    continue
                parsed = try_parse(content, typ)
                if parsed is None:
                    continue
                n_parsed += 1
                cat_hits = find_paths(parsed, ["catalog"], f"script{i}")
                if cat_hits:
                    out(f"  script[{i}] type={typ!r}: {len(cat_hits)} chei 'catalog' (ex: {[h[0] for h in cat_hits[:5]]})")
                b = find_tree(parsed, f"script{i}")
                if b["count"] > best["count"]:
                    best = b
            out(f"bloburi cu 'catalog' parsate: {n_parsed}")
            if best["node"]:
                nodes = best["node"]
                out("arbore gasit la:", best["path"], "| child_key:", best.get("child_key"))
                out("nr noduri radacina:", len(nodes))
                out("titluri radacina:", [n.get("title") or n.get("name") for n in nodes][:40])
                ck = best.get("child_key")
                first2 = None
                for n in nodes:
                    ch = n.get(ck) if ck else None
                    if isinstance(ch, list) and len(ch) >= 2:
                        first2 = n
                        break
                if first2:
                    out("primul nod cu >=2 copii: id=", first2.get("id"), "title=", first2.get("title") or first2.get("name"))
                    for chn in (first2.get(ck) or [])[:2]:
                        gk = None
                        for kk, vv in chn.items():
                            if isinstance(vv, list) and vv and all(isinstance(z, dict) and "id" in z for z in vv):
                                gk = kk
                                break
                        out("   copil: id=", chn.get("id"), "title=", chn.get("title") or chn.get("name"),
                            "nr_copii=", len(chn.get(gk) or []) if gk else 0)
                tree_ok = True
            else:
                out("nu am gasit arbore {id,title,catalogs[]} in bloburile HTML")
                tree_ok = False

            # Bonus: endpoint real din HTML + max 2 bundle-uri JS cu 'catalog' in nume
            out("--- bonus: cautare 'api/v2/catalog' in HTML + bundle-uri ---")
            found_ep = set()
            for m in re.findall(r"api/v2/catalog[\w/.-]*", body):
                found_ep.add(m)
            for ep in list(found_ep)[:10]:
                p = body.find(ep)
                seg = re.sub(r"\s+", " ", body[max(0, p - 80):p + len(ep) + 80])
                out(f"  [HTML] {ep}: …{seg}…")
            bundles = [s.get("src") for s in soup.find_all("script", src=True) if "catalog" in (s.get("src") or "").lower()]
            out("bundle-uri JS cu 'catalog' in nume:", bundles[:5])
            for src in bundles[:2]:
                if REQ["n"] >= 13:
                    out("  (buget requesturi atins -> nu descarc bundle-ul)")
                    break
                bsrc = src if src.startswith("http") else ("https://www.vinted.ro" + src if src.startswith("/") else "https:" + src)
                time.sleep(4)
                rb = vget(bsrc)
                out(f"  bundle {bsrc[:90]} -> HTTP {rb.status_code} len={len(rb.text or '')}")
                if rb.status_code == 200:
                    eps = set(re.findall(r"api/v2/catalog[\w/.-]*", rb.text))
                    for ep in list(eps)[:10]:
                        p = rb.text.find(ep)
                        seg = re.sub(r"\s+", " ", rb.text[max(0, p - 80):p + len(ep) + 80])
                        out(f"    [JS] {ep}: …{seg}…")
                        found_ep.add(ep)

            verdict(
                "V2",
                "OK" if (best["node"] or found_ep) else "NU",
                f"arbore in blob HTML={'DA @'+str(best['path']) if best['node'] else 'NU'}; "
                f"endpointuri catalog descoperite={sorted(found_ep)[:6]}",
            )
except Exception as e:
    out("V2 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("V2", "FAIL", f"eroare V2: {str(e)[:120]}")


# ╔════════════════════════ V3 ════════════════════════╗
try:
    banner("V3", "Okazii: vanzator real + calificative + data (max 3 detalii)")
    from app.services.radar.okazii_scraper import _build_url as okazii_build, _request as okazii_req

    surl = okazii_build("iphone 12 pro", None, "all", None, None, 1)
    out("search url:", surl)
    REQ["n"] += 1
    shtml = okazii_req(surl)
    if not shtml:
        verdict("V3", "FAIL", "fara raspuns la search Okazii")
    else:
        soup = BeautifulSoup(shtml, "html.parser")
        cards = soup.select("#listing-Okazii .list-item")
        links = []
        for c in cards:
            lt = (c.select_one("figure.item-image a[href]")
                  or c.select_one(".item-title h2 a[href]")
                  or c.find("a", href=True))
            if lt and lt.get("href"):
                href = lt.get("href")
                if href.startswith("/"):
                    href = "https://www.okazii.ro" + href
                if href not in links:
                    links.append(href)
            if len(links) >= 3:
                break
        out("primele linkuri:", links)
        found_page = None
        last_soup = None
        for idx, link in enumerate(links[:3]):
            if idx > 0:
                time.sleep(4)
            REQ["n"] += 1
            dh = okazii_req(link)
            if not dh:
                out(f"  detaliu {idx} fara raspuns")
                continue
            last_soup = BeautifulSoup(dh, "html.parser")
            has = "calificativ" in dh.lower()
            out(f"  detaliu {idx} ({link[:70]}...): contine 'calificativ' = {has}")
            if has:
                found_page = (link, dh, last_soup)
                break
        if found_page:
            link, dh, ds = found_page
            out(f"--- pagina cu 'calificativ': {link} ---")
            ctx_all(dh, "calificativ", radius=300, max_hits=5)
            out("  -- ancore profil/magazin/vanzator --")
            seller_sel = None
            for a in ds.select('a[href*="/magazin"], a[href*="profil"], a[href*="vanzator"]')[:8]:
                par = a.parent
                out(f"    href={a.get('href')} text={a.get_text(' ', strip=True)[:50]!r} "
                    f"parent=<{getattr(par,'name','?')} class={par.get('class') if par else None}>")
                if seller_sel is None:
                    seller_sel = f"a[href*='{'/magazin' if '/magazin' in (a.get('href') or '') else 'profil'}']"
            out("  -- contexte etichete vanzator/data --")
            for lbl in ["Vandut de", "Vânzător", "vanzator", "Adaugat", "Publicat", "Listat", "Valabil"]:
                ctx_all(dh, lbl, radius=300, max_hits=1)
            out("  -- JSON-LD (seller/offers/date) --")
            for scl in ds.find_all("script", type="application/ld+json")[:3]:
                try:
                    j = json.loads(scl.string or "{}")
                except Exception:
                    continue
                for pth, val in find_paths(j, ["seller", "offer", "date", "valid", "author"], "ld"):
                    out(f"    {pth}: {str(val)[:200] if isinstance(val,(str,int,float)) else jdump(val,300)}")
            verdict("V3", "OK", f"seller_selector={seller_sel}; calificativ prezent public; vezi contexte pentru numar")
        else:
            out("NICIUNA dintre cele 3 pagini nu contine 'calificativ'")
            if last_soup is not None:
                out("  -- ancore profil/magazin de pe ULTIMA pagina --")
                for a in last_soup.select('a[href*="/magazin"], a[href*="profil"], a[href*="vanzator"]')[:10]:
                    out(f"    href={a.get('href')} text={a.get_text(' ', strip=True)[:50]!r}")
            verdict("V3", "NU", "calificativ negasit pe primele 3 anunturi (posibil layout magazin diferit)")
except Exception as e:
    out("V3 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("V3", "FAIL", f"eroare V3: {str(e)[:120]}")


# ╔════════════════════════ V4 ════════════════════════╗
try:
    banner("V4", "Publi24: nume vanzator + data exacta (2 detalii)")
    from app.services.radar.publi24_scraper import _build_url as p24_build, _request as p24_req

    known = "https://www.publi24.ro/anunturi/electronice/telefoane-mobile/iphone/anunt/iphone-12-pro-max-impecabil/i4g022d5ge377093dd98eeddi07f0i79.html"
    REQ["n"] += 1
    dh1 = p24_req(known)
    page1_url = known
    if not dh1:
        out("anuntul RP-DIAG indisponibil -> caut primul ne-promovat")
        surl = p24_build("iphone 12 pro", None, None, None, None, None, 1)
        REQ["n"] += 1
        sh = p24_req(surl)
        if sh:
            ss = BeautifulSoup(sh, "html.parser")
            for c in ss.select("div.article-item"):
                cls = " ".join(c.get("class", []))
                if c.select_one(".art-promoted") or "b2b" in cls:
                    continue
                lt = c.select_one("h2.article-title a[href]") or c.find("a", href=True)
                if lt and lt.get("href"):
                    page1_url = lt["href"]
                    if page1_url.startswith("/"):
                        page1_url = "https://www.publi24.ro" + page1_url
                    break
            time.sleep(4)
            REQ["n"] += 1
            dh1 = p24_req(page1_url)
    out("pagina 1:", page1_url)
    if not dh1:
        verdict("V4", "FAIL", "fara raspuns la detaliul Publi24 (pagina 1)")
    else:
        ds = BeautifulSoup(dh1, "html.parser")
        out("--- contexte vanzator ---")
        for lbl in ["Membru", "Contact", "Persoana fizica", "Persoană fizică", "Firma", "Detalii vanzator", "Nume"]:
            ctx_all(dh1, lbl, radius=300, max_hits=1)
        out("--- itemprop taguri ---")
        for ip in ds.find_all(attrs={"itemprop": True})[:25]:
            out(f"  <{ip.name} itemprop={ip.get('itemprop')!r}> = {ip.get_text(' ', strip=True)[:120]}")
        out("--- JSON-LD ---")
        for scl in ds.find_all("script", type="application/ld+json")[:3]:
            try:
                j = json.loads(scl.string or "{}")
            except Exception:
                out("  <ld+json neparsabil>")
                continue
            out("  " + jdump(j, 1500).replace("\n", "\n  "))
        out("--- element 'Valabil din' (selector + format) ---")
        vnode = ds.find(string=re.compile("Valabil din", re.I))
        valabil_text = None
        if vnode is not None:
            par = vnode.parent
            valabil_text = " ".join(vnode.split())
            out(f"  <{getattr(par,'name','?')} class={par.get('class') if par else None}> text={par.get_text(' ', strip=True)[:120]!r}")
        else:
            out("  'Valabil din' ABSENT")
        out("--- variabile JS inline cu posibil nume vanzator ---")
        seller_var = None
        for scl in ds.find_all("script"):
            t = scl.string or ""
            if not t:
                continue
            for key in ["sellerName", "userName", "owner", "contact"]:
                for m in re.finditer(re.escape(key), t):
                    p = m.start()
                    seg = re.sub(r"\s+", " ", t[max(0, p - 20):p + 150])
                    out(f"    [{key}] …{seg}…")
                    seller_var = seller_var or key
                    break  # o potrivire per cheie per script

        # pagina 2 — dezambiguizare format data (card vs 'Valabil din')
        out("--- pagina 2: dezambiguizare format data ---")
        surl2 = p24_build("iphone 12 pro", None, None, None, None, None, 1)
        REQ["n"] += 1
        sh2 = p24_req(surl2)
        card_date = None
        page2_url = None
        if sh2:
            ss2 = BeautifulSoup(sh2, "html.parser")
            best_day = -1
            for c in ss2.select("div.article-item"):
                cls = " ".join(c.get("class", []))
                if c.select_one(".art-promoted") or "b2b" in cls:
                    continue
                de = c.select_one("p.article-date span") or c.select_one(".article-date")
                lt = c.select_one("h2.article-title a[href]") or c.find("a", href=True)
                if not (de and lt and lt.get("href")):
                    continue
                dtext = de.get_text(" ", strip=True)
                low = dtext.lower()
                if "azi" in low or "ieri" in low:
                    continue
                md = re.search(r"(\d{1,2})", dtext)
                day = int(md.group(1)) if md else 0
                if day > best_day:
                    best_day = day
                    card_date = dtext
                    page2_url = lt["href"]
                    if page2_url.startswith("/"):
                        page2_url = "https://www.publi24.ro" + page2_url
            out("card ales (data mai veche):", card_date, "| url:", page2_url)
            if page2_url:
                time.sleep(4)
                REQ["n"] += 1
                dh2 = p24_req(page2_url)
                if dh2:
                    ds2 = BeautifulSoup(dh2, "html.parser")
                    v2 = ds2.find(string=re.compile("Valabil din", re.I))
                    out("  card_date:", card_date)
                    out("  detaliu 'Valabil din':", (" ".join(v2.split()) if v2 else "ABSENT"))
        verdict(
            "V4", "OK",
            f"seller nume via JS var={seller_var or 'indisponibil public'}; 'Valabil din' selector gasit={vnode is not None}; "
            f"comparatie card vs detaliu pentru format={card_date}",
        )
except Exception as e:
    out("V4 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("V4", "FAIL", f"eroare V4: {str(e)[:120]}")


# ╔════════════════════════ V5 ════════════════════════╗
try:
    banner("V5", "Facebook (conditionat de sesiune)")
    from app.services.radar.facebook_scraper import is_facebook_session_valid

    cand = []
    for pat in [
        os.path.join(BACKEND, "data", "facebook_session_*.json"),
        os.path.join(BACKEND, "facebook_storage_state.json"),
        os.path.join(REPO_ROOT, "data", "facebook_session_*.json"),
        os.path.join(REPO_ROOT, "facebook_storage_state.json"),
    ]:
        cand += glob.glob(pat)
    out("candidate (basenames):", [os.path.basename(p) for p in cand])
    valid = [p for p in cand if is_facebook_session_valid(p)]
    out("nr sesiuni valide:", len(valid))
    if not valid:
        verdict("V5", "SKIP", "sesiune inactiva")
    else:
        verdict(
            "V5", "FAIL",
            "sesiune valida exista dar scraperul marketplace e curl_cffi-only; seller trust (rating/'S-a inscris'/urmaritori) cere vizita profil via Playwright (>30 linii glue nou) -> nu fortez",
        )
except Exception as e:
    out("V5 EXCEPTIE:", "".join(traceback.format_exc())[:1200])
    verdict("V5", "FAIL", f"eroare V5: {str(e)[:120]}")


# ╔════════════════════════ RAPORT FINAL ════════════════════════╗
banner("REZUMAT", "Tabel de verdicte")
out(f"requesturi HTTP folosite (aprox): {REQ['n']}")
out("| Pas | Verdict | Concluzie intr-o linie |")
out("|-----|---------|------------------------|")
order = {f"V{i}": i for i in range(6)}
for step, status, concl in sorted(_VERDICTS, key=lambda x: order.get(x[0], 99)):
    out(f"| {step:<3} | {status:<7} | {concl} |")

out("")
out("--- git status --porcelain (READ-ONLY) ---")
try:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=30)
    st = ((r.stdout or "") + (r.stderr or "")).rstrip()
    out(st if st else "<curat>")
except Exception as e:
    out(f"<git error: {e}>")

out("")
out("[RP-DIAG-2 terminat]")
_OUT_F.close()
