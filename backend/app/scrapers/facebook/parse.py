"""Normalizatorul UNIC al anunturilor Facebook — SSR si GraphQL, aceeasi iesire.

Nucleul logat-out (FB-1). Functiile de mai jos sunt MUTATE IDENTIC din
app/services/radar/facebook_scraper.py (cut-paste, cu docstring cu tot), doar
redenumite fara underscore-ul de privat:

    _SCRIPT_JSON_RE -> SCRIPT_JSON_RE      _parse_price     -> parse_price
    _iter_listing_objects -> iter_listing_objects           _parse_location  -> parse_location
    _looks_like_login_wall -> looks_like_login_wall         _is_active       -> is_active
    _deep_first -> deep_first                               _collect_key     -> collect_key

Originalele RAMAN pe loc in radar/facebook_scraper.py: consumatorii (Radar, Auto,
Imobiliare) importa de acolo pana la FB-5. Duplicarea e temporara si deliberata —
altfel nu se poate distinge o regresie de MUTARE de una de LOGICA.

`looks_like_login_wall` sta aici (nu in client.py) fiindca e analiza de HTML, ca
tot restul fisierului; clientul doar o apeleaza.

Singura logica proprie a fisierului e `canonic()`: forma canonica a unui anunt,
identica indiferent daca obiectul brut vine din SSR sau din GraphQL. Nu contine
NIMIC specific unui consumator (fara filtre de pret, categorie, an, model).
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

# Helper pur (fara dependinte) — nu poate crea ciclu de import. Vezi R1 in parse_price.
from app.utils.number_format import parse_number

BASE = "https://www.facebook.com"
SCRIPT_JSON_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.DOTALL
)


def iter_listing_objects(html: str) -> list[dict]:
    """Extrage toate <script type=application/json>, json.loads pe fiecare (skip la
    eroare) și walk recursiv după orice dict cu AMBELE chei
    'marketplace_listing_title' și 'id'."""
    found: list[dict] = []

    def walk(obj):
        if isinstance(obj, dict):
            if "marketplace_listing_title" in obj and "id" in obj:
                found.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for block in SCRIPT_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        walk(data)
    return found


def walk_listing_objects(obj) -> list[dict]:
    """Acelasi walk ca `iter_listing_objects`, dar pe un obiect DEJA parsat (raspunsul
    GraphQL), nu pe HTML. Traseul explicit prin `edges` se foloseste doar pentru
    cursor si page_info — anunturile se iau structural, ca sa nu depindem de forma
    exacta a raspunsului (suprafata logat-out se misca activ)."""
    found: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            if "marketplace_listing_title" in o and "id" in o:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return found


# R3 / FBM-1e — markerii formularului de login serviti IN pagina. Facebook raspunde
# frecvent 200 pe URL-ul ORIGINAL, cu formularul de login in corp si FARA redirect,
# deci verificarea pe final_url nu-l prinde.
_LOGIN_EMAIL_RE = re.compile(r"""name\s*=\s*(?:"email"|'email'|email\b)""", re.IGNORECASE)
_LOGIN_PASS_RE = re.compile(r"""name\s*=\s*(?:"pass"|'pass'|pass\b)""", re.IGNORECASE)
_LOGIN_ACTION_RE = re.compile(r"""<form[^>]*\baction\s*=\s*['"]?[^'">\s]*/login""",
                              re.IGNORECASE)


def looks_like_login_wall(html) -> bool:
    """True daca html-ul poarta markerii formularului de login Facebook.

    Cel putin unul: id-ul `royal_login_form`, perechea name="email" + name="pass" pe
    acelasi document, sau un <form> al carui action contine "/login". Tolerant la
    ghilimele simple/duble si la majuscule. Pe o pagina normala de marketplace: False.
    """
    if not html:
        return False
    low = str(html).lower()
    if "royal_login_form" in low:
        return True
    if _LOGIN_EMAIL_RE.search(low) and _LOGIN_PASS_RE.search(low):
        return True
    return bool(_LOGIN_ACTION_RE.search(low))


def deep_first(obj, key: str, _depth: int = 0):
    """Prima valoare scalară pentru `key` oriunde în obiect (creation_time e imbricat
    în if_gk_just_listed_tag_on_search_feed, nu la nivelul de sus)."""
    if _depth > 6:
        return None
    if isinstance(obj, dict):
        if key in obj and not isinstance(obj[key], (dict, list)):
            return obj[key]
        for v in obj.values():
            r = deep_first(v, key, _depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = deep_first(v, key, _depth + 1)
            if r is not None:
                return r
    return None


def parse_price(obj: dict) -> tuple[Optional[float], str]:
    """Prioritate listing_price.amount (float); fallback regex pe formatted_amount
    ('RON800' -> 800.0/RON, '€800' -> 800.0/EUR).

    R1 (audit FB): fallback-ul facea un replace orb `.replace(".","").replace(",",".")`,
    deci "RON1,500" -> 1.5 si "€1,234.56" -> 1.23 — de 1000x mai mic, TACUT si in gama
    care trece de filtrele de pret. Formatul EN cu virgula de mii e frecvent pe
    Marketplace. Regula corecta e in app/utils/number_format.parse_number (aceeasi
    deja dovedita pe Imobiliare). Modulul Auto primeste fixul automat: facebook_auto_scraper
    importa _parse_price de aici.
    """
    lp = obj.get("listing_price") or {}
    fmt = lp.get("formatted_amount") or ""
    currency = "RON"
    if fmt:
        up = fmt.upper()
        if "€" in fmt or "EUR" in up:
            currency = "EUR"
        elif "$" in fmt or "USD" in up:
            currency = "USD"

    price = None
    amount = lp.get("amount")
    if amount not in (None, ""):
        try:
            price = float(amount)
        except (ValueError, TypeError):
            price = None
    if price is None and fmt:
        m = re.search(r"[\d.,]+", fmt)
        if m:
            price = parse_number(m.group(0))
    return price, currency


def parse_location(obj: dict) -> Optional[str]:
    rg = (obj.get("location") or {}).get("reverse_geocode") or {}
    city = rg.get("city")
    if city:
        return city
    return (rg.get("city_page") or {}).get("display_name")


def is_active(obj: dict) -> bool:
    """Exclude sold/not-live/pending/hidden — DOAR daca cheia e prezenta (lipsa cheii
    NU inseamna exclus)."""
    if obj.get("is_sold") is True:
        return False
    if obj.get("is_live") is False:
        return False
    if obj.get("is_pending") is True:
        return False
    if obj.get("is_hidden") is True:
        return False
    return True


def collect_key(root, key: str) -> list:
    """Toate valorile pentru cheia `key` oriunde in structura JSON (recursiv)."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key:
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(root)
    return found


def canonic(obj: dict) -> Optional[dict]:
    """Forma canonica a unui anunt brut, indiferent de sursa (SSR sau GraphQL).

    Intoarce None daca anuntul nu e activ sau daca ii lipseste `id`.

    `listed_at` e UTC AWARE, spre deosebire de `search_facebook` din radar, care
    foloseste `datetime.fromtimestamp(ct)` (local, naiv). Diferenta e deliberata si
    trebuie stiuta la cablarea din FB-5: un timestamp local pus intr-o coloana UTC
    e o eroare tacuta de cateva ore. Garda `> 1_000_000_000` e pastrata din original.

    `external_id` e id-ul BRUT, fara prefixul `fb_` pe care il pune radar-ul:
    prefixarea e treaba consumatorului, nu a normalizatorului.
    """
    if not isinstance(obj, dict):
        return None
    oid = obj.get("id")
    if oid in (None, ""):
        return None
    if not is_active(obj):
        return None

    price, currency = parse_price(obj)

    listed_at = None
    ct = deep_first(obj, "creation_time")
    if isinstance(ct, (int, float)) and ct > 1_000_000_000:
        try:
            listed_at = datetime.fromtimestamp(ct, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            listed_at = None

    image_url = deep_first(obj.get("primary_listing_photo") or {}, "uri")

    cat = deep_first(obj, "marketplace_listing_category_id")

    return {
        "external_id": str(oid),
        "title": obj.get("marketplace_listing_title"),
        "price": price,
        "currency": currency,
        "location": parse_location(obj),
        "image_url": image_url,
        "listed_at": listed_at,
        "category_id": str(cat) if cat not in (None, "") else None,
        "source_url": f"{BASE}/marketplace/item/{oid}/",
    }
