"""Script de mapare OLX category_id -> subcategorie FlipRadar.

Rulare (din backend/, cu venv):
    python -m scripts.map_olx_categories

Strategie: OLX expune INTREGUL arbore de categorii intr-un singur request, in
`window.__PRERENDERED_STATE__.categories.list` (dict {id: nod} cu name/parentId/
children). Ad-urile din search poarta ID-uri de FRUNZA (ex. 948 = iPhone), deci
fiecare subcategorie FlipRadar se mapeaza la nodul OLX corespunzator SI la tot
subarborele lui. Un singur request, toate ID-urile.

Output: afiseaza raportul de mapare + dict-ul complet `OLX_CATEGORY_ID_TO_SUBCATEGORY`
gata de copiat in `app/utils/radar_scanner.py`. Standalone — nu se importa in app.
"""
import json
import re
import sys
from collections import Counter
from datetime import date

# Consola Windows (cp1252) nu poate afisa diacritice/emoji — fortam UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from curl_cffi import requests as curl_requests
from app.services.radar.base_scraper import build_headers

_IMPERSONATE = "chrome110"


# FlipRadar main category -> slug-ul OLX (normalizedName al nodului top-level).
# Corespunde cu OLX_CATEGORY_SLUGS din olx_scraper.py.
MAIN_SLUGS = {
    "electronice-si-electrocasnice": "electronice-si-electrocasnice",
    "moda-si-frumusete": "moda-frumusete",
    "piese-auto-moto-si-ambarcatiuni": "piese-auto",
    "casa-si-gradina": "casa-gradina",
    "mama-si-copilul": "mama-si-copilul",
    "sport-timp-liber-si-arta": "hobby-sport-turism",
    "animale-de-companie": "animale-de-companie",
    "agro-si-industrie": "anunturi-agricole",
    "servicii": "servicii-afaceri-colaborari",
    "echipamente-profesionale-si-vanzare-companii": "firme-echipamente-profesionale",
    "cazare-turism": "cazare-turism",
    "inchiriere-bunuri-si-vehicule": "inchiriere-vehicule-echipamente-articole",
}

# (main_cat_slug, subcategorie_flipradar, olx_sub_slug estimativ)
SUBCATEGORIES_TO_MAP = [
    ("electronice-si-electrocasnice", "Telefoane", "telefoane-mobile"),
    ("electronice-si-electrocasnice", "Electrocasnice", "electrocasnice"),
    ("electronice-si-electrocasnice", "Tablete - eReadere", "tablete-ereadere"),
    ("electronice-si-electrocasnice", "TV", "televizoare"),
    ("electronice-si-electrocasnice", "Videoproiectoare & Accesorii", "videoproiectoare-accesorii"),
    ("electronice-si-electrocasnice", "Retelistica & Servere", "retelistica-servere"),
    ("electronice-si-electrocasnice", "Piese telefoane & tablete", "piese-telefoane-tablete"),
    ("electronice-si-electrocasnice", "Laptop-Calculator-Gaming", "calculatoare-laptop-accesorii"),
    ("electronice-si-electrocasnice", "Ingrijire Personala", "ingrijire-personala"),
    ("electronice-si-electrocasnice", "Periferice & Accesorii Laptop-PC-Gaming", "periferice-accesorii"),
    ("electronice-si-electrocasnice", "Imprimante, scannere", "imprimante-scannere"),
    ("electronice-si-electrocasnice", "Home Cinema & Audio", "audio-hi-fi"),
    ("electronice-si-electrocasnice", "Gadgets, Wearables & Camere foto-video", "gadgets-wearables"),
    ("electronice-si-electrocasnice", "Drone & accesorii", "drone-accesorii"),
    ("electronice-si-electrocasnice", "Componente Laptop-PC", "componente-accesorii-pc"),
    ("electronice-si-electrocasnice", "Casti Audio", "casti-audio"),
    ("electronice-si-electrocasnice", "Casa inteligenta - Smarthome", "casa-smart"),
    ("electronice-si-electrocasnice", "Audio Hi Fi & Profesionale", "audio-hi-fi-profesional"),
    ("electronice-si-electrocasnice", "Aparate medicale & Wellness", "aparate-medicale"),
    ("electronice-si-electrocasnice", "Accesorii telefoane & tablete", "accesorii-telefoane-si-tablete"),
    ("moda-si-frumusete", "Haine dama", "haine-dama"),
    ("moda-si-frumusete", "Incaltaminte dama", "incaltaminte-dama"),
    ("moda-si-frumusete", "Incaltaminte barbati", "incaltaminte-barbati"),
    ("moda-si-frumusete", "Haine barbati", "haine-barbati"),
    ("moda-si-frumusete", "Accesorii", "accesorii-moda"),
    ("moda-si-frumusete", "Ceasuri", "ceasuri"),
    ("moda-si-frumusete", "Lenjerie si costume de baie dama", "lenjerie-costume-baie"),
    ("moda-si-frumusete", "Haine pentru gravide", "haine-gravide"),
    ("moda-si-frumusete", "Lenjerie si costume de inot barbati", "lenjerie-barbati"),
    ("moda-si-frumusete", "Palarii, sepci si bandane", "palarii-sepci"),
    ("moda-si-frumusete", "Haine pentru nunta", "haine-nunta"),
    ("moda-si-frumusete", "Sanatate si frumusete", "sanatate-frumusete"),
    ("moda-si-frumusete", "Alte accesorii de moda si frumusete", "alte-accesorii-moda"),
    ("moda-si-frumusete", "Cadouri", "cadouri"),
    ("piese-auto-moto-si-ambarcatiuni", "Roti - Jante - Anvelope", "anvelope-jante-roti"),
    ("piese-auto-moto-si-ambarcatiuni", "Consumabile - accesorii", "consumabile-accesorii-auto"),
    ("piese-auto-moto-si-ambarcatiuni", "Caroserie - Interior", "caroserie-interior"),
    ("piese-auto-moto-si-ambarcatiuni", "Mecanica - electrica", "mecanica-electrica"),
    ("piese-auto-moto-si-ambarcatiuni", "Alte piese", "alte-piese-auto"),
    ("piese-auto-moto-si-ambarcatiuni", "Alte Vehicule", "alte-vehicule"),
    ("piese-auto-moto-si-ambarcatiuni", "Vehicule pentru dezmembrare", "vehicule-dezmembrare"),
    ("casa-si-gradina", "Articole menaj", "articole-menaj"),
    ("casa-si-gradina", "Constructii", "constructii"),
    ("casa-si-gradina", "Decoratiuni pentru interior", "decoratiuni-interior"),
    ("casa-si-gradina", "Finisaj interior", "finisaj-interior"),
    ("casa-si-gradina", "Gradina", "gradina"),
    ("casa-si-gradina", "Hale metalice, structuri metalice si containere", "hale-metalice"),
    ("casa-si-gradina", "Iluminat", "iluminat"),
    ("casa-si-gradina", "Instalatii electrice", "instalatii-electrice"),
    ("casa-si-gradina", "Instalatii sanitare", "instalatii-sanitare"),
    ("casa-si-gradina", "Instalatii termice", "instalatii-termice"),
    ("casa-si-gradina", "Mobila", "mobila"),
    ("casa-si-gradina", "Scule, unelte, feronerie", "scule-unelte-feronerie"),
    ("mama-si-copilul", "Haine - Incaltaminte copii si gravide", "haine-incaltaminte-copii"),
    ("mama-si-copilul", "La plimbare", "carucioare-accesorii"),
    ("mama-si-copilul", "Jocuri - Jucarii", "jocuri-jucarii"),
    ("mama-si-copilul", "Camera copilului", "camera-copilului"),
    ("mama-si-copilul", "Alimentatie - Ingrijire", "alimentatie-ingrijire"),
    ("mama-si-copilul", "Articole scolare - papetarie", "articole-scolare"),
    ("mama-si-copilul", "Alte produse copii", "alte-produse-copii"),
    ("sport-timp-liber-si-arta", "Biciclete - Fitness - Suplimente", "biciclete-fitness"),
    ("sport-timp-liber-si-arta", "Camping", "camping-outdoor"),
    ("sport-timp-liber-si-arta", "Pescuit", "pescuit"),
    ("sport-timp-liber-si-arta", "Fotbal", "fotbal"),
    ("sport-timp-liber-si-arta", "Tenis", "tenis"),
    ("sport-timp-liber-si-arta", "Sporturi de apa", "sporturi-apa"),
    ("sport-timp-liber-si-arta", "Sporturi de iarna", "sporturi-iarna"),
    ("sport-timp-liber-si-arta", "Trotinete, role, skateboard", "trotinete-role"),
    ("sport-timp-liber-si-arta", "Vanatoare", "vanatoare"),
    ("sport-timp-liber-si-arta", "Arta - Obiecte de colectie", "arta-obiecte-colectie"),
    ("sport-timp-liber-si-arta", "Carti - Muzica - Filme", "carti-muzica-filme"),
    ("animale-de-companie", "Caini", "caini"),
    ("animale-de-companie", "Pisici", "pisici"),
    ("animale-de-companie", "Mancare si gustari pentru animale de companie", "mancare-animale"),
    ("animale-de-companie", "Accesorii pentru animale de companie", "accesorii-animale"),
    ("animale-de-companie", "Adoptii", "adoptii"),
    ("animale-de-companie", "Alte animale de companie", "alte-animale"),
    ("agro-si-industrie", "Utilaje agricole si industriale", "utilaje-agricole"),
    ("agro-si-industrie", "Produse piata - alimentatie", "produse-alimentare"),
    ("agro-si-industrie", "Cereale - plante - pomi", "cereale-plante"),
    ("agro-si-industrie", "Animale domestice si pasari", "animale-domestice"),
    ("echipamente-profesionale-si-vanzare-companii", "Echipamente pentru magazine si birouri", "echipamente-magazine"),
    ("echipamente-profesionale-si-vanzare-companii", "Horeca", "horeca"),
    ("echipamente-profesionale-si-vanzare-companii", "Alte echipamente profesionale", "alte-echipamente-prof"),
]


def _strip(s: str) -> str:
    return (s or "").lower().strip().replace("ă", "a").replace("â", "a").replace("î", "i") \
        .replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t") \
        .replace(" & ", " ").replace("&", " ").replace("-", " ").replace(",", " ")


def _fetch_olx_category_tree() -> dict:
    """Extrage {id:int -> nod} din __PRERENDERED_STATE__.categories.list (homepage OLX).
    Un singur request. Returneaza {} la orice esec."""
    try:
        resp = curl_requests.get(
            "https://www.olx.ro/",
            headers=build_headers({"Referer": "https://www.olx.ro/"}),
            impersonate=_IMPERSONATE,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[OlxCategoryMapper] homepage HTTP {resp.status_code}")
            return {}
        m = re.search(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', resp.text, re.DOTALL)
        if not m:
            print("[OlxCategoryMapper] __PRERENDERED_STATE__ absent")
            return {}
        state = json.loads(json.loads(m.group(1)))
        raw = (state.get("categories") or {}).get("list") or {}
        return {int(k): v for k, v in raw.items()}
    except Exception as e:
        print(f"[OlxCategoryMapper] eroare fetch arbore: {e}")
        return {}


def main() -> int:
    nodes = _fetch_olx_category_tree()
    if not nodes:
        print("EROARE: nu am putut obtine arborele de categorii OLX.")
        return 1
    print(f"[OlxCategoryMapper] arbore incarcat: {len(nodes)} noduri\n")

    def name(i): return (nodes.get(i) or {}).get("name")
    def norm(i): return (nodes.get(i) or {}).get("normalizedName")

    def descendants(root: int) -> set:
        out, stack = {root}, [root]
        while stack:
            n = stack.pop()
            for c in (nodes.get(n, {}).get("children") or []):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out

    # main slug -> id top-level (dupa normalizedName)
    main_id = {}
    for fr_main, olx_main_slug in MAIN_SLUGS.items():
        hit = next((i for i, nd in nodes.items() if nd.get("normalizedName") == olx_main_slug and not nd.get("parentId")), None)
        main_id[fr_main] = hit

    def resolve_sub(main_slug: str, fr_name: str, olx_slug: str):
        """Gaseste nodul OLX pentru subcategoria FlipRadar in subarborele main."""
        mid = main_id.get(main_slug)
        if not mid:
            return None, "main lipsa"
        sub_ids = descendants(mid) - {mid}
        # 1) normalizedName == olx_slug
        for i in sub_ids:
            if norm(i) == olx_slug:
                return i, "slug"
        # 2) name accent-normalizat == fr_name
        t = _strip(fr_name)
        for i in sub_ids:
            if _strip(name(i)) == t:
                return i, "name"
        # 3) match pe tokeni (toti tokenii fr in numele OLX, doar copii directi)
        direct = nodes.get(mid, {}).get("children") or []
        ftoks = set(_strip(fr_name).split())
        best = None
        for i in direct:
            ntoks = set(_strip(name(i)).split())
            if ftoks and ftoks <= ntoks:
                best = i; break
        if best:
            return best, "tokens"
        return None, "nerezolvat"

    mapping = {}          # id(str) -> fr_name
    report = []           # (fr_name, anchor_id, n_ids, status)
    slug_map = {}         # normalizedName al nodului-ancora -> fr_name (pt. keyword-uri slug)
    unresolved = []
    for main_slug, fr_name, olx_slug in SUBCATEGORIES_TO_MAP:
        anchor, how = resolve_sub(main_slug, fr_name, olx_slug)
        if not anchor:
            unresolved.append((fr_name, main_slug, olx_slug))
            report.append((fr_name, None, 0, how))
            print(f"[MAP] {main_slug} > {fr_name:<45} → NEREZOLVAT ({how}) ⚠")
            continue
        subtree = descendants(anchor)
        for i in subtree:
            mapping[str(i)] = fr_name
        anchor_slug = norm(anchor)
        if anchor_slug:
            slug_map[anchor_slug] = fr_name
        report.append((fr_name, anchor, len(subtree), how))
        print(f"[MAP] {fr_name:<45} → nod OLX {anchor} '{name(anchor)}' ({len(subtree)} id-uri, via {how}) ✅")

    # verificare coerenta: 948 (iPhone) -> Telefoane
    print("\n=== Verificare coerenta ===")
    print(f"  id 948 ('{name(948)}') -> {mapping.get('948')!r} (asteptat: 'Telefoane')")
    print(f"  id 2239 ('{name(2239)}') -> {mapping.get('2239')!r} (asteptat: 'Accesorii telefoane & tablete')")

    ok = sum(1 for _, a, _, _ in report if a)
    print(f"\nAcoperire: {ok}/{len(SUBCATEGORIES_TO_MAP)} subcategorii mapate · {len(mapping)} ID-uri totale")
    if unresolved:
        print("Nerezolvate:", [u[0] for u in unresolved])

    # dict final gata de copiat (chei string, ca listing['olx_category'])
    print("\n" + "=" * 70)
    print("# Generat automat — map_olx_categories.py — " + date.today().isoformat())
    print(f"# Acoperire: {ok}/{len(SUBCATEGORIES_TO_MAP)} subcategorii FlipRadar · {len(mapping)} ID-uri OLX")
    print("OLX_CATEGORY_ID_TO_SUBCATEGORY = {")
    for k in sorted(mapping, key=lambda x: int(x)):
        print(f'    "{k}": {json.dumps(mapping[k], ensure_ascii=False)},')
    print("}")

    # Map secundar: slug OLX de subcategorie (normalizedName al nodului-ancora) ->
    # numele FlipRadar. Folosit ca sa activam filtrul pt. keyword-urile care stocheaza
    # categoria ca slug (ex. "electronice-si-electrocasnice/telefoane-mobile") in loc
    # de a avea subcategoria in marketplace_config.
    print("\n# Generat automat — map_olx_categories.py — " + date.today().isoformat())
    print(f"# Slug subcategorie OLX -> subcategorie FlipRadar ({len(slug_map)} intrari)")
    print("OLX_SUBCATEGORY_SLUG_TO_NAME = {")
    for k in sorted(slug_map):
        print(f'    {json.dumps(k, ensure_ascii=False)}: {json.dumps(slug_map[k], ensure_ascii=False)},')
    print("}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
