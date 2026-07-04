#!/usr/bin/env python3
"""
FB Marketplace — DIAGNOSTIC FAZA 0 (script de UNICA folosinta).

NU face parte din arborele de productie si NU importa/modifica search_facebook,
facebook_auth, categories sau alt cod existent. Doar CITESTE fisierul de sesiune
salvat si face cateva fetch-uri diagnostice cu curl_cffi, raportand DATE BRUTE.

Reguli de securitate:
- NU se printeaza NICIODATA valorile cookie-urilor (doar numarul + prezenta c_user
  + numele cookie-urilor, care nu sunt secrete).

Utilizare:
    python fb_diagnostic.py [--out DIR]
`--out` = unde se salveaza artefactele (dump HTML / snippet). Implicit: dir-ul
scriptului. Rulat cu un director in afara repo-ului -> git ramane curat.
"""

import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys

# --- UTF-8 stdout pe consola Windows (diacritice romanesti) ---
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Calea reala a proiectului (vezi memoria flipradar-layout).
BACKEND_DIR = r"C:\licenta\flipRadar\backend"
# Fallback identic cu app/config.py daca .env nu are DATABASE_URL.
DEFAULT_DATABASE_URL = "postgresql://postgres:***REMOVED***@localhost:5432/flipradar"

# Header realiste de browser (UA Chrome + Accept-Language cerut).
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

SEARCH_URL = "https://www.facebook.com/marketplace/search/?query=iphone&minPrice=0"
CATEGORY_SLUG_URL = "https://www.facebook.com/marketplace/category/electronics/"

# Semnale de login-wall / checkpoint in HTML.
LOGIN_FORM_PATTERNS = [
    r'id="login_form"',
    r'name="login"',
    r'action="[^"]*/login',
    r'<input[^>]+name="pass"',
    r'You must log in',
    r'Log in to Facebook',
    r'Log In or Sign Up',
    r'id="loginbutton"',
]


def resolve_session_path():
    """Rezolva calea sesiunii FB *din cod/DB*, fara a presupune.

    Ordine:
      1) radar_settings.facebook_session_path din DB (daca e set + fisierul exista)
      2) default builder <backend>/data/facebook_session_{user_id}.json (mirror la
         _default_facebook_session_path din app/routers/radar.py)
      3) glob dupa <backend>/data/facebook_session_*.json
    Returneaza (path|None, provenance_str, db_rows).
    """
    provenance = []
    db_rows = []

    # 1) DB
    try:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(BACKEND_DIR, ".env"))
        except Exception:
            pass
        db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, user_id, facebook_session_path FROM radar_settings ORDER BY user_id"
                )
                db_rows = cur.fetchall()
        finally:
            conn.close()
        provenance.append(f"DB radar_settings: {len(db_rows)} rand(uri)")
        for r in db_rows:
            provenance.append(
                f"  id={r['id']} user_id={r['user_id']} "
                f"facebook_session_path={r['facebook_session_path']!r}"
            )
        # a) primul path setat in DB care exista pe disk
        for r in db_rows:
            p = r.get("facebook_session_path")
            if p and os.path.isfile(p):
                provenance.append(f"-> ales din DB (fisier exista): {p}")
                return p, "\n".join(provenance), db_rows
        # b) default builder pentru fiecare user_id din DB
        for r in db_rows:
            uid = r.get("user_id")
            cand = os.path.join(BACKEND_DIR, "data", f"facebook_session_{uid}.json")
            if os.path.isfile(cand):
                provenance.append(
                    f"-> ales via default builder pentru user_id={uid}: {cand}"
                )
                return cand, "\n".join(provenance), db_rows
    except Exception as exc:
        provenance.append(f"DB lookup a esuat: {type(exc).__name__}: {exc}")

    # 3) glob pe disk
    data_dir = os.path.join(BACKEND_DIR, "data")
    cands = sorted(glob.glob(os.path.join(data_dir, "facebook_session_*.json")))
    provenance.append(f"glob {os.path.join(data_dir, 'facebook_session_*.json')} -> {cands}")
    if cands:
        provenance.append(f"-> ales primul de pe disk: {cands[0]}")
        return cands[0], "\n".join(provenance), db_rows

    return None, "\n".join(provenance), db_rows


def load_cookies(session_path):
    """storage_state Playwright -> dict {name: value}. NU printeaza valori."""
    with open(session_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("cookies") if isinstance(data, dict) else data
    cookies = {}
    for c in (raw or []):
        n = c.get("name")
        v = c.get("value")
        if n is not None:
            cookies[n] = "" if v is None else v
    storage = data if isinstance(data, dict) else {}
    return cookies, storage


def looks_like_login_wall(final_url, html):
    hits = []
    lu = (final_url or "").lower()
    if "login" in lu:
        hits.append("url final contine 'login'")
    if "checkpoint" in lu:
        hits.append("url final contine 'checkpoint'")
    for pat in LOGIN_FORM_PATTERNS:
        if re.search(pat, html, re.IGNORECASE):
            hits.append(f"HTML match: {pat}")
    return hits


def fetch_and_report(label, url, cookies, out_dir, dump_name):
    """Fetch curl_cffi + raport complet de date brute. Returneaza dict sau None."""
    from curl_cffi import requests as creq

    print("\n" + "=" * 78)
    print(f"[{label}] GET {url}")
    print("=" * 78)
    try:
        resp = creq.get(
            url,
            cookies=cookies,
            headers=HEADERS,
            impersonate="chrome110",
            allow_redirects=True,
            timeout=45,
        )
    except Exception as exc:
        print(f"  EROARE fetch: {type(exc).__name__}: {exc}")
        return None

    html = resp.text or ""
    print(f"  status_code : {resp.status_code}")
    print(f"  final_url   : {resp.url}")
    print(f"  len(text)   : {len(html)} chars")
    try:
        print(f"  len(content): {len(resp.content)} bytes")
    except Exception:
        pass

    dump_path = os.path.join(out_dir, dump_name)
    try:
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  dump salvat : {dump_path}")
    except Exception as exc:
        print(f"  dump EROARE : {exc}")

    # a) login-wall / checkpoint
    hits = looks_like_login_wall(str(resp.url), html)
    print(f"  a) login-wall/checkpoint semnale: {hits if hits else 'niciunul'}")

    # b, c) marker-e de card
    mpi = html.count("MarketplaceProductItem")
    gcpi = html.count("GroupCommerceProductItem")
    print(f"  b) 'MarketplaceProductItem'  : {mpi}")
    print(f"  c) 'GroupCommerceProductItem': {gcpi}")

    # d) <script type="application/json"> (tolerant la atribute suplimentare)
    json_scripts = re.findall(r'<script[^>]*type="application/json"', html)
    print(f'  d) <script type="application/json"> tag-uri: {len(json_scripts)}')

    # e) ID-uri de anunt via regex ceruta
    ids_exact = re.findall(r"/marketplace/item/(\d+)", html)
    uniq_exact = sorted(set(ids_exact), key=ids_exact.index)
    # supliment: FB serializeaza JSON cu '\/' escaping -> varianta toleranta
    ids_tol = re.findall(r"\\?/marketplace\\?/item\\?/(\d+)", html)
    uniq_tol = sorted(set(ids_tol), key=ids_tol.index)
    print(f"  e) /marketplace/item/(\\d+) UNICE (regex exact ceruta): {len(uniq_exact)}")
    print(f"     primele 5: {uniq_exact[:5]}")
    print(
        f"     [supliment] varianta toleranta la '\\/' escaping: "
        f"{len(uniq_tol)} unice, primele 5: {uniq_tol[:5]}"
    )

    return {
        "status": resp.status_code,
        "final_url": str(resp.url),
        "len": len(html),
        "html": html,
        "login_hits": hits,
        "mpi": mpi,
        "gcpi": gcpi,
        "json_scripts": len(json_scripts),
        "ids_exact": uniq_exact,
        "ids_tol": uniq_tol,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="director pentru artefacte (dump/snippet)",
    )
    args = ap.parse_args()
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    print("#" * 78)
    print("# FB Marketplace — DIAGNOSTIC FAZA 0 (date brute, fara concluzii)")
    print("#" * 78)
    print(f"out_dir artefacte: {out_dir}")

    # ---- PAS 1: rezolvare cale sesiune ----
    print("\n----- PAS 1: rezolvare cale sesiune FB (din cod/DB) -----")
    session_path, provenance, _db_rows = resolve_session_path()
    print(provenance)
    print(f"CALE SESIUNE REZOLVATA: {session_path}")
    if not session_path or not os.path.isfile(session_path):
        print("Nu exista fisier de sesiune -> STOP.")
        return
    st = os.stat(session_path)
    print(
        f"  fisier exista, size={st.st_size} bytes, "
        f"mtime={_dt.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}"
    )

    # ---- PAS 2: incarcare cookies (FARA valori) ----
    print("\n----- PAS 2: incarcare cookies (storage_state Playwright) -----")
    cookies, storage = load_cookies(session_path)
    print(f"  numar cookies : {len(cookies)}")
    print(f"  are 'c_user'  : {'c_user' in cookies}")
    print(f"  nume cookies  : {sorted(cookies.keys())}")
    if storage:
        print(f"  storage_state chei top-level: {list(storage.keys())}")
        origins = storage.get("origins")
        if isinstance(origins, list):
            print(f"  origins (localStorage) count: {len(origins)}")

    # ---- PAS 2b: fetch SEARCH ----
    search = fetch_and_report(
        "SEARCH query=iphone", SEARCH_URL, cookies, out_dir, "fb_search_dump.html"
    )

    # snippet daca MarketplaceProductItem >= 1
    if search and search["mpi"] >= 1:
        idx = search["html"].find("MarketplaceProductItem")
        start = max(0, idx - 1000)
        end = min(len(search["html"]), idx + 1000)
        snippet = search["html"][start:end]
        snip_path = os.path.join(out_dir, "fb_search_snippet.txt")
        with open(snip_path, "w", encoding="utf-8") as f:
            f.write(snippet)
        print(
            f"\n  [snippet] 'MarketplaceProductItem' gasit la index {idx} "
            f"-> salvat {snip_path} ({len(snippet)} chars)"
        )
    else:
        print(
            "\n  [snippet] 'MarketplaceProductItem' NU a aparut "
            "-> fb_search_snippet.txt NU se genereaza"
        )

    # ---- PAS 3a: fetch CATEGORY slug ----
    fetch_and_report(
        "CATEGORY electronics (slug)",
        CATEGORY_SLUG_URL,
        cookies,
        out_dir,
        "fb_category_dump.html",
    )

    # ---- PAS 3b: fetch DETAIL (daca avem un id din pasul 2) ----
    item_ids = []
    if search:
        item_ids = search["ids_exact"] or search["ids_tol"]
    if item_ids:
        item_id = item_ids[0]
        detail_url = f"https://www.facebook.com/marketplace/item/{item_id}/"
        detail = fetch_and_report(
            f"DETAIL item {item_id}", detail_url, cookies, out_dir, "fb_item_dump.html"
        )
        if detail:
            html = detail["html"]
            print("\n  [DETAIL] cautare cuvinte-cheie in HTML/JSON (numar aparitii):")
            key_groups = {
                "pret": ['"price"', '"amount"', '"amount_with_offset"',
                         '"formatted_amount"', '"currency"'],
                "data_postare": ['"creation_time"', 'creation_time', '"listing_date"',
                                 '"time"', 'zile in urma', 'days ago', 'weeks ago'],
                "descriere": ['"redacted_description"', '"description"',
                              'marketplace_listing_title', '"custom_title"'],
                "vanzator": ['"marketplace_listing_seller"', '"story_seller"',
                             '"seller"', '"actor"', '__isActor'],
            }
            for grup, patterns in key_groups.items():
                parts = [f"{pat}={html.count(pat)}" for pat in patterns]
                print(f"    {grup}: " + ", ".join(parts))
    else:
        print("\n  [DETAIL] niciun id de anunt gasit la pasul 2 -> se sare pagina de detaliu")

    print("\n" + "#" * 78)
    print(f"# GATA. Artefacte in: {out_dir}")
    print("#" * 78)


if __name__ == "__main__":
    main()
