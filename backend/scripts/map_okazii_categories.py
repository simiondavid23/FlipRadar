"""Script de mapare categorii Okazii -> PLATFORM_CATEGORIES["okazii"].

Rulare (din backend/, cu venv):
    python -m scripts.map_okazii_categories

Strategie: pagina /catalog/ expune INTREGUL arbore, server-side randat. Structura:
  - departament  (<h2> intr-un .category-section)  — grupare, fara slug propriu
  - categorie    (<h3><a href="/{slug}/">)          — slug de 1 segment (ex. telefoane-mobile-si-smartphones)
  - subcategorie (<h4>, in <ul>)                     — prea granular, ignorat (recomandare 2 nivele)

Slug-urile de categorie (h3) sunt confirmate ca functionand ca rafinare de cautare:
`/cautare/{keyword}/{slug}.html`. Departamentele nu au slug propriu -> value=None
(grupare, ca intrarile "Diverse" existente); subcategoriile poarta slug-ul real.

Output: raport + blocul `"okazii": [...]` gata de copiat in
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
_CATALOG_URL = "https://www.okazii.ro/catalog/"


def _single_segment_slug(href: str) -> str | None:
    """Extrage slug-ul daca URL-ul e o categorie de 1 segment (/{slug}/), altfel None."""
    if not href:
        return None
    slug = href.split("?")[0].rstrip("/").split("okazii.ro/")[-1].strip("/")
    if slug and "/" not in slug:
        return slug
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s*\(\s*[\d.]+\s*\)\s*$", "", (text or "").strip()).strip()


def _fetch_catalog():
    resp = curl_requests.get(_CATALOG_URL, headers=build_headers({"Referer": "https://www.okazii.ro/"}),
                             impersonate=_IMPERSONATE, timeout=25)
    if resp.status_code != 200:
        print(f"[OkaziiCategoryMapper] HTTP {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    departments = []
    for section in soup.select(".category-section"):
        h2 = section.find("h2")
        dept_label = _clean(h2.get_text(strip=True)) if h2 else None
        if not dept_label:
            continue
        subs = []
        seen = set()
        for h3a in section.select("h3 a[href]"):
            slug = _single_segment_slug(h3a.get("href", ""))
            label = _clean(h3a.get_text(" ", strip=True))
            if slug and label and slug not in seen:
                seen.add(slug)
                subs.append({"label": label, "value": slug})
        if subs:
            departments.append({"label": dept_label, "value": None, "subcategories": subs})
    return departments


def main() -> int:
    departments = _fetch_catalog()
    if not departments:
        print("EROARE: nu am putut obtine arborele de categorii Okazii.")
        return 1
    total_subs = sum(len(d["subcategories"]) for d in departments)
    print(f"[OkaziiCategoryMapper] {len(departments)} departamente, {total_subs} categorii\n")
    for d in departments:
        print(f"[MAP] {d['label']:<34} — {len(d['subcategories'])} categorii :: "
              f"{[s['value'] for s in d['subcategories']][:4]}")

    print(f"\nAcoperire: {len(departments)} departamente · {total_subs} categorii totale")

    print("\n" + "=" * 78)
    print(f"    # Generat automat — map_okazii_categories.py — {date.today().isoformat()}")
    print(f"    # {len(departments)} departamente · {total_subs} categorii (arbore live /catalog/)")
    print("    # URL scraper: https://www.okazii.ro/cautare/{keyword}/{value}.html")
    print('    "okazii": [')
    for d in departments:
        print("        {")
        print(f'            "label": {_pyrepr(d["label"])},')
        print('            "value": None,')
        print('            "subcategories": [')
        for s in d["subcategories"]:
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
