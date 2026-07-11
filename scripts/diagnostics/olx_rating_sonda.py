# -*- coding: utf-8 -*-
"""FlipRadar — SONDA rating vanzator OLX (diagnostic READ-ONLY, nu se comite).

Intrebarea: ratingul vanzatorului de pe olx.ro (stele + numar recenzii) este
obtenabil FARA autentificare? Si daca da — de unde exact?

Ce probeaza, per anunt (max 3):
  V1  pagina anuntului (HTML salvat local) + dump de context in jurul
      cuvintelor-cheie (rating/recenz/calificat/stele/review/recommend) —
      lectia din DIAG-2: nu ghicim containere, lasam HTML-ul sa vorbeasca.
  V2  window.__PRERENDERED_STATE__ — walk recursiv, printeaza orice cheie
      care contine termeni de rating + valoarea ei.
  V3  blocurile <script type="application/ld+json"> — cautam AggregateRating.
  V4  /api/v1/offers/{id} — dump COMPLET al cheilor din `data` + obiectul
      `data.user` integral (RP-DIAG a confirmat doar name/created; verificam
      ca n-am ratat nimic).
  V5  /api/v1/users/{user_id}/ — status + primele ~800 caractere.
  V6  pagina de profil a vanzatorului (/oferte/user/...) — HTML salvat +
      dump cuvinte-cheie + walk pe state-ul ei.
  V7  (o singura data) scan pe primele 3 bundle-uri JS ale paginii dupa
      URL-uri/siruri care contin review|rating|opinie|feedback — ca sa aflam
      numele endpointului real pe care il foloseste site-ul (patternul care
      a functionat la catalogul Vinted).

CUM SE RULEAZA (din radacina repo-ului, cu venv-ul backend activ):
  1. Completeaza LISTING_URLS mai jos cu 2-3 URL-uri de anunturi OLX.
     IMPORTANT: minim unul la care VEZI in browser ca vanzatorul ARE recenzii
     (stele + numar) — altfel absenta datelor nu dovedeste nimic.
  2. python scripts/diagnostics/olx_rating_sonda.py > scripts/diagnostics/olx_rating_sonda_output.txt 2>&1
  3. Lipeste fisierul de output integral in chat.

Fisiere generate (toate in scripts/diagnostics/, raman NEcomise):
  _olx_rating_L{i}.html  — HTML-ul fiecarui anunt
  _olx_rating_P{i}.html  — HTML-ul profilului de vanzator (daca e gasit)
"""
import json
import random
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests as curl_requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── COMPLETEAZA AICI (sau da URL-urile ca argumente in linia de comanda) ──────
LISTING_URLS = [
    "https://www.olx.ro/d/oferta/iphone-17-pro-max-97-baterie-amanet-sz-non-stop-IDkKMG0.html?search_reason=search%7Corganic",
    "https://www.olx.ro/d/oferta/iphone-14-pro-max-128gb-IDkKMGZ.html?search_reason=search%7Corganic"
]
# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).resolve().parent
IMPERSONATE = "chrome131"
TERMS = ("rating", "recenz", "calificat", "stele", "review", "recommend", "opinie", "feedback")
HDRS_HTML = {"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}
HDRS_API = {"Accept": "application/json, text/plain, */*", "Referer": "https://www.olx.ro/",
            "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}

_summary: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)


def pause() -> None:
    time.sleep(random.uniform(2.0, 4.0))


def get(url: str, headers: dict, label: str):
    """GET cu impersonate; returneaza response sau None (cu print de status)."""
    try:
        r = curl_requests.get(url, headers=headers, impersonate=IMPERSONATE, timeout=20)
        say(f"    [{label}] GET {url} -> HTTP {r.status_code} ({len(r.content)} bytes)")
        return r
    except Exception as exc:
        say(f"    [{label}] GET {url} -> EROARE: {exc}")
        return None


def kw_context_dump(text: str, label: str, max_hits_per_term: int = 4, radius: int = 200) -> int:
    """Printeaza contextul (±radius) in jurul fiecarui termen de rating. Returneaza nr. total de hituri."""
    total = 0
    low = text.lower()
    for term in TERMS:
        hits = 0
        start = 0
        while hits < max_hits_per_term:
            i = low.find(term, start)
            if i < 0:
                break
            ctx = text[max(0, i - radius): i + radius].replace("\n", " ")
            ctx = re.sub(r"\s+", " ", ctx)
            say(f'    [{label}] "{term}" @ {i}: …{ctx}…')
            hits += 1
            total += 1
            start = i + len(term)
    if total == 0:
        say(f"    [{label}] niciun termen de rating gasit in text.")
    return total


def extract_js_string(html: str, marker: str):
    """Extrage literalul string JS de dupa `marker =` (cu escape-uri), fara ghicit de regex lacom."""
    m = re.search(re.escape(marker) + r"\s*=\s*\"", html)
    if not m:
        return None
    i = m.end()  # primul caracter DUPA ghilimeaua de deschidere
    buf = []
    while i < len(html):
        c = html[i]
        if c == "\\":
            buf.append(html[i:i + 2]); i += 2; continue
        if c == '"':
            return '"' + "".join(buf) + '"'
        buf.append(c); i += 1
    return None


def load_prerendered_state(html: str):
    lit = extract_js_string(html, "window.__PRERENDERED_STATE__")
    if not lit:
        return None, "marker negasit"
    try:
        inner = json.loads(lit)          # literalul e un JSON string
        return json.loads(inner), "ok"   # …care contine JSON-ul real
    except Exception as exc:
        return None, f"parse esuat: {exc}"


def walk_for_terms(node, path: str, printed: list) -> None:
    """Walk recursiv: printeaza orice cheie care contine un termen de rating."""
    if len(printed) >= 120:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if any(t in str(k).lower() for t in TERMS):
                printed.append(p)
                say(f"    [state] {p} = {repr(v)[:300]}")
            walk_for_terms(v, p, printed)
    elif isinstance(node, list):
        for idx, v in enumerate(node[:25]):
            walk_for_terms(v, f"{path}[{idx}]", printed)


def find_offer_ids(html: str) -> list[str]:
    ids: list[str] = []
    for pat in (r'"ad_id"\s*:\s*(\d{6,})', r'"adId"\s*:\s*"?(\d{6,})', r'"id"\s*:\s*(\d{8,})'):
        for m in re.findall(pat, html):
            if m not in ids:
                ids.append(m)
                say(f"    [id] candidat offer id {m} (pattern: {pat})")
            if len(ids) >= 2:
                return ids
    return ids


def ldjson_dump(html: str) -> int:
    blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    hits = 0
    for b in blocks:
        if re.search(r"aggregateRating|AggregateRating|\"Review\"", b):
            hits += 1
            say(f"    [ld+json] bloc cu rating:\n{b.strip()[:1500]}")
    if hits == 0:
        say(f"    [ld+json] {len(blocks)} blocuri gasite, niciunul cu AggregateRating/Review.")
    return hits


def bundles_scan(html: str) -> int:
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    srcs = [s for s in srcs if s.startswith("http") and ("olx" in s or "statics" in s)][:3]
    say(f"    [bundles] scanez {len(srcs)} bundle-uri JS: {srcs}")
    pat = re.compile(r'[a-zA-Z0-9_\-./:{}?=]*(?:review|rating|opinie|feedback)[a-zA-Z0-9_\-./:{}?=]*', re.I)
    found: list[str] = []
    for s in srcs:
        pause()
        r = get(s, HDRS_HTML, "bundle")
        if not r or r.status_code != 200:
            continue
        for m in pat.findall(r.text[:3_000_000]):
            if len(m) > 8 and m not in found:
                found.append(m)
    for f in found[:40]:
        say(f"    [bundles] {f}")
    say(f"    [bundles] total siruri distincte: {len(found)} (afisate max 40)")
    return len(found)


def probe_listing(idx: int, url: str) -> None:
    say(f"\n{'=' * 78}\nL{idx}: {url}\n{'=' * 78}")
    r = get(url, HDRS_HTML, "V1")
    if not r or r.status_code != 200:
        _summary.append(f"L{idx}: FETCH ESUAT (V1) — restul sectiunilor sarite")
        return
    html = r.text
    (OUT_DIR / f"_olx_rating_L{idx}.html").write_text(html, encoding="utf-8")

    say("\n  V1 — cuvinte-cheie in HTML-ul anuntului:")
    v1 = kw_context_dump(html, "V1")

    say("\n  V2 — __PRERENDERED_STATE__:")
    state, verdict = load_prerendered_state(html)
    v2 = 0
    if state is None:
        say(f"    [state] {verdict}")
    else:
        printed: list = []
        walk_for_terms(state, "", printed)
        v2 = len(printed)
        if v2 == 0:
            say("    [state] parsat OK, dar nicio cheie cu termeni de rating.")

    say("\n  V3 — ld+json:")
    v3 = ldjson_dump(html)

    say("\n  V4 — /api/v1/offers/{id}:")
    user_id = None
    v4_keys = "—"
    for oid in find_offer_ids(html) or ["(niciun id gasit)"]:
        if not oid.isdigit():
            say("    [V4] nu am gasit un offer id numeric in pagina.")
            break
        pause()
        ro = get(f"https://www.olx.ro/api/v1/offers/{oid}", HDRS_API, "V4")
        if not ro or ro.status_code != 200:
            continue
        try:
            data = (ro.json() or {}).get("data") or {}
        except Exception as exc:
            say(f"    [V4] JSON invalid: {exc}"); continue
        v4_keys = ",".join(sorted(data.keys()))
        say(f"    [V4] chei in data: {v4_keys}")
        say(f"    [V4] data.user COMPLET:\n{json.dumps(data.get('user'), ensure_ascii=False, indent=2)[:2000]}")
        u = data.get("user") or {}
        user_id = u.get("id")
        break

    say("\n  V5 — /api/v1/users/{user_id}/:")
    v5 = "SKIP (fara user_id)"
    if user_id:
        pause()
        ru = get(f"https://www.olx.ro/api/v1/users/{user_id}/", HDRS_API, "V5")
        if ru is not None:
            v5 = f"HTTP {ru.status_code}"
            say(f"    [V5] body[:800]: {ru.text[:800]}")

    say("\n  V6 — profil vanzator:")
    v6 = "SKIP (link negasit)"
    mp = re.search(r'href="([^"]*/oferte/user/[^"]*)"', html)
    if mp:
        purl = mp.group(1)
        if purl.startswith("/"):
            purl = "https://www.olx.ro" + purl
        pause()
        rp = get(purl, HDRS_HTML, "V6")
        if rp and rp.status_code == 200:
            (OUT_DIR / f"_olx_rating_P{idx}.html").write_text(rp.text, encoding="utf-8")
            hits = kw_context_dump(rp.text, "V6")
            pstate, pv = load_prerendered_state(rp.text)
            if pstate is not None:
                printed: list = []
                walk_for_terms(pstate, "", printed)
                hits += len(printed)
            v6 = f"{hits} hituri"
    _summary.append(f"L{idx}: V1={v1} hituri HTML · V2={v2} chei state · V3={v3} ld+json · "
                    f"V4 data.keys=[{v4_keys[:120]}] · V5={v5} · V6={v6}")


def main() -> None:
    urls = sys.argv[1:] or LISTING_URLS
    if not urls:
        say("EROARE: completeaza LISTING_URLS in script sau da URL-urile ca argumente."); sys.exit(1)
    say(f"SONDA rating OLX — {len(urls[:3])} anunturi, impersonate={IMPERSONATE}")
    for i, u in enumerate(urls[:3], 1):
        probe_listing(i, u)
        pause()
    say(f"\n{'=' * 78}\nV7 — scan bundle-uri JS (o singura data, de pe L1):\n{'=' * 78}")
    first_html = OUT_DIR / "_olx_rating_L1.html"
    v7 = bundles_scan(first_html.read_text(encoding="utf-8")) if first_html.exists() else 0

    say(f"\n{'=' * 78}\nREZUMAT\n{'=' * 78}")
    for line in _summary:
        say("  " + line)
    say(f"  V7: {v7} siruri review/rating in bundle-uri")
    say("\nGata. Lipeste in chat fisierul olx_rating_sonda_output.txt integral.")


if __name__ == "__main__":
    main()
