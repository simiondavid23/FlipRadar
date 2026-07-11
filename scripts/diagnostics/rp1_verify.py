# -*- coding: utf-8 -*-
"""RP-1 FAZA 10 — verificare manuala (necomis).

Demonstreaza pipeline-ul de enrichment + badge de risc pe date REALE, respectand
plafonul de trafic (<=12 requesturi). NOTA importanta: search_okazii/publi24/olx
imbogatesc INTERN o pagina intreaga de rezultate (zeci de fetch-uri de detaliu),
deci a le apela integral ar depasi masiv plafonul. De aceea:
  - Vinted: LIVE (search-ul NU imbogateste per-item) + 1 detaliu on-demand;
  - OLX: LIVE minimal (o pagina de search pt. id numeric + 1 apel offers);
  - Okazii/Publi24: pe fixture-urile din tests/fixtures (parserele-s testate live-echiv).
"""
import sys
import os
import json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(REPO_ROOT, "backend")
FIX = os.path.join(BACKEND, "tests", "fixtures")
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("GROQ_API_KEY", "x")

from app.services.radar.scorer import compute_seller_risk  # noqa: E402

RESALE = 2500.0  # pret de revanzare presupus pentru "iphone 12 pro" (pt. calcul risc)
REQ = {"n": 0}


def row(platform, title, price, sn, sr, srat, la, risk):
    t = (title or "")[:34].ljust(34)
    return (f"{platform:<8} | {t} | {str(price):>7} | {str(sn or '-')[:16]:<16} | "
            f"rev={str(sr):<5} | rat={str(srat):<5} | {str(la or '-')[:19]:<19} | risc={risk}")


def hdr(t):
    print("\n" + "=" * 100)
    print(t)
    print("=" * 100)


# ── VINTED (live: search + 1 detaliu) ───────────────────────────────────────
hdr("VINTED — search live (seller/listed_at din search) + 1 detaliu on-demand")
try:
    from app.services.radar.vinted_scraper import search_vinted, get_vinted_item_detail
    REQ["n"] += 2  # cookie + search
    res = search_vinted("iphone 12 pro", max_price=5000, min_price=None)
    print(f"search_vinted -> {len(res)} rezultate\n")
    for it in res[:5]:
        risk, reason = compute_seller_risk("vinted", it.get("price"), RESALE,
                                           it.get("seller_name"), it.get("seller_reviews"),
                                           it.get("seller_rating"), it.get("extra_attributes"))
        print(row("vinted", it.get("title"), it.get("price"), it.get("seller_name"),
                  it.get("seller_reviews"), it.get("seller_rating"),
                  it.get("listed_at"), f"{risk}{' ('+reason+')' if reason else ''}"))
    if res:
        first = res[0]
        vid = (first.get("external_id") or "").replace("vinted_", "")
        print(f"\n-- enrichment on-demand pentru item {vid} (pagina HTML) --")
        REQ["n"] += 1
        det = get_vinted_item_detail(vid)
        if det:
            print("  seller_name   :", det.get("seller_name"))
            print("  seller_reviews:", det.get("seller_reviews"))
            print("  seller_rating :", det.get("seller_rating"), "(0-5)")
            print("  seller_badges :", det.get("seller_badges"))
            print("  listed_at     :", det.get("listed_at"))
            print("  attributes    :", det.get("attributes"))
            print("  description   :", (det.get("description") or "")[:80])
            risk, reason = compute_seller_risk("vinted", first.get("price"), RESALE,
                                               det.get("seller_name"), det.get("seller_reviews"),
                                               det.get("seller_rating"), det.get("attributes"))
            print("  => RISC:", risk, "|", reason)
        else:
            print("  detaliu None (403/blocaj) — enrichment ramane de reincercat")
except Exception as e:
    import traceback
    print("VINTED verify EXCEPTIE:", "".join(traceback.format_exc())[:1500])


# ── OLX (live minimal: 1 pagina search pt. id numeric + 1 apel offers) ───────
hdr("OLX — enrichment live minimal (id numeric din search + /api/v1/offers)")
try:
    from curl_cffi import requests as curl_requests
    from app.services.radar.base_scraper import build_headers
    from app.services.radar.olx_scraper import _extract_olx_numeric_ids, fetch_olx_offer_details
    REQ["n"] += 1
    r = curl_requests.get("https://www.olx.ro/oferte/q-iphone-12-pro/",
                          headers=build_headers({"Referer": "https://www.olx.ro/"}),
                          impersonate="chrome110", timeout=20)
    ids = _extract_olx_numeric_ids(r.text if r.status_code == 200 else "")
    first_id = next(iter(ids.values()), None)
    print(f"search HTTP {r.status_code}; id-uri numerice extrase: {len(ids)}; primul: {first_id}")
    if first_id:
        REQ["n"] += 1
        det = fetch_olx_offer_details(first_id)
        risk, reason = compute_seller_risk("olx", 800, RESALE, det.get("seller_name"),
                                           None, None, {"olx_member_since": det.get("olx_member_since")})
        print(row("olx", det.get("description", "")[:34], "~800", det.get("seller_name"),
                  "-", "-", det.get("listed_at"), f"{risk}{' ('+reason+')' if reason else ''}"))
        print("  member_since:", det.get("olx_member_since"), "| seller_id:", det.get("seller_id"))
except Exception as e:
    import traceback
    print("OLX verify EXCEPTIE:", "".join(traceback.format_exc())[:1200])


# ── OKAZII / PUBLI24 (fixture — evita enrichment-ul unei pagini intregi) ─────
hdr("OKAZII — parser vanzator pe fixture (fara trafic)")
try:
    from bs4 import BeautifulSoup
    from app.services.radar.okazii_scraper import _extract_okazii_seller
    with open(os.path.join(FIX, "okazii_info_seller.html"), encoding="utf-8") as f:
        s = _extract_okazii_seller(BeautifulSoup(f.read(), "html.parser"))
    risk, reason = compute_seller_risk("okazii", 100, RESALE, s.get("seller_name"),
                                       s.get("seller_reviews"), s.get("seller_rating"), s)
    print(row("okazii", "(fixture) " + (s.get("seller_name") or ""), 100, s.get("seller_name"),
              s.get("seller_reviews"), s.get("seller_rating"), None, f"{risk}"))
    print("  seller_type:", s.get("okazii_seller_type"))
except Exception as e:
    print("OKAZII verify EXCEPTIE:", str(e)[:200])

hdr("PUBLI24 — parser data pe fixture (fara trafic)")
try:
    from app.services.radar.publi24_scraper import _parse_valabil_din
    with open(os.path.join(FIX, "publi24_valabil.html"), encoding="utf-8") as f:
        dt = _parse_valabil_din(f.read())
    print("  listed_at (Valabil din):", dt, "| seller_name: indisponibil public (§7)")
    risk, reason = compute_seller_risk("publi24", 100, RESALE, None, None, None, None)
    print("  => RISC (vanzator necunoscut + pret mic):", risk, "|", reason)
except Exception as e:
    print("PUBLI24 verify EXCEPTIE:", str(e)[:200])


print(f"\n[Requesturi HTTP folosite (aprox): {REQ['n']}]")
print("[RP-1 verify terminat]")
