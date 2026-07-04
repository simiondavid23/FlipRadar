#!/usr/bin/env python3
"""TEMP — verificare extinsa search_facebook (curl_cffi). NU face parte din livrabil.
Ruleaza direct functia (nu prin API). Sectiuni: b1, b2, b3 (argv). Fara argv -> b2,b3.

Foloseste componentele REALE ale modulului (read-only) — nu modifica logica.
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BACKEND = r"C:\licenta\flipRadar\backend"
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import app.services.radar.facebook_scraper as fb
from app.services.radar.facebook_scraper import search_facebook
from app.services.radar.categories import PLATFORM_CATEGORIES
from app.services.log_manager import log_manager

SESSION = r"C:\licenta\flipRadar\backend\data\facebook_session_13.json"
SCRATCH = r"C:\Users\david\AppData\Local\Temp\claude\C--licenta\0f9575a2-22cb-4e46-bd0e-739e07f0fb95\scratchpad"

# instrumentare fetch (test-only): numaram cate GET-uri reale se fac
_orig_fetch = fb._fetch
_fetch_calls = {"n": 0}
def _counting_fetch(url, cookies):
    _fetch_calls["n"] += 1
    return _orig_fetch(url, cookies)
fb._fetch = _counting_fetch


def _logs_since(last_id):
    return [e for e in log_manager.get_all("radar") if e["id"] > last_id]


def _last_log_id():
    lg = log_manager.get_all("radar")
    return lg[-1]["id"] if lg else 0


# cuvinte cheie relevante per id de categorie
KW = {
    "1567543000236608": "geanta", "1266429133383966": "rochie",
    "931157863635831": "adidasi", "214968118845643": "bratara",
    "1792291877663080": "laptop", "1557869527812749": "telefon",
    "686977074745292": "xbox", "613858625416355": "carti",
    "624859874282116": "carucior", "1555452698044988": "parfum",
    "800089866739547": "fantana", "1658310421102081": "bicicleta",
    "757715671026531": "jante", "1534799543476160": "tablou",
    "393860164117441": "moneda", "678754142233400": "frigider",
    "1583634935226685": "canapea", "1569171756675761": "lenjerie pat",
    "1670493229902393": "bormasina", "676772489112490": "chitara",
    "895487550471874": "tobe", "1550246318620997": "lesa caine",
    "1468271819871448": "apartament de inchiriat", "1383948661922113": "aparat fitness",
    "606456512821491": "lego", "807311116002614": "masina",
}


def all_category_values():
    out = []
    for c in PLATFORM_CATEGORIES["facebook"]:
        if c.get("value"):
            out.append((str(c["value"]), c["label"], "top"))
        for s in c.get("subcategories") or []:
            if s.get("value"):
                out.append((str(s["value"]), s["label"], "sub"))
    return out


def _count_log(logs, needle):
    return sum(1 for e in logs if needle in e["msg"])


def section_b1():
    print("\n" + "#" * 78)
    print("# B1 — ACOPERIRE PE CATEGORII (search_facebook direct, filtru de categorie)")
    print("#" * 78)
    cats = all_category_values()
    print(f"# {len(cats)} valori de categorie (NU 19 cum estima prompt-ul)\n")
    sold_total = 0
    for i, (val, label, kind) in enumerate(cats):
        kw = KW.get(val, label)
        # before (fara filtru)
        before = search_facebook(keyword=kw, max_price=0, session_path=SESSION, min_price=0)
        time.sleep(2.5)
        # after (cu filtru de categorie) + capturam log-urile
        lid = _last_log_id()
        after = search_facebook(keyword=kw, max_price=0, session_path=SESSION, min_price=0, category=val)
        logs = _logs_since(lid)
        unknown = _count_log(logs, "category_id necunoscut")
        sold = 0
        for e in logs:
            if "excluse (sold" in e["msg"]:
                try:
                    sold = int(e["msg"].split("Facebook:")[1].strip().split()[0])
                except Exception:
                    sold = 0
        sold_total += sold
        titles = [r["title"] for r in after[:3]]
        print(f"[{i+1:2d}/{len(cats)}] {label} ({kind}) id={val} kw='{kw}'")
        print(f"      before={len(before):2d}  after={len(after):2d}  unknown_cat_logat={unknown}  sold_excl={sold}")
        for t in titles:
            print(f"        · {t}")
        time.sleep(2.5)
    print(f"\n# B1 TOTAL sold/not-live/pending/hidden excluse (din toate rularile): {sold_total}")


def section_b2():
    print("\n" + "#" * 78)
    print("# B2 — CAZURI LIMITA")
    print("#" * 78)

    # 1) keyword gol -> [] fara fetch
    _fetch_calls["n"] = 0
    r = search_facebook(keyword="", max_price=0, session_path=SESSION)
    ok = (r == []) and (_fetch_calls["n"] == 0)
    print(f"[keyword gol] result={r} fetch_calls={_fetch_calls['n']} -> {'PASS' if ok else 'FAIL'}")

    # 2) page=2 -> [] fara fetch
    _fetch_calls["n"] = 0
    r = search_facebook(keyword="iphone", max_price=0, session_path=SESSION, page=2)
    ok = (r == []) and (_fetch_calls["n"] == 0)
    print(f"[page=2] result_len={len(r)} fetch_calls={_fetch_calls['n']} -> {'PASS' if ok else 'FAIL'}")

    # 3) session_path inexistent -> [] + WARN, fara crash
    lid = _last_log_id()
    _fetch_calls["n"] = 0
    try:
        r = search_facebook(keyword="iphone", max_price=0, session_path=r"C:\nu\exista\sesiune.json")
        logs = _logs_since(lid)
        warn = any(e["level"] == "WARN" for e in logs)
        ok = (r == []) and (_fetch_calls["n"] == 0) and warn
        print(f"[session inexistent] result_len={len(r)} fetch={_fetch_calls['n']} warn={warn} -> {'PASS' if ok else 'FAIL'}")
    except Exception as exc:
        print(f"[session inexistent] CRASH {type(exc).__name__}: {exc} -> FAIL")

    # 4) session JSON corupt -> [] + fara crash necontrolat
    bad = os.path.join(SCRATCH, "fb_bad_session.json")
    with open(bad, "w", encoding="utf-8") as f:
        f.write("{ asta nu e json valid ,,, ")
    lid = _last_log_id()
    _fetch_calls["n"] = 0
    try:
        r = search_facebook(keyword="iphone", max_price=0, session_path=bad)
        ok = (r == []) and (_fetch_calls["n"] == 0)
        print(f"[session corupt] result_len={len(r)} fetch={_fetch_calls['n']} -> {'PASS' if ok else 'FAIL'}")
    except Exception as exc:
        print(f"[session corupt] CRASH {type(exc).__name__}: {exc} -> FAIL")

    # 5) min/max price
    time.sleep(2)
    res = search_facebook(keyword="iphone", max_price=0, session_path=SESSION, min_price=0)
    time.sleep(2.5)
    lo, hi = 1000.0, 3000.0
    res_f = search_facebook(keyword="iphone", max_price=hi, session_path=SESSION, min_price=lo)
    prices = [r["price"] for r in res_f if r["price"] is not None]
    in_range = all(lo <= p <= hi for p in prices)
    print(f"[min/max price] fara filtru={len(res)}  cu [{lo},{hi}]={len(res_f)}  "
          f"preturi_non_null={len(prices)} toate_in_interval={in_range} -> {'PASS' if in_range else 'FAIL'}")
    print(f"      interval preturi ramase: {min(prices) if prices else None}..{max(prices) if prices else None}")

    # 6) exclude_words
    time.sleep(2.5)
    base = search_facebook(keyword="telefon", max_price=0, session_path=SESSION, min_price=0)
    # alege un cuvant care apare sigur in titluri
    from collections import Counter
    words = Counter()
    for r in base:
        for w in (r["title"] or "").lower().split():
            if len(w) >= 4:
                words[w] += 1
    excl = None
    for w, c in words.most_common():
        if 1 <= c < len(base):
            excl = w
            break
    time.sleep(2.5)
    filt = search_facebook(keyword="telefon", max_price=0, session_path=SESSION, min_price=0, exclude_words=[excl] if excl else [])
    none_contains = all(excl not in (r["title"] or "").lower() for r in filt) if excl else True
    dropped = len(base) - len(filt)
    print(f"[exclude_words] cuvant='{excl}' base={len(base)} dupa={len(filt)} scazut={dropped} "
          f"niciun_titlu_contine={none_contains} -> {'PASS' if (excl and dropped >= 0 and none_contains) else 'INFO'}")

    # 7) dedup: raw walker vs unique id (aceeasi pagina)
    time.sleep(2.5)
    url = fb._build_search_url("iphone", 0, 0)
    cookies = fb._load_cookies(SESSION)
    html, _ = _orig_fetch(url, cookies)
    raw = fb._iter_listing_objects(html or "")
    uniq = len(set(str(o.get("id")) for o in raw))
    final = search_facebook(keyword="iphone", max_price=0, session_path=SESSION, min_price=0)
    print(f"[dedup] obiecte_brute_walker={len(raw)}  id_unice={uniq}  rezultat_final={len(final)}  "
          f"(dedup a redus {len(raw)-uniq} duplicate brute)")

    # 8) diacritice / unicode
    for kw in ["mașină", "canapea extensibilă"]:
        time.sleep(2.5)
        try:
            r = search_facebook(keyword=kw, max_price=0, session_path=SESSION, min_price=0)
            ex = r[0]["title"] if r else "(0 rezultate)"
            print(f"[diacritice '{kw}'] rezultate={len(r)} ex='{ex}' -> {'PASS' if isinstance(r, list) else 'FAIL'}")
        except Exception as exc:
            print(f"[diacritice '{kw}'] CRASH {type(exc).__name__}: {exc} -> FAIL")


def section_b3():
    print("\n" + "#" * 78)
    print("# B3 — needs_reauth IZOLAT (fara re_authenticate real)")
    print("#" * 78)
    from app.services.facebook_auth import needs_reauth

    valid = {"cookies": [{"name": "c_user", "value": "x"}], "origins": []}
    old = os.path.join(SCRATCH, "fb_sess_old.json")
    new = os.path.join(SCRATCH, "fb_sess_new.json")
    for p in (old, new):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(valid, f)
    now = time.time()
    os.utime(old, (now - 100000, now - 100000))  # ~27.7h vechime
    os.utime(new, (now - 3600, now - 3600))       # 1h vechime

    r_old = needs_reauth([], old)
    r_new = needs_reauth([], new)
    r_results = needs_reauth([{"x": 1}], old)  # results ne-goale -> False
    print(f"[old >23h, results=[]]  needs_reauth={r_old}  (astept True)  -> {'PASS' if r_old is True else 'FAIL'}")
    print(f"[new 1h,   results=[]]  needs_reauth={r_new}  (astept False) -> {'PASS' if r_new is False else 'FAIL'}")
    print(f"[old, results ne-gol]   needs_reauth={r_results} (astept False) -> {'PASS' if r_results is False else 'FAIL'}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["b2", "b3"]
    if "b1" in which:
        section_b1()
    if "b2" in which:
        section_b2()
    if "b3" in which:
        section_b3()
    print("\n[fb_verify] gata:", which)
