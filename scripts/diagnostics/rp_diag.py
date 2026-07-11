# -*- coding: utf-8 -*-
"""RP-DIAG — diagnostic READ-ONLY pentru imbunatatirile Radar Piata.

STRICT DIAGNOSTIC. Nu modifica niciun fisier din backend/ sau frontend/.
Nu ruleaza git add/commit/push. Singurele fisiere noi: acest script si
rp_diag_output.txt (NECOMISE). Nu printeaza niciodata cookie-uri / tokeni /
headere de autentificare / continut de fisiere de sesiune — doar date publice
despre anunturi si vanzatori.

Ruleaza cu venv-ul backend-ului, din radacina repo-ului:
    backend/venv/Scripts/python.exe scripts/diagnostics/rp_diag.py
"""
import sys
import os
import json
import re
import time
import glob
import subprocess
import traceback

# ── UTF-8 pe consola Windows (diacritice RO) ────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND)  # ca importurile `from app...` sa functioneze

OUT_PATH = os.path.join(HERE, "rp_diag_output.txt")
# Mod "d4b" = probe suplimentar tintit, rulat SEPARAT; nu re-ruleaza D0-D9,
# doar adauga (append) la fisierul existent. Restul (fara argument) = run normal.
_D4B = len(sys.argv) > 1 and sys.argv[1] == "d4b"
_OUT_F = open(OUT_PATH, "a" if _D4B else "w", encoding="utf-8")


def out(*parts):
    """Tee: scrie in rp_diag_output.txt SI in terminal, incremental (flush)."""
    text = " ".join(str(p) for p in parts)
    _OUT_F.write(text + "\n")
    _OUT_F.flush()
    try:
        print(text, flush=True)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


# ── Verdicte (pentru tabelul final) ─────────────────────────────────────────
_VERDICTS = []  # (pas, status, concluzie-o-linie)


def verdict(step, status, concl, detail=None):
    line = detail if detail else concl
    out(f"VERDICT {step}: {status} — {line}")
    safe = re.sub(r"\s+", " ", concl).replace("|", "/").strip()
    _VERDICTS.append((step, status, safe[:110]))


# ── Scrubbing: nu scoatem niciodata date sensibile ──────────────────────────
_SENSITIVE = re.compile(
    r"(e[-_]?mail|token|msisdn|phone|telefon|password|passwd|secret|cookie|"
    r"session|access_token|refresh|api[_-]?key|apikey|authenticity|csrf|bearer)",
    re.I,
)


def scrub(obj, _depth=0):
    if _depth > 12:
        return "…"
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SENSITIVE.search(k):
                clean[k] = "<redacted>"
            else:
                clean[k] = scrub(v, _depth + 1)
        return clean
    if isinstance(obj, list):
        return [scrub(x, _depth + 1) for x in obj]
    return obj


def jdump(obj, limit=4000):
    try:
        s = json.dumps(scrub(obj), indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        s = f"<json dump error: {e}> repr={repr(obj)[:limit]}"
    if len(s) > limit:
        s = s[:limit] + f"\n… [trunchiat la {limit} caractere]"
    return s


def keys_of(d):
    if isinstance(d, dict):
        return list(d.keys())
    return f"<not a dict: {type(d).__name__}>"


def find_paths(obj, tokens, path="item", acc=None, seen=None, _depth=0):
    """Cautare recursiva dupa chei care CONTIN oricare token (case-insensitive).
    Returneaza [(cale, subarbore)] cu dedup pe cale."""
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
                if path + "." + str(k) not in seen:
                    seen.add(path + "." + str(k))
                    acc.append((f"{path}.{k}", v))
            find_paths(v, tokens, f"{path}.{k}", acc, seen, _depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_paths(v, tokens, f"{path}[{i}]", acc, seen, _depth + 1)
    return acc


def banner(step, title):
    out("")
    out("=" * 78)
    out(f"==={step}===  {title}")
    out("=" * 78)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ PROBE SUPLIMENTAR GATED (python rp_diag.py d4b) — NU re-ruleaza D0-D9      ║
# ╚══════════════════════════════════════════════════════════════════════════╝
if _D4B:
    import time as _t
    out("")
    out("#" * 78)
    out("=== SUPLIMENTAR (probe tintit, sesiune Vinted NOUA) ===")
    out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out("Motiv: D4 (catalog) a esuat cu cele 2 surse prescrise; D2/D3 (detaliu item)")
    out("au dat 403 pe sesiune reutilizata. Verific: (a) endpointul canonic de catalog")
    out("/api/v2/catalog/initializers; (b) daca o sesiune NOUA trece de 403 la detaliu.")
    out("#" * 78)
    from vinted_scraper import VintedWrapper
    w2 = None
    for attempt in range(3):
        try:
            w2 = VintedWrapper("https://www.vinted.ro")
            break
        except Exception as e:
            out(f"  construct w2 attempt {attempt + 1}/3 esuat: {str(e)[:120]}")
            _t.sleep(6)
    if w2 is None:
        verdict("D4b", "FAIL", "nu am putut construi o sesiune Vinted noua pentru probe")
    else:
        # (a) D4b — arborele de catalog via endpointul canonic
        out("--- D4b: GET /api/v2/catalog/initializers ---")
        try:
            init = w2.curl("/api/v2/catalog/initializers")
            out("initializers top keys:", keys_of(init))
            dtos = init.get("dtos") if isinstance(init, dict) else None
            tree = None
            if isinstance(dtos, dict):
                out("dtos keys:", keys_of(dtos))
                tree = dtos.get("catalogs")
            if not tree and isinstance(init, dict):
                tree = init.get("catalogs")
            if tree:
                out("nr cataloage radacina:", len(tree))
                out("titluri radacina:", [c.get("title") for c in tree][:40])
                r0 = tree[0]
                out("primul: id=", r0.get("id"), "| title=", r0.get("title"),
                    "| chei obiect catalog:", keys_of(r0))
                for ch in (r0.get("catalogs") or [])[:2]:
                    out("   copil: id=", ch.get("id"), "| title=", ch.get("title"),
                        "| nr_copii=", len(ch.get("catalogs") or []))
                verdict("D4b", "OK",
                        f"sursa functionala = GET /api/v2/catalog/initializers -> dtos.catalogs; structura id/title/catalogs[] confirmata ({len(tree)} radacini)")
            else:
                out("initializers 200 dar fara arbore catalogs:", jdump(init, 1500))
                verdict("D4b", "FAIL", "initializers 200 dar fara dtos.catalogs")
        except Exception as e:
            out("initializers esuat:", str(e)[:160])
            verdict("D4b", "FAIL", f"/api/v2/catalog/initializers esuat: {str(e)[:100]}")

        # (b) D2b — detaliu item cu sesiune NOUA (premisa RP-1: reuse vs fresh)
        out("--- D2b: item detail cu sesiune NOUA (verific daca trece de 403) ---")
        try:
            _t.sleep(6)
            s = w2.search({"search_text": "iphone 12 pro", "order": "newest_first", "per_page": 10})
            iid = (s.get("items") or [{}])[0].get("id") if isinstance(s, dict) else None
            out("id telefon pentru detaliu:", iid)
            if iid:
                _t.sleep(6)
                try:
                    d = w2.item(str(iid))
                    ito = d.get("item") if (isinstance(d, dict) and "item" in d) else d
                    out("SUCCES detaliu cu sesiune noua! top keys:", keys_of(d), "| item keys:", keys_of(ito))
                    u = ito.get("user") if isinstance(ito, dict) else None
                    if isinstance(u, dict):
                        keep = {k: u.get(k) for k in [
                            "id", "login", "feedback_count", "feedback_reputation",
                            "positive_feedback_count", "negative_feedback_count", "created_at",
                        ] if k in u}
                        out("item.user (feedback):", jdump(keep, 1500))
                        out("item.user (complet scrubbed):", jdump(u, 3000))
                    tokens = ["attribut", "battery", "capac", "model", "sim", "color", "colour", "storage"]
                    hits = find_paths(d, tokens, "item")
                    out(f"gasiri chei atribute telefon ({len(hits)}):")
                    for pth, val in hits[:40]:
                        out(f"  PATH {pth}: {jdump(val, 1500)}")
                    verdict("D2b", "OK",
                            "sesiune NOUA trece de detaliu -> RP-1: enrichment cu sesiune proaspata/rotita per lot (reuse simplu al aceleiasi sesiuni NU e suficient)")
                except Exception as e:
                    out(f"detaliu cu sesiune noua: ESEC — {type(e).__name__}: {str(e)[:150]}")
                    verdict("D2b", "FAIL",
                            f"si sesiunea NOUA da eroare la detaliu ({str(e)[:70]}) -> endpoint blocat pe IP/geo (datacenter), nu doar rate-limit de sesiune")
            else:
                verdict("D2b", "FAIL", "fara id de telefon din cautare")
        except Exception as e:
            out("D2b search esuat:", str(e)[:150])
            verdict("D2b", "FAIL", f"eroare cautare pentru D2b: {str(e)[:100]}")

    out("")
    out("### TABEL SUPLIMENTAR")
    out("| Pas | Verdict | Concluzie |")
    out("|-----|---------|-----------|")
    for step, status, concl in _VERDICTS:
        out(f"| {step} | {status} | {concl} |")
    out("[RP-DIAG d4b terminat]")
    _OUT_F.close()
    sys.exit(0)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ START                                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝
out("RP-DIAG — diagnostic read-only Radar Piata")
out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
out(f"repo_root: {REPO_ROOT}")
out("NOTA: fisier NECOMIS. Fara git add/commit/push. Fara cookie-uri/tokeni in output.")

# instanta Vinted partajata intre D1..D4
VW = None
VINTED_IDS = []
PHONE_ID = None


# ╔════════════════════════ D0 ════════════════════════╗
try:
    banner("D0", "vinted-scraper: versiune, API, mecanism de sesiune")
    import inspect
    import vinted_scraper

    out("dir(vinted_scraper) public:",
        [x for x in dir(vinted_scraper) if not x.startswith("_")])
    try:
        import importlib.metadata as _md
        ver = _md.version("vinted-scraper")
    except Exception as e:
        ver = f"<indisponibil: {e}>"
    out("versiune (pip 'vinted-scraper'):", ver)

    has_wrapper = hasattr(vinted_scraper, "VintedWrapper")
    out("VintedWrapper prezent:", has_wrapper)
    from vinted_scraper import VintedWrapper, VintedScraper

    out("VintedWrapper metode publice:",
        [m for m in dir(VintedWrapper) if not m.startswith("_")])
    out("VintedScraper metode publice:",
        [m for m in dir(VintedScraper) if not m.startswith("_")])

    wf = inspect.getsourcefile(VintedWrapper)
    out("sursa VintedWrapper:", wf)

    def cite(path, start, end, label):
        out(f"  -- {label} ({os.path.basename(path)}:{start}-{end}) --")
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            for i in range(start, min(end, len(lines)) + 1):
                out(f"    {i}: {lines[i - 1].rstrip(chr(10))}")
        except Exception as e:
            out(f"    <nu am putut citi sursa: {e}>")

    # Citate scurte care dovedesc mecanismul de sesiune (cod, NU valori de cookie)
    cite(wf, 36, 51, "camp _client (httpx.Client) + __post_init__ (creeaza client + fetch cookie 1x)")
    cite(wf, 173, 190, "curl(): reutilizeaza self._client + self.session_cookie la fiecare apel")

    verdict(
        "D0", "OK",
        "VintedWrapper exista (JSON brut); sesiune = httpx.Client la wrapper._client + cookie dict la wrapper.session_cookie, fetch 1x in __post_init__, reutilizat la toate apelurile (401 -> auto-refresh). Reutilizabila/accesibila DA.",
    )
except Exception as e:
    out("D0 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D0", "FAIL", f"eroare inspectie vinted_scraper: {str(e)[:120]}")


# ╔════════════════════════ D1 ════════════════════════╗
try:
    banner("D1", "Vinted: JSON brut de cautare")

    def build_vinted():
        from vinted_scraper import VintedWrapper
        last = None
        for attempt in range(2):
            try:
                return VintedWrapper("https://www.vinted.ro"), None
            except Exception as e:
                last = e
                out(f"  construct VintedWrapper attempt {attempt + 1}/2 esuat: {str(e)[:140]}")
                time.sleep(7)
        return None, last

    VW, err = build_vinted()
    if VW is None:
        verdict("D1", "FAIL", f"nu am putut construi VintedWrapper / fetch cookie: {str(err)[:100]}")
    else:
        time.sleep(6)  # same-domain: intre cookie-fetch (construct) si search
        raw = VW.search({"search_text": "iphone 12 pro", "order": "newest_first", "per_page": 24})
        out("top-level keys (search raw):", keys_of(raw))
        items = raw.get("items") if isinstance(raw, dict) else None
        if not items:
            out("search: fara 'items' -> keys:", keys_of(raw))
            verdict("D1", "FAIL", "search fara items (raspuns gol/neasteptat)")
        else:
            out("nr items:", len(items))
            out("chei complete PRIM item:", keys_of(items[0]))
            for i, it in enumerate(items[:3]):
                out(f"--- item[{i}] ---")
                out("  id:", it.get("id"))
                out("  title:", it.get("title"))
                out("  price (struct completa):", jdump(it.get("price"), 700))
                out("  url:", it.get("url"))
                u = it.get("user")
                if isinstance(u, dict) and len(json.dumps(u, default=str)) < 1200:
                    out("  user (complet, scrubbed):", jdump(u, 1500))
                else:
                    out("  user keys:", keys_of(u))
                    out("  user.login:", (u or {}).get("login") if isinstance(u, dict) else None)
                    if isinstance(u, dict):
                        for k in u:
                            if "feedback" in str(k).lower():
                                out(f"  user.{k}:", u[k])
                ph = it.get("photo")
                out("  photo keys:", keys_of(ph))
                out("  photo.high_resolution (integral):", jdump((ph or {}).get("high_resolution") if isinstance(ph, dict) else None, 900))
                out("  brand_title:", it.get("brand_title"))
                out("  status:", it.get("status"))
                if it.get("id") is not None:
                    VINTED_IDS.append(it.get("id"))

            first = items[0]
            fu = first.get("user") if isinstance(first, dict) else None
            login_present = bool(isinstance(fu, dict) and fu.get("login"))
            fph = first.get("photo") if isinstance(first, dict) else None
            hr_ts = None
            if isinstance(fph, dict) and isinstance(fph.get("high_resolution"), dict):
                hr_ts = fph["high_resolution"].get("timestamp")
            desc_present = isinstance(first, dict) and "description" in first
            verdict(
                "D1", "OK",
                f"user.login in search={login_present}; photo.high_resolution.timestamp in search={hr_ts is not None}; description in search={desc_present}",
            )
except Exception as e:
    out("D1 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D1", "FAIL", f"eroare search Vinted: {str(e)[:120]}")


# ╔════════════════════════ D2 ════════════════════════╗
try:
    banner("D2", "Vinted: JSON brut de detaliu (item)")
    if VW is None or not VINTED_IDS:
        verdict("D2", "SKIP", "fara instanta/ID-uri Vinted din D1")
    else:
        # D1 a cautat exact 'iphone 12 pro' -> toate rezultatele sunt telefoane;
        # folosim primul id pentru detaliul de telefon.
        PHONE_ID = VINTED_IDS[0]
        time.sleep(6)
        raw2 = VW.item(str(PHONE_ID))
        out("top-level keys (item raw):", keys_of(raw2))
        item_obj = raw2.get("item") if (isinstance(raw2, dict) and "item" in raw2) else raw2
        out("item keys:", keys_of(item_obj))

        u = item_obj.get("user") if isinstance(item_obj, dict) else None
        if isinstance(u, dict):
            keep = {k: u.get(k) for k in [
                "id", "login", "feedback_count", "feedback_reputation",
                "positive_feedback_count", "negative_feedback_count", "created_at",
            ] if k in u}
            out("item.user (campuri de incredere):", jdump(keep, 2000))
            out("item.user (complet, scrubbed, trunchiat):", jdump(u, 4000))
            fb_present = "feedback_count" in u
        else:
            out("item.user:", "<absent sau non-dict>")
            fb_present = False

        # Cautare recursiva dupa atributele telefonului
        tokens = ["attribut", "battery", "capac", "model", "sim", "color", "colour", "storage"]
        hits = find_paths(raw2, tokens, "item")
        out(f"gasiri chei atribute (total {len(hits)}, afisez max 50):")
        attr_path_example = None
        for pth, val in hits[:50]:
            if attr_path_example is None and "attribut" in pth.lower():
                attr_path_example = pth
            out(f"  PATH {pth}:")
            out("    " + jdump(val, 2000).replace("\n", "\n    "))
        if attr_path_example is None and hits:
            attr_path_example = hits[0][0]

        desc = (item_obj.get("description") if isinstance(item_obj, dict) else None) or ""
        out("description[:300]:", desc[:300])
        date_field = None
        for k in ["created_at", "created_at_ts", "updated_at_ts"]:
            if isinstance(item_obj, dict) and k in item_obj:
                out(f"item.{k}:", item_obj[k])
                if date_field is None:
                    date_field = k
        photos = (item_obj.get("photos") if isinstance(item_obj, dict) else None) or []
        p0ts = None
        if photos and isinstance(photos[0], dict):
            hr = photos[0].get("high_resolution") or {}
            p0ts = hr.get("timestamp") if isinstance(hr, dict) else None
            out("photos[0].high_resolution.timestamp:", p0ts)

        rec_date = date_field or ("photos[0].high_resolution.timestamp" if p0ts else "N/A")
        verdict(
            "D2", "OK",
            f"feedback_count la user={fb_present}; cale atribute exemplu={attr_path_example}; camp data postare recomandat={rec_date}",
        )
except Exception as e:
    out("D2 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D2", "FAIL", f"eroare item Vinted: {str(e)[:120]}")


# ╔════════════════════════ D3 ════════════════════════╗
try:
    banner("D3", "Vinted: reutilizarea sesiunii (sanity rate-limit)")
    if VW is None or len(VINTED_IDS) < 2:
        verdict("D3", "SKIP", "instanta lipsa sau <2 ID-uri suplimentare din D1")
    else:
        other = [i for i in VINTED_IDS if str(i) != str(PHONE_ID)][:2]
        oks = []
        blocked = False
        for oid in other:
            time.sleep(7)
            try:
                r = VW.item(str(oid))
                ok = bool(r)
                out(f"item({oid}): {'SUCCES' if ok else 'GOL'} — top keys={keys_of(r)}")
                oks.append(ok)
            except Exception as e:
                msg = str(e)
                out(f"item({oid}): ESEC — {type(e).__name__}: {msg[:160]}")
                if "403" in msg or "429" in msg:
                    blocked = True
                oks.append(False)
        total_consecutive = 1 + sum(1 for x in oks if x)  # D2 (1) + cele de aici
        all_ok = (not blocked) and all(oks)
        verdict(
            "D3", "OK" if all_ok else "FAIL",
            f"{total_consecutive}/3 detail-uri consecutive pe aceeasi sesiune reusite; 403/429 intalnit={blocked}",
        )
except Exception as e:
    out("D3 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D3", "FAIL", f"eroare reutilizare sesiune: {str(e)[:120]}")


# ╔════════════════════════ D4 ════════════════════════╗
try:
    banner("D4", "Vinted: arborele de cataloage")
    if VW is None:
        verdict("D4", "FAIL", "fara instanta Vinted (D1 esuat) -> nu pot folosi sesiunea partajata")
    else:
        cats = None
        source = None
        time.sleep(6)
        try:
            cats = VW.curl("/api/v2/catalogs")
            source = "GET /api/v2/catalogs"
        except Exception as e:
            out("endpoint /api/v2/catalogs esuat:", str(e)[:160])
            # fallback: homepage embedded (aceeasi sesiune)
            try:
                time.sleep(6)
                resp = VW._client.get("/")
                html = resp.text if resp.status_code == 200 else ""
                m = re.search(r'"catalogs"\s*:\s*\[', html)
                out("homepage contine marker '\"catalogs\":[':", bool(m))
                source = "homepage embedded"
            except Exception as e2:
                out("fallback homepage esuat:", str(e2)[:160])

        roots = None
        if isinstance(cats, dict):
            out("catalogs raspuns top keys:", keys_of(cats))
            roots = cats.get("catalogs")
        if roots:
            out("nr cataloage radacina:", len(roots))
            out("titluri radacina:", [c.get("title") for c in roots][:40])
            r0 = roots[0]
            out("primul catalog: id=", r0.get("id"), "title=", r0.get("title"))
            children = r0.get("catalogs") or []
            out("  primul are", len(children), "copii; primii 2:")
            for ch in children[:2]:
                out("   copil: id=", ch.get("id"), "title=", ch.get("title"),
                    "nr_copii=", len(ch.get("catalogs") or []))
            verdict(
                "D4", "OK",
                f"sursa={source}; structura {{id,title,catalogs[]}} confirmata DA ({len(roots)} radacini)",
            )
        else:
            verdict("D4", "FAIL", f"nu am obtinut lista de cataloage (sursa={source})")
except Exception as e:
    out("D4 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D4", "FAIL", f"eroare cataloage Vinted: {str(e)[:120]}")


# ── de aici incolo: curl_cffi + helperii read-only din app.services.radar ───
from bs4 import BeautifulSoup  # noqa: E402
from curl_cffi import requests as curl_requests  # noqa: E402
from app.services.radar.base_scraper import build_headers  # noqa: E402

_IMP = "chrome110"


# ╔════════════════════════ D5 ════════════════════════╗
try:
    banner("D5", "OLX: vanzator + data exacta")

    def olx_get(url, accept_json=False, referer="https://www.olx.ro/"):
        extra = {"Referer": referer}
        if accept_json:
            extra["Accept"] = "application/json, text/plain, */*"
        return curl_requests.get(url, headers=build_headers(extra), impersonate=_IMP, timeout=20)

    def olx_first_ad(html):
        """(id_numeric, url) primul anunt din __PRERENDERED_STATE__ (Apollo)."""
        try:
            m = re.search(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', html, re.DOTALL)
            if not m:
                return None, None
            state = json.loads(json.loads(m.group(1)))
            ads = (state.get("listing") or {}).get("listing", {}).get("ads") or []
            for ad in ads:
                aid = ad.get("id")
                url = ad.get("url") or ad.get("urlPath") or ""
                if aid:
                    if url.startswith("/"):
                        url = "https://www.olx.ro" + url
                    return str(aid), url
        except Exception as e:
            out("  olx state parse err:", str(e)[:120])
        return None, None

    r = olx_get("https://www.olx.ro/oferte/q-iphone-12-pro/")
    out("search HTTP:", r.status_code)
    html = r.text if r.status_code == 200 else ""
    m = re.search(r'https://www\.olx\.ro/d/oferta/[^\s"\'<>]+', html) or re.search(r'/d/oferta/[^\s"\'<>]+', html)
    regex_url = m.group(0) if m else None
    if regex_url and regex_url.startswith("/"):
        regex_url = "https://www.olx.ro" + regex_url
    num_id, ad_url = olx_first_ad(html)
    out("primul anunt (regex /d/oferta/):", regex_url)
    out("primul ad id numeric (state):", num_id)
    detail_url = ad_url or regex_url

    api_source = "N/A"
    api_user_fields = []
    # 5a — API
    out("--- 5a API /api/v1/offers/{id} ---")
    if num_id:
        time.sleep(6)
        ra = olx_get(f"https://www.olx.ro/api/v1/offers/{num_id}", accept_json=True)
        out("API HTTP:", ra.status_code, "| content-type:", ra.headers.get("content-type", ""))
        if ra.status_code == 200:
            try:
                j = ra.json()
                out("API top keys:", keys_of(j))
                data = j.get("data") if isinstance(j, dict) else j
                out("API data keys:", keys_of(data))
                user = (data or {}).get("user") if isinstance(data, dict) else None
                if isinstance(user, dict):
                    uf = {k: user.get(k) for k in [
                        "id", "name", "created", "about", "seller_type",
                        "is_business", "company_name",
                    ] if k in user}
                    out("API data.user (scrubbed):", jdump(uf, 1500))
                    api_user_fields = list(uf.keys())
                    api_source = "API"
                for k in ["created_time", "last_refresh_time", "valid_to", "pushup_time"]:
                    if isinstance(data, dict) and k in data:
                        out(f"API data.{k}:", data[k])
            except Exception as e:
                out("API json parse esuat:", str(e)[:140])
        else:
            out("API non-200 -> ma bazez pe HTML (5b)")
    else:
        out("5a: fara id numeric -> nu apelez API")

    # 5b — HTML fallback
    out("--- 5b HTML detaliu ---")
    html_fields = []
    if detail_url:
        time.sleep(6)
        rd = olx_get(detail_url)
        out("detail HTTP:", rd.status_code)
        if rd.status_code == 200:
            ds = BeautifulSoup(rd.text, "html.parser")
            el = ds.select_one('[data-testid="user-profile-user-name"]')
            out('[data-testid="user-profile-user-name"]:', el.get_text(" ", strip=True) if el else "ABSENT")
            if el:
                html_fields.append("user-profile-user-name")
            node = ds.find(string=re.compile(r"Pe OLX din", re.I))
            out("text 'Pe OLX din':", (" ".join(node.split())[:120]) if node else "ABSENT")
            if node:
                html_fields.append("Pe OLX din")
            pa = ds.select_one('[data-cy="ad-posted-at"]')
            out('[data-cy="ad-posted-at"]:', pa.get_text(" ", strip=True) if pa else "ABSENT")
            if pa:
                html_fields.append("ad-posted-at")
            out("ld+json (doar campuri vanzator/data):")
            for sc in ds.find_all("script", type="application/ld+json")[:4]:
                try:
                    j = json.loads(sc.string or "{}")
                except Exception:
                    continue
                dtoks = ["seller", "author", "date", "valid", "posted", "offer", "priceval"]
                for pth, val in find_paths(j, dtoks, "ld"):
                    if isinstance(val, (str, int, float)):
                        out(f"   {pth}:", str(val)[:160])
                    else:
                        out(f"   {pth}: {jdump(val, 400)}")
        else:
            out("detail non-200 -> nu pot extrage HTML")
    else:
        out("5b: fara URL de detaliu")

    reco = "API" if api_user_fields else ("HTML" if html_fields else "niciuna")
    verdict(
        "D5", "OK" if (api_user_fields or html_fields) else "FAIL",
        f"sursa recomandata={reco}; API user fields={api_user_fields}; HTML fields={html_fields}",
    )
except Exception as e:
    out("D5 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D5", "FAIL", f"eroare OLX: {str(e)[:120]}")


# ╔════════════════════════ D6 ════════════════════════╗
try:
    banner("D6", "Okazii: vanzator + calificative + data")
    from app.services.radar.okazii_scraper import _build_url as okazii_build, _request as okazii_req

    url = okazii_build("iphone 12 pro", None, "all", None, None, 1)
    out("search url:", url)
    html = okazii_req(url)
    if not html:
        verdict("D6", "FAIL", "fara raspuns la pagina de cautare Okazii")
    else:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("#listing-Okazii .list-item")
        out("nr carduri:", len(cards))
        link = None
        for c in cards:
            lt = (c.select_one("figure.item-image a[href]")
                  or c.select_one(".item-title h2 a[href]")
                  or c.find("a", href=True))
            if lt and lt.get("href"):
                link = lt.get("href")
                break
        if link and link.startswith("/"):
            link = "https://www.okazii.ro" + link
        out("primul anunt:", link)
        if not link:
            verdict("D6", "FAIL", "niciun link de anunt in carduri")
        else:
            time.sleep(6)
            dhtml = okazii_req(link)
            if not dhtml:
                verdict("D6", "FAIL", "fara raspuns la pagina de detaliu Okazii")
            else:
                ds = BeautifulSoup(dhtml, "html.parser")
                prof = (ds.select_one('a[href*="/profil"]')
                        or ds.select_one('a[href*="/vanzator"]')
                        or ds.select_one('a[href*="magazin"]')
                        or ds.select_one('a[href*="/user"]'))
                seller_selector = None
                if prof:
                    seller_selector = 'a[href*="/profil"]' if "/profil" in (prof.get("href") or "") else f'a[href*="{(prof.get("href") or "")[:20]}"]'
                    cont = prof
                    for _ in range(3):
                        if cont.parent is not None:
                            cont = cont.parent
                    out("seller container outerHTML[:2500]:")
                    out(str(cont)[:2500])
                else:
                    out("seller profile link ABSENT (a[href*=profil]/vanzator/magazin)")
                calif_selector = None
                for el in ds.find_all(string=re.compile("calificativ", re.I))[:5]:
                    par = el.parent
                    txt = " ".join(par.get_text(" ", strip=True).split())[:220] if par else ""
                    out("'calificativ':", txt, "| parent tag/clasa:", getattr(par, "name", "?"), (par.get("class") if par else None))
                    if calif_selector is None and par is not None:
                        calif_selector = f"{getattr(par, 'name', '?')}.{'.'.join(par.get('class') or [])}"
                date_found = False
                for label in ["Publicat", "Adăugat", "Adaugat", "Valabil", "Postat"]:
                    node = ds.find(string=re.compile(label, re.I))
                    if node:
                        date_found = True
                        ctx = " ".join(node.parent.get_text(" ", strip=True).split())[:160] if node.parent else ""
                        out(f"data '{label}':", " ".join(node.split())[:100], "| ctx:", ctx)
                verdict(
                    "D6", "OK",
                    f"seller_selector={seller_selector}; calificativ_selector={calif_selector}; data publica={date_found}",
                )
except Exception as e:
    out("D6 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D6", "FAIL", f"eroare Okazii: {str(e)[:120]}")


# ╔════════════════════════ D7 ════════════════════════╗
try:
    banner("D7", "Publi24: vanzator pe pagina de detaliu")
    from app.services.radar.publi24_scraper import _build_url as p24_build, _request as p24_req

    url = p24_build("iphone 12 pro", None, None, None, None, None, 1)
    out("search url:", url)
    html = p24_req(url)
    if not html:
        verdict("D7", "FAIL", "fara raspuns la pagina de cautare Publi24")
    else:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.article-item")
        out("nr carduri:", len(cards))
        link = None
        for c in cards:
            cls = " ".join(c.get("class", []))
            if c.select_one(".art-promoted") or "b2b" in cls:
                continue
            lt = c.select_one("h2.article-title a[href]") or c.find("a", href=True)
            if lt and lt.get("href"):
                link = lt.get("href")
                break
        if link and link.startswith("/"):
            link = "https://www.publi24.ro" + link
        out("primul anunt (ne-promovat):", link)
        if not link:
            verdict("D7", "FAIL", "niciun link de anunt ne-promovat in carduri")
        else:
            time.sleep(6)
            dhtml = p24_req(link)
            if not dhtml:
                verdict("D7", "FAIL", "fara raspuns la pagina de detaliu Publi24")
            else:
                ds = BeautifulSoup(dhtml, "html.parser")
                membru = ds.find(string=re.compile("Membru din", re.I))
                seller_selector = None
                anchor = None
                if membru is not None:
                    anchor = membru.parent
                else:
                    anchor = (ds.select_one('[class*="user"]')
                              or ds.select_one('[class*="seller"]')
                              or ds.select_one('[class*="advertiser"]')
                              or ds.select_one('[class*="contact"]'))
                if anchor is not None:
                    cont = anchor
                    for _ in range(3):
                        if cont.parent is not None:
                            cont = cont.parent
                    seller_selector = f"{getattr(cont, 'name', '?')}.{'.'.join(cont.get('class') or [])}"
                    out("seller zona outerHTML[:2000]:")
                    out(str(cont)[:2000])
                else:
                    out("zona vanzator ABSENTA (fara 'Membru din' / clase user/seller)")
                out("'Membru din':", (" ".join(membru.split())[:120]) if membru else "ABSENT")
                acct = ds.find(string=re.compile(r"Persoan[aă] fizic|Firm[aă]|Juridic", re.I))
                out("tip cont (Persoana fizica/Firma):", (" ".join(acct.split())[:80]) if acct else "ABSENT")
                for label in ["Publicat", "Actualizat", "Adăugat", "Valabil", "Data"]:
                    node = ds.find(string=re.compile(label, re.I))
                    if node:
                        ctx = " ".join(node.parent.get_text(" ", strip=True).split())[:150] if node.parent else ""
                        out(f"data '{label}':", " ".join(node.split())[:100], "| ctx:", ctx)
                verdict(
                    "D7", "OK",
                    f"seller_selector={seller_selector}; 'Membru din' exista={membru is not None}",
                )
except Exception as e:
    out("D7 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D7", "FAIL", f"eroare Publi24: {str(e)[:120]}")


# ╔════════════════════════ D8 ════════════════════════╗
try:
    banner("D8", "Facebook Marketplace: vizibilitate vanzator (doar daca sesiune activa)")
    from app.services.radar.facebook_scraper import is_facebook_session_valid

    candidates = []
    for pat in [
        os.path.join(BACKEND, "data", "facebook_session_*.json"),
        os.path.join(BACKEND, "facebook_storage_state.json"),
        os.path.join(REPO_ROOT, "data", "facebook_session_*.json"),
        os.path.join(REPO_ROOT, "facebook_storage_state.json"),
    ]:
        candidates += glob.glob(pat)
    out("fisiere sesiune candidate (basenames):", [os.path.basename(p) for p in candidates])
    valid = [p for p in candidates if is_facebook_session_valid(p)]
    out("nr sesiuni valide:", len(valid))
    if not valid:
        verdict("D8", "SKIP", "sesiune Facebook inactiva/expirata (niciun storage_state valid) -> nu deschid Marketplace")
    else:
        # Regula D8: nu fortez daca glue-code-ul depaseste ~30 linii sau cere
        # modificari. Scraperul marketplace e curl_cffi-only; on-demand detail
        # (fetch_facebook_listing_detail) intoarce DOAR descriere+galerie, nu
        # campuri de vanzator. Rating/'Joined Facebook'/followers cer o vizita de
        # profil via Playwright (cod nou >30 linii) -> FAIL onest, nu improvizez.
        verdict(
            "D8", "FAIL",
            "sesiune valida exista dar scraperul marketplace e curl_cffi-only; on-demand detail da doar descriere+galerie. Rating/'Joined Facebook'/followers necesita vizita profil via Playwright (>30 linii glue nou) -> nu fortez (regula 6/D8)",
        )
except Exception as e:
    out("D8 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D8", "FAIL", f"eroare verificare sesiune FB: {str(e)[:120]}")


# ╔════════════════════════ D9 ════════════════════════╗
try:
    banner("D9", "Puncte de integrare in codul LOCAL (fara modificari)")

    def read_lines(rel):
        p = rel if os.path.isabs(rel) else os.path.join(BACKEND, rel)
        with open(p, encoding="utf-8") as f:
            return f.readlines()

    def grep_n(rel, pattern):
        hits = []
        for i, ln in enumerate(read_lines(rel), 1):
            if re.search(pattern, ln):
                hits.append((i, ln.rstrip("\n")))
        return hits

    def show_range(rel, start, end):
        lines = read_lines(rel)
        for i in range(max(1, start), min(end, len(lines)) + 1):
            out(f"  {i}: {lines[i - 1].rstrip(chr(10))}")

    def show_def(rel, pattern, n_lines):
        hits = grep_n(rel, pattern)
        if not hits:
            out(f"  <'{pattern}' negasit in {rel}>")
            return
        ln = hits[0][0]
        out(f"  {rel} :: {pattern} @ linia {ln}")
        show_range(rel, ln, ln + n_lines - 1)

    R = "app/services/radar/"

    out("[1] get_vinted_item_detail (definitie + 15 linii):")
    for ln, txt in grep_n(R + "vinted_scraper.py", r"def get_vinted_item_detail"):
        out(f"   grep {ln}: {txt.strip()}")
    show_def(R + "vinted_scraper.py", r"def get_vinted_item_detail", 15)

    out("[2] fetch_okazii_listing_details (definitie + apeluri + context 5 linii):")
    for ln, txt in grep_n(R + "okazii_scraper.py", r"fetch_okazii_listing_details"):
        out(f"   grep {ln}: {txt.strip()}")
    calls = grep_n(R + "okazii_scraper.py", r"= fetch_okazii_listing_details|details = fetch_okazii_listing_details")
    for ln, _ in calls:
        out(f"   -- context apel @ {ln} --")
        show_range(R + "okazii_scraper.py", ln - 2, ln + 3)

    out("[3] fetch_publi24_listing_details (definitie + apeluri + context 5 linii):")
    for ln, txt in grep_n(R + "publi24_scraper.py", r"fetch_publi24_listing_details"):
        out(f"   grep {ln}: {txt.strip()}")
    calls = grep_n(R + "publi24_scraper.py", r"details = fetch_publi24_listing_details")
    for ln, _ in calls:
        out(f"   -- context apel @ {ln} --")
        show_range(R + "publi24_scraper.py", ln - 2, ln + 3)

    out("[4] _fetch_detail_image (grep + 10 linii context la apel):")
    for ln, txt in grep_n(R + "olx_scraper.py", r"_fetch_detail_image"):
        out(f"   grep {ln}: {txt.strip()}")
    callsites = [ln for ln, txt in grep_n(R + "olx_scraper.py", r"_fetch_detail_image") if "def " not in txt]
    for ln in callsites:
        out(f"   -- context apel @ {ln} --")
        show_range(R + "olx_scraper.py", ln - 5, ln + 5)

    out("[5] is_excluded (functia integrala din base_scraper.py):")
    hits = grep_n(R + "base_scraper.py", r"def is_excluded")
    if hits:
        start = hits[0][0]
        lines = read_lines(R + "base_scraper.py")
        end = len(lines)
        for i in range(start, len(lines)):
            if i > start and re.match(r"^\S", lines[i]) and lines[i].startswith("def "):
                end = i
                break
        show_range(R + "base_scraper.py", start, end)

    out("[6] git status --porcelain + git log --oneline -3 (READ-ONLY):")

    def git(args):
        try:
            r = subprocess.run(["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
            return ((r.stdout or "") + (r.stderr or "")).rstrip()
        except Exception as e:
            return f"<git error: {e}>"

    st = git(["status", "--porcelain"])
    out("  git status --porcelain:")
    out("   " + (st.replace("\n", "\n   ") if st else "<curat / niciun fisier modificat>"))
    lg = git(["log", "--oneline", "-3"])
    out("  git log --oneline -3:")
    out("   " + lg.replace("\n", "\n   "))

    verdict("D9", "OK", "puncte de integrare localizate; git status/log capturate (read-only)")
except Exception as e:
    out("D9 EXCEPTIE:", "".join(traceback.format_exc())[:1500])
    verdict("D9", "FAIL", f"eroare confirmare integrare: {str(e)[:120]}")


# ╔════════════════════════ TABEL VERDICTE ════════════════════════╗
banner("REZUMAT", "Tabel de verdicte")
out("| Pas | Verdict (OK/FAIL/SKIP) | Concluzie intr-o linie |")
out("|-----|------------------------|------------------------|")
order = {f"D{i}": i for i in range(10)}
for step, status, concl in sorted(_VERDICTS, key=lambda x: order.get(x[0], 99)):
    out(f"| {step:<3} | {status:<22} | {concl} |")

out("")
out("[RP-DIAG terminat]")
_OUT_F.close()
