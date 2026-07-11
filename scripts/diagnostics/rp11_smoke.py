# -*- coding: utf-8 -*-
"""RP-1.1 — live smoke: throttle real pe enrichment Vinted. <=2 requesturi HTML.

Ia 2 id-uri printr-un search wrapper (API — NU intra in bugetul HTML), apoi face 2
enrichment-uri HTML reale. Al 2-lea trebuie sa astepte >=20s (throttle). La blocked
(get_vinted_item_detail -> None din cauza 403/skip): STOP, fara reincercare.
"""
import sys
import os
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("GROQ_API_KEY", "x")

_RF = open(os.path.join(HERE, "rp11_raport.txt"), "w", encoding="utf-8")


def out(*p):
    t = " ".join(str(x) for x in p)
    _RF.write(t + "\n"); _RF.flush()
    try:
        print(t, flush=True)
    except Exception:
        print(t.encode("ascii", "replace").decode("ascii"), flush=True)


out("RP-1.1 — live smoke (throttle enrichment Vinted)")
out(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

from app.services.radar import vinted_html  # noqa: E402
from app.services.radar.vinted_scraper import get_vinted_item_detail  # noqa: E402

# ── id-uri prin wrapper (API, NU intra in bugetul HTML) ─────────────────────
ids = []
try:
    from vinted_scraper import VintedWrapper
    w = None
    for a in range(3):
        try:
            w = VintedWrapper("https://www.vinted.ro"); break
        except Exception as e:
            out(f"  wrapper attempt {a+1}/3: {str(e)[:60]}"); time.sleep(6)
    if w:
        s = w.search({"search_text": "iphone 12 pro", "order": "newest_first", "per_page": 12})
        for it in (s.get("items") or []):
            if "iphone" in (it.get("title") or "").lower() and it.get("id"):
                ids.append(str(it["id"]))
            if len(ids) >= 2:
                break
except Exception as e:
    out("wrapper search EXCEPTIE:", str(e)[:120])

out("id-uri (din wrapper, free):", ids)
if len(ids) < 2:
    out("STOP: nu am 2 id-uri de la wrapper — nu pot rula smoke-ul de throttle")
    out("[RP-1.1 smoke terminat]")
    _RF.close()
    sys.exit(0)

# ── enrichment 1 (HTML #1) — fara asteptare (fara request HTML anterior) ────
out("")
out("=== enrichment 1 (HTML request #1) ===")
gs = vinted_html.guard_status("vinted.ro")
out("guard_status inainte:", gs)
t0 = time.time()
d1 = get_vinted_item_detail(ids[0])
e1 = time.time() - t0
# Intervalul REAL pe care limiterul il impune intre req1 si req2 (ce vede DataDome):
# = momentul-tinta rezervat de fetch1 minus startul lui fetch1. Include jitter-ul.
reserved_next = vinted_html._domain_next_ts.get("vinted.ro", 0.0)
throttle_interval = reserved_next - t0
out(f"rezultat: {'OK' if d1 else 'SKIP/BLOCKED'} in {e1:.1f}s")
out(f"interval throttle impus intre req1 si req2 (via limiter): {throttle_interval:.1f}s "
    f"(>=20 asteptat; e2 wall-clock e mai mic cu ~procesarea lui fetch1)")
if d1:
    out("  attributes (sample):", dict(list((d1.get('attributes') or {}).items())[:4]))
if not d1:
    out("STOP: enrichment 1 blocat/skip (get_vinted_item_detail -> None) — fara reincercare")
    out("guard_status dupa:", vinted_html.guard_status("vinted.ro"))
    out("[RP-1.1 smoke terminat]")
    _RF.close()
    sys.exit(0)

# ── enrichment 2 (HTML #2) — trebuie throttled >=20s ────────────────────────
out("")
out("=== enrichment 2 (HTML request #2) — asteptat throttle >=20s ===")
t1 = time.time()
d2 = get_vinted_item_detail(ids[1])
e2 = time.time() - t1
out(f"rezultat: {'OK' if d2 else 'SKIP/BLOCKED'} in {e2:.1f}s")
out(f"throttle impus de limiter >=20s: {e2 >= 20.0}  (min_interval={vinted_html._MIN_INTERVAL['vinted.ro']}s, jitter<= {vinted_html._JITTER_MAX['vinted.ro']}s)")
if not d2:
    out("NOTA: enrichment 2 skip/blocked — vezi guard_status")
out("guard_status final:", vinted_html.guard_status("vinted.ro"))

out("")
out("[RP-1.1 smoke terminat — 2 requesturi HTML]")
_RF.close()
