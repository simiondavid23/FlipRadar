"""Script de mapare categorii LaJumate -> PLATFORM_CATEGORIES["lajumate"].

Rulare (din backend/, cu venv):
    python -m scripts.map_lajumate_categories

Strategie: LaJumate expune INTREGUL arbore de categorii, server-side randat, in
pagina "harta categorii" (https://lajumate.ro/landing-page/harta-categorii) — toate
link-urile /anunturi/{principala} si /anunturi/{principala}/{subcategorie}. Sursa e
completa (14 principale + ~180 subcategorii, inclusiv Telefoane), spre deosebire de
`desktopCategoriesServer` din SSR care e doar un set curat de scurtaturi.

Construim structura 2-nivel (principala + subcategorie), ca la OLX. Slug-ul de
subcategorie e "principala/subcategorie", folosit direct de scraper ca /anunturi/{slug}.

Output: raport + blocul `"lajumate": [...]` gata de copiat in
`app/services/radar/categories.py`. Standalone — nu se importa in app.
"""
import re
import sys
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
_MAP_URL = "https://lajumate.ro/landing-page/harta-categorii"


def _clean_label(text: str) -> str:
    """Anchor text vine cu numarul de anunturi in coada: 'Telefoane ( 299 )'."""
    return re.sub(r"\s*\(\s*[\d.]+\s*\)\s*$", "", (text or "").strip()).strip()


def _fetch_tree() -> tuple[dict, dict]:
    """Returneaza (mains {slug: label}, subs {main_slug: [(sub_slug_full, label)]})."""
    resp = curl_requests.get(_MAP_URL, headers=build_headers({"Referer": "https://lajumate.ro/"}),
                             impersonate=_IMPERSONATE, timeout=25)
    if resp.status_code != 200:
        print(f"[LajumateCategoryMapper] HTTP {resp.status_code}")
        return {}, {}
    soup = BeautifulSoup(resp.text, "html.parser")
    mains: dict[str, str] = {}
    subs: dict[str, list] = {}
    for a in soup.select('a[href^="/anunturi/"]'):
        href = a.get("href", "").split("?")[0].rstrip("/")
        tail = href.split("/anunturi/", 1)[-1]
        parts = tail.split("/")
        label = _clean_label(a.get_text(" ", strip=True))
        if not label:
            continue
        if len(parts) == 1 and parts[0]:
            mains.setdefault(parts[0], label)
        elif len(parts) == 2 and parts[0] and parts[1]:
            subs.setdefault(parts[0], [])
            if tail not in [s for s, _ in subs[parts[0]]]:
                subs[parts[0]].append((tail, label))
    return mains, subs


def main() -> int:
    mains, subs = _fetch_tree()
    if not mains:
        print("EROARE: nu am putut obtine arborele de categorii LaJumate.")
        return 1
    print(f"[LajumateCategoryMapper] {len(mains)} categorii principale, "
          f"{sum(len(v) for v in subs.values())} subcategorii\n")

    platform_cats = []
    total_subs = 0
    for main_slug, main_label in mains.items():
        sub_entries = [{"label": lbl, "value": slug} for slug, lbl in subs.get(main_slug, [])]
        total_subs += len(sub_entries)
        platform_cats.append({"label": main_label, "value": main_slug, "subcategories": sub_entries})
        print(f"[MAP] {main_label:<48} ({main_slug}) — {len(sub_entries)} subcategorii")

    print(f"\nAcoperire: {len(platform_cats)} categorii principale · {total_subs} subcategorii totale")

    print("\n" + "=" * 78)
    print(f"    # Generat automat — map_lajumate_categories.py — {date.today().isoformat()}")
    print(f"    # {len(platform_cats)} categorii principale · {total_subs} subcategorii (arbore live LaJumate)")
    print("    # URL scraper (fallback pe categorie): https://lajumate.ro/anunturi/{value}")
    print('    "lajumate": [')
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
    """repr cu ghilimele duble, pastrand diacriticele (ca sursa existenta)."""
    import json
    return json.dumps(s, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
