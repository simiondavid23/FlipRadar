# -*- coding: utf-8 -*-
"""RP-1 FAZA 0 — sonde de structura (READ-ONLY, inaintea implementarii).

Produce scripts/diagnostics/rp1_sonda_output.txt + fixtures pentru teste.
Nu comite nimic. Trafic <= 8 requesturi. Foloseste structurile REALE gasite
pentru a ghida implementarea din fazele urmatoare.
"""
import sys
import os
import re
import json
import time
import glob
import random
import traceback

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

OUT_PATH = os.path.join(HERE, "rp1_sonda_output.txt")
_OUT_F = open(OUT_PATH, "w", encoding="utf-8")


def out(*parts):
    text = " ".join(str(p) for p in parts)
    _OUT_F.write(text + "\n")
    _OUT_F.flush()
    try:
        print(text, flush=True)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def ctx(hay, needle, radius=800, max_hits=1, label=None):
    low = hay.lower()
    nl = needle.lower()
    idx = 0
    hits = 0
    while hits < max_hits:
        p = low.find(nl, idx)
        if p < 0:
            break
        seg = hay[max(0, p - radius): p + len(needle) + radius]
        out(f"  [±{radius} '{needle}' @ {p}]:")
        out("   " + seg.replace("\n", "\\n"))
        idx = p + len(needle)
        hits += 1
    if hits == 0:
        out(f"  '{needle}': 0 aparitii")
    return hits


def banner(step, title):
    out("")
    out("=" * 78)
    out(f"==={step}===  {title}")
    out("=" * 78)


out("RP-1 FAZA 0 — sonde de structura")
out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
out("NOTA: fisier NECOMIS. Fara git add/commit/push.")


# ╔════════════════════════ S0 ════════════════════════╗
try:
    banner("S0", "Maparea RadarListing + conventia datetime (fara requesturi)")

    def read_lines(rel):
        with open(os.path.join(BACKEND, rel), encoding="utf-8") as f:
            return f.readlines()

    scanner = read_lines("app/utils/radar_scanner.py")
    # localizeaza RadarListing(...) si printeaza blocul
    start = None
    for i, ln in enumerate(scanner):
        if "listing_db = RadarListing(" in ln:
            start = i
            break
    if start is not None:
        out("--- constructia RadarListing(...) la salvare (radar_scanner.py) ---")
        for i in range(start, min(start + 24, len(scanner))):
            out(f"  {i+1}: {scanner[i].rstrip(chr(10))}")
            if scanner[i].strip() == ")":
                break
    else:
        out("  <nu am gasit 'listing_db = RadarListing('>")

    # ce chei din dict-ul scraperului sunt copiate
    mapped = re.findall(r"=\s*listing\.get\(\"(\w+)\"\)", "".join(scanner))
    out("chei listing.get(...) copiate azi in RadarListing:", sorted(set(mapped)))
    for col in ["seller_name", "seller_id", "listed_at", "attributes_json", "seller_reviews", "seller_rating", "seller_risk"]:
        out(f"  '{col}' deja persistat azi:", any(col in m for m in mapped) or f"coloana {col} folosita direct" if col in "".join(scanner) else False)

    out("--- conventia datetime pentru listed_at (scrapere existente) ---")
    for rel, name in [
        ("app/services/radar/vinted_scraper.py", "datetime.fromtimestamp"),
        ("app/services/radar/olx_scraper.py", "datetime("),
        ("app/services/radar/publi24_scraper.py", "datetime("),
    ]:
        txt = "".join(read_lines(rel))
        has_naive = "fromtimestamp" in txt or re.search(r"datetime\(\s*year", txt) or "datetime(year" in txt
        out(f"  {rel}: fromtimestamp={'fromtimestamp' in txt} · tz-aware(utc)={'timezone.utc' in txt}")
    out("model radar_listing: found_at=aware UTC (default), listed_at=DateTime naiv (coloana fara tz)")
    out("DECIZIE S0: listed_at = datetime NAIV local (consecvent cu OLX/_parse_olx_date, "
        "Publi24/_parse_date, Vinted/datetime.fromtimestamp). seller_name/seller_id/listed_at "
        "SUNT deja mapate la salvare; adaug DOAR attributes_json/seller_reviews/seller_rating/seller_risk.")
except Exception as e:
    out("S0 EXCEPTIE:", "".join(traceback.format_exc())[:1500])


# ╔════════════════════════ S1 ════════════════════════╗
RSC = None
try:
    banner("S1", "Vinted item: decodare RSC __next_f + cai exacte")
    from vinted_scraper import VintedWrapper
    from curl_cffi import requests as curl_requests

    w = None
    for attempt in range(3):
        try:
            w = VintedWrapper("https://www.vinted.ro")
            break
        except Exception as e:
            delay = 2 * (2 ** attempt)
            out(f"  construct wrapper {attempt+1}/3 esuat ({str(e)[:70]}), backoff {delay}s")
            time.sleep(delay)
    if w is None:
        out("STOP S1: nu am putut construi VintedWrapper (cookie)")
    else:
        time.sleep(6)
        s = w.search({"search_text": "iphone 12 pro", "order": "newest_first", "per_page": 20})
        item = None
        for it in (s.get("items") or []):
            if "iphone" in (it.get("title") or "").lower():
                item = it
                break
        item = item or (s.get("items") or [None])[0]
        if not item:
            out("STOP S1: search fara iteme")
        else:
            iid = item.get("id")
            iurl = item.get("url") or f"https://www.vinted.ro/items/{iid}"
            out("item ales: id=", iid, "url=", iurl, "title=", item.get("title"))
            out("search: user.login=", (item.get("user") or {}).get("login"),
                "user.id=", (item.get("user") or {}).get("id"),
                "photo.high_resolution.timestamp=", ((item.get("photo") or {}).get("high_resolution") or {}).get("timestamp"))

            sess = curl_requests.Session(impersonate="chrome131", timeout=20, allow_redirects=True)
            time.sleep(6)
            r = sess.get(iurl, headers={"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"})
            out("item page HTTP:", r.status_code, "len:", len(r.text or ""))
            html = r.text or ""

            # Decodare RSC: self.__next_f.push([1,"...escaped..."])
            chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', html)
            decoded_parts = []
            for c in chunks:
                try:
                    decoded_parts.append(json.loads('"' + c + '"'))
                except Exception:
                    continue
            RSC = "".join(decoded_parts)
            out(f"chunks __next_f[1,...]: {len(chunks)}; decoded len: {len(RSC)}")

            fx = os.path.join(FIXTURES, "vinted_item_rsc.txt")
            with open(fx, "w", encoding="utf-8") as f:
                f.write(RSC)
            out("fixture salvat:", fx)

            fc = RSC.count("feedback_count")
            out("aparitii 'feedback_count' in RSC decodat:", fc)
            if fc == 0:
                out("STOP componenta 'feedback Vinted': feedback_count absent in RSC")
            for anchor, rad in [("feedback_count", 800), ("feedback_reputation", 400),
                                 ("seller_badges_info", 800), ("Sănătatea bateriei", 500),
                                 ("Capacitate de stocare", 500), ("\"photos\"", 700),
                                 ("\"attributes\"", 900)]:
                ctx(RSC, anchor, radius=rad, max_hits=1)
            # salvez si un fragment ld+json din HTML
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            if m:
                out("--- ld+json Product (din HTML) ---")
                out("  " + m.group(1)[:900])
except Exception as e:
    out("S1 EXCEPTIE:", "".join(traceback.format_exc())[:1800])


# ╔════════════════════════ S2 ════════════════════════╗
try:
    banner("S2", "OLX id numeric din __PRERENDERED_STATE__")
    from app.services.radar.base_scraper import build_headers
    from curl_cffi import requests as curl_requests

    r = curl_requests.get("https://www.olx.ro/oferte/q-iphone-12-pro/",
                          headers=build_headers({"Referer": "https://www.olx.ro/"}),
                          impersonate="chrome110", timeout=20)
    out("OLX search HTTP:", r.status_code)
    html = r.text if r.status_code == 200 else ""
    m = re.search(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', html, re.DOTALL)
    mapped = 0
    if m:
        state = json.loads(json.loads(m.group(1)))
        ads = (state.get("listing") or {}).get("listing", {}).get("ads") or []
        out(f"anunturi in state: {len(ads)}; maparea id_numeric -> url pentru 3 carduri:")
        for ad in ads[:3]:
            aid = ad.get("id")
            url = ad.get("url") or ad.get("urlPath") or ""
            tok = re.search(r"-ID([A-Za-z0-9]+)\.html", url)
            out(f"  id_numeric={aid} · external_id_token={tok.group(1) if tok else '?'} · url={url[:80]}")
            if aid:
                mapped += 1
        out("DECIZIE S2:", "id numeric ACCESIBIL din __PRERENDERED_STATE__.ads[].id -> folosesc /api/v1/offers/{id}"
            if mapped else "id numeric NEGASIT -> fallback pe pagina HTML de detaliu (selectorii §5)")
    else:
        out("STOP S2: __PRERENDERED_STATE__ negasit -> fallback pe HTML detaliu (§5)")
except Exception as e:
    out("S2 EXCEPTIE:", "".join(traceback.format_exc())[:1500])


# ╔════════════════════════ S3 ════════════════════════╗
try:
    banner("S3", "Facebook payload: campuri de trust (doar daca sesiune valida)")
    from app.services.radar.facebook_scraper import (
        is_facebook_session_valid, _load_cookies, _fetch, _build_search_url, _iter_listing_objects,
    )
    sess_files = glob.glob(os.path.join(BACKEND, "data", "facebook_session_*.json"))
    sess_files += glob.glob(os.path.join(REPO_ROOT, "data", "facebook_session_*.json"))
    valid = [p for p in sess_files if is_facebook_session_valid(p)]
    out("sesiuni FB valide:", len(valid), "(basenames:", [os.path.basename(p) for p in valid], ")")
    if not valid:
        out("S3 SKIP: nicio sesiune FB valida -> componenta 'trust FB' se inchide")
    else:
        sp = valid[0]
        url = _build_search_url("iphone", None, None)
        html, final = _fetch(url, _load_cookies(sp))
        if not html:
            out("S3: fetch marketplace esuat -> trust FB indisponibil")
        else:
            objs = _iter_listing_objects(html)
            out(f"obiecte listing gasite: {len(objs)}")
            trust_tokens = ["rating", "recommend", "joined", "member", "follower"]
            found = {}
            def walk(o, path="root", depth=0):
                if depth > 14:
                    return
                if isinstance(o, dict):
                    for k, v in o.items():
                        kl = str(k).lower()
                        if any(t in kl for t in trust_tokens):
                            found.setdefault(k, str(v)[:120])
                        walk(v, f"{path}.{k}", depth + 1)
                elif isinstance(o, list):
                    for x in o[:20]:
                        walk(x, path, depth + 1)
            for o in objs[:5]:
                walk(o)
            # si un scan pe tot HTML-ul dupa numele cheilor
            html_keys = {}
            for t in trust_tokens:
                for mm in re.finditer(r'"([a-zA-Z_]*' + t + r'[a-zA-Z_]*)"\s*:', html):
                    html_keys.setdefault(mm.group(1), 0)
                    html_keys[mm.group(1)] += 1
            out("chei trust in obiectele listing:", found or "NICIUNA")
            out("chei trust (regex pe HTML, top):", dict(list(html_keys.items())[:15]) or "NICIUNA")
            if not found and not html_keys:
                out("S3 REZULTAT: niciun camp de trust in payload-ul folosit -> FAZA 6 se sare")
            else:
                out("S3 REZULTAT: exista campuri candidate -> FAZA 6 poate extrage best-effort")
except Exception as e:
    out("S3 EXCEPTIE:", "".join(traceback.format_exc())[:1500])


out("")
out("[RP-1 FAZA 0 terminat]")
_OUT_F.close()
