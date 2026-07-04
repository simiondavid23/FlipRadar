"""Script de mapare categorii Publi24 -> PLATFORM_CATEGORIES["publi24"].

Rulare (din backend/, cu venv):
    python -m scripts.map_publi24_categories

Strategie: Publi24 foloseste path-uri /anunturi/{categorie}/{subcategorie}/ (aceeasi
adancime ca judetul, care e tot segment de path). Deci:
  1. de pe homepage extragem cele 12 categorii principale (link-uri 1-segment care
     NU sunt judete);
  2. pentru fiecare, fetch /anunturi/{categorie}/ si extragem link-urile de
     subcategorie /anunturi/{categorie}/{sub}/ — excluzand judetele (detectate din
     facet-ul `county_name`).

value-ul stocat e slug de path: main = "electronice", sub = "electronice/telefoane-mobile"
(format identic cu OLX). Scraper-ul il foloseste ca /anunturi/{value}/?q=...

Output: raport + blocul `"publi24": [...]` gata de copiat in
`app/services/radar/categories.py`. Standalone — nu se importa in app.
"""
import re
import sys
import time
from collections import OrderedDict
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from app.services.radar.base_scraper import build_headers

_IMPERSONATE = "chrome110"
_BASE = "https://www.publi24.ro"

# Fallback de judete (daca facet-ul lipseste pe vreo pagina). Detectam si dinamic.
_COUNTY_FALLBACK = {
    "alba", "arad", "arges", "bacau", "bihor", "bistrita-nasaud", "botosani", "braila",
    "brasov", "bucuresti", "buzau", "calarasi", "caras-severin", "cluj", "constanta",
    "covasna", "dambovita", "dolj", "galati", "giurgiu", "gorj", "harghita", "hunedoara",
    "ialomita", "iasi", "ilfov", "maramures", "mehedinti", "mures", "neamt", "olt",
    "prahova", "salaj", "satu-mare", "sibiu", "suceava", "teleorman", "timis", "tulcea",
    "valcea", "vaslui", "vrancea",
}


def _get(url: str) -> BeautifulSoup | None:
    resp = curl_requests.get(url, headers=build_headers({"Referer": _BASE + "/"}),
                             impersonate=_IMPERSONATE, timeout=25)
    if resp.status_code != 200:
        print(f"[Publi24CategoryMapper] HTTP {resp.status_code} pentru {url}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


def _clean(text: str) -> str:
    return re.sub(r"\s*\(\s*[\d.]+\s*\)\s*$", "", (text or "").strip()).strip()


def _detect_counties(soup: BeautifulSoup) -> set:
    counties = set()
    for inp in soup.select('[data-key="county_name"], [data-faceted*="county"]'):
        ul = inp.find_next("ul")
        if ul:
            for li in ul.select("li[data-slug]"):
                counties.add(li["data-slug"])
    return counties or set(_COUNTY_FALLBACK)


def _discover_mains(soup: BeautifulSoup) -> "OrderedDict[str, str]":
    """Categorii principale = link-uri /anunturi/{slug}/ care NU sunt judete."""
    counties = _detect_counties(soup) | set(_COUNTY_FALLBACK)
    mains: "OrderedDict[str, str]" = OrderedDict()
    for a in soup.select('a[href*="/anunturi/"]'):
        href = a.get("href", "").split("?")[0]
        m = re.match(r'(?:https://www\.publi24\.ro)?/anunturi/([a-z0-9-]+)/$', href)
        if not m:
            continue
        slug = m.group(1)
        label = _clean(a.get_text(" ", strip=True))
        if slug in counties or not label or len(label) > 40:
            continue
        mains.setdefault(slug, label)
    return mains


def _subcategories(main_slug: str) -> list:
    soup = _get(f"{_BASE}/anunturi/{main_slug}/")
    if not soup:
        return []
    counties = _detect_counties(soup) | set(_COUNTY_FALLBACK)
    subs = OrderedDict()
    pat = re.compile(rf'(?:https://www\.publi24\.ro)?/anunturi/{re.escape(main_slug)}/([a-z0-9-]+)/$')
    for a in soup.select(f'a[href*="/anunturi/{main_slug}/"]'):
        href = a.get("href", "").split("?")[0]
        m = pat.match(href)
        if not m:
            continue
        sub = m.group(1)
        if sub in counties:
            continue
        label = _clean(a.get_text(" ", strip=True))
        if label and sub not in subs:
            subs[sub] = label
    return [{"label": lbl, "value": f"{main_slug}/{sub}"} for sub, lbl in subs.items()]


def main() -> int:
    home = _get(_BASE + "/")
    if not home:
        print("EROARE: nu am putut obtine homepage-ul Publi24.")
        return 1
    mains = _discover_mains(home)
    if not mains:
        print("EROARE: nu am gasit categorii principale.")
        return 1
    print(f"[Publi24CategoryMapper] {len(mains)} categorii principale\n")

    platform_cats = []
    total_subs = 0
    for slug, label in mains.items():
        subs = _subcategories(slug)
        total_subs += len(subs)
        platform_cats.append({"label": label, "value": slug, "subcategories": subs})
        print(f"[MAP] {label:<24} ({slug}) — {len(subs)} subcategorii :: {[s['value'].split('/')[-1] for s in subs][:5]}")
        time.sleep(0.8)

    print(f"\nAcoperire: {len(platform_cats)} categorii principale · {total_subs} subcategorii totale")

    print("\n" + "=" * 78)
    print(f"    # Generat automat — map_publi24_categories.py — {date.today().isoformat()}")
    print(f"    # {len(platform_cats)} categorii principale · {total_subs} subcategorii (pagini live /anunturi/)")
    print("    # URL scraper: https://www.publi24.ro/anunturi/{value}/?q={keyword}")
    print('    "publi24": [')
    for c in platform_cats:
        print("        {")
        print(f'            "label": {_pyrepr(c["label"])},')
        print(f'            "value": {_pyrepr(c["value"])},')
        print('            "subcategories": [')
        for s in c["subcategories"]:
            print(f'                {{"label": {_pyrepr(s["label"])}, "value": {_pyrepr(s["value"])}}},')
        print("            ],")
        print("        },")
    print("    ],")
    return 0


def _pyrepr(s: str) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
