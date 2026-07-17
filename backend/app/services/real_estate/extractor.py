"""
Extracts structured data from free-text real estate listings.
Strategy: regex first, Groq LLM fallback for missing critical fields.
"""
import re
from typing import Optional

# Numarul de pret: cifre cu separatori de mii . sau , dar FARA spatii interne
# (spatiile lasau regex-ul sa inghita un numar anterior, ex. "etaj 4, 550" -> 4.55).
_PRICE_PATTERNS = [
    r"(\d[\d.,]*\d|\d)\s*(?:eur|euro|€)(?:/lun[aă]?)?",
    r"(\d[\d.,]*\d|\d)\s*(?:ron|lei|RON)(?:/lun[aă]?)?",
    r"preț?\s*:?\s*(\d[\d.,]*\d|\d)\s*(?:eur|ron|lei|€)",
    r"chirie\s*:?\s*(\d[\d.,]*\d|\d)",
]

_ROOMS_PATTERNS = [
    r"(\d)\s*camere?",
    r"(\d)\s*cam\b",
    r"ap(?:artament)?\s*(\d)\s*cam",
    r"garsonier[aă]",
    r"studio",
]

_AREA_PATTERNS = [
    r"(\d{2,3})\s*mp",
    r"(\d{2,3})\s*m[²2]",
    r"suprafat[aă]\s*:?\s*(\d{2,3})",
    r"(\d{2,3})\s*metri\s*p[aă]trat",
]

_FLOOR_PATTERNS = [
    r"etaj\s*(\d{1,2})",
    r"etaj\s*(parter|mansard[aă]|ultim)",
    r"(\d{1,2})/(\d{1,2})\s*etaje?",
]

_FURNISHED_POSITIVE = ["mobilat", "utilat", "complet mobilat", "mobilata",
                        "cu mobilier", "furnished"]
_FURNISHED_NEGATIVE = ["nemobilat", "gol", "fara mobila", "unfurnished"]


def _clean_number(text: str) -> Optional[float]:
    try:
        cleaned = re.sub(r"[\s\.]", "", text).replace(",", ".")
        return float(cleaned)
    except Exception:
        return None


def extract_price(text: str) -> tuple:
    t = text.lower()
    for pattern in _PRICE_PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1))
            if val and 50 < val < 50000:
                currency = "EUR" if any(
                    x in m.group(0) for x in ["eur", "euro", "€"]) else "RON"
                return val, currency
    return None, None


def extract_rooms(text: str) -> Optional[int]:
    t = text.lower()
    if re.search(r"garsonier[aă]|studio", t):
        return 1
    for pattern in _ROOMS_PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if m and m.lastindex and m.group(1).isdigit():
            rooms = int(m.group(1))
            if 1 <= rooms <= 8:
                return rooms
    return None


def extract_area(text: str) -> Optional[int]:
    for pattern in _AREA_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _clean_number(m.group(1))
            if val and 15 <= val <= 500:
                return int(val)
    return None


def extract_floor(text: str) -> Optional[str]:
    t = text.lower()
    m = re.search(r"etaj\s*(parter|\d{1,2}|mansard[aă]|ultim)", t)
    if m:
        return m.group(1)
    m2 = re.search(r"\betaj\b.*?(\d{1,2})\s*/\s*(\d{1,2})", t)
    if m2:
        return f"{m2.group(1)}/{m2.group(2)}"
    return None


def extract_furnished(text: str) -> Optional[bool]:
    t = text.lower()
    if any(w in t for w in _FURNISHED_POSITIVE):
        return True
    if any(w in t for w in _FURNISHED_NEGATIVE):
        return False
    return None


def extract_all(text: str) -> dict:
    price, currency = extract_price(text)
    rooms = extract_rooms(text)
    area = extract_area(text)
    floor = extract_floor(text)
    furnished = extract_furnished(text)
    return {
        "price": price,
        "currency": currency or "EUR",
        "rooms": rooms,
        "area_sqm": area,
        "floor": floor,
        "furnished": furnished,
        "price_per_sqm": (
            round(price / area, 2)
            if price and area and area > 0 else None
        ),
    }


def groq_extract(text: str, existing: dict,
                 ai_client=None, model: str = None) -> dict:
    """
    Fallback la LLM (client OpenAI-compatibil per user — PKG-2) cand regex-ul
    rateaza campuri critice. Apelat doar cand price SAU rooms lipsesc.
    ai_client=None (AI dezactivat / neconfigurat) -> intoarce `existing` neschimbat.
    """
    if ai_client is None:
        return existing
    if existing.get("price") and existing.get("rooms"):
        return existing  # regex got what we need

    try:
        import json
        prompt = (
            "Extrage din textul următor: pret (număr), moneda (EUR/RON), "
            "camere (număr întreg sau 1 pentru garsonieră/studio), "
            "suprafata_mp (număr), etaj (text), zona (string). "
            "Răspunde DOAR cu JSON valid, fără explicații. "
            "Dacă nu găsești un câmp, folosește null.\n"
            f"Text: {text[:800]}"
        )
        resp = ai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        result = existing.copy()
        if not result.get("price") and parsed.get("pret"):
            result["price"] = float(parsed["pret"])
            result["currency"] = parsed.get("moneda", "EUR")
        if not result.get("rooms") and parsed.get("camere"):
            result["rooms"] = int(parsed["camere"])
        if not result.get("area_sqm") and parsed.get("suprafata_mp"):
            result["area_sqm"] = int(parsed["suprafata_mp"])
        if not result.get("floor") and parsed.get("etaj"):
            result["floor"] = str(parsed["etaj"])
        if not result.get("zone_raw") and parsed.get("zona"):
            result["zone_raw"] = parsed["zona"]
        if result.get("price") and result.get("area_sqm"):
            result["price_per_sqm"] = round(
                result["price"] / result["area_sqm"], 2)
        return result
    except Exception as exc:
        print(f"[Extractor] AI fallback error: {exc}")
        return existing


# ─────────────────────────────────────────────────────────────────────────────
# Extractor regex-only pentru postari FB Groups (pre-extractie in
# facebook_group_service). Logica DIFERITA de extract_all — unificarea reala
# necesita diagnostic separat, ramane TODO. Mutat aici din vechiul
# services/real_estate_extractor.py (REF-1), FARA schimbare de logica.
# `passes_keyword_filter` e helperul-companion din acelasi fisier vechi, folosit tot
# de facebook_group_service — mutat impreuna ca sa nu se rupa comportamentul.
# ─────────────────────────────────────────────────────────────────────────────


def extract_real_estate_data(text: str) -> dict:
    """
    Extrage date structurate dintr-o postare de grup Facebook imobiliare.
    Foloseste exclusiv regex — fara AI, fara Groq.
    Returneaza doar campurile gasite; campurile negasite lipsesc din dict.
    """
    lower = text.lower()
    result = {}

    # ── Preț ─────────────────────────────────────────────────────────
    price_patterns = [
        (r'(\d[\d\s\.]{1,8})\s*€',       "EUR"),
        (r'(\d[\d\s\.]{1,8})\s*euro\b',  "EUR"),
        (r'(\d[\d\s\.]{1,8})\s*eur\b',   "EUR"),
        (r'(\d[\d\s\.]{1,8})\s*ron\b',   "RON"),
        (r'(\d[\d\s\.]{1,8})\s*lei\b',   "RON"),
    ]
    for pattern, currency in price_patterns:
        m = re.search(pattern, lower)
        if m:
            raw = re.sub(r'[\s\.]', '', m.group(1))
            if raw.isdigit() and 50 <= int(raw) <= 5000000:
                result["pret"] = int(raw)
                result["moneda"] = currency
                break

    # ── Tip anunț ─────────────────────────────────────────────────────
    if re.search(r'\b(inchiriez|închiriez|inchiriere|închiriere|de inchiriat|chirie)\b', lower):
        result["tip_anunt"] = "inchiriere"
    elif re.search(r'\b(vand|vând|vanzare|vânzare|de vanzare|de vânzare)\b', lower):
        result["tip_anunt"] = "vanzare"

    # ── Tip proprietate ───────────────────────────────────────────────
    type_patterns = [
        (r'\bgarsonier[aă]\b',                  "garsoniera"),
        (r'\bstudio\b',                          "studio"),
        (r'\b1\s*camer[aă]\b',                  "1 camera"),
        (r'\bapartament\s*cu\s*1\b',             "1 camera"),
        (r'\b2\s*camere?\b',                     "2 camere"),
        (r'\bapartament\s*cu\s*2\b',             "2 camere"),
        (r'\b3\s*camere?\b',                     "3 camere"),
        (r'\bapartament\s*cu\s*3\b',             "3 camere"),
        (r'\b4\s*camere?\b',                     "4 camere"),
        (r'\bpentthouse\b|\bpenthouse\b',        "penthouse"),
        (r'\b(casa|casă|vila|vilă)\b',           "casa"),
        (r'\bduplex\b',                          "duplex"),
        (r'\bterasa\b|\bterasă\b',               "apartament cu terasa"),
    ]
    for pattern, label in type_patterns:
        if re.search(pattern, lower):
            result["tip_proprietate"] = label
            break

    # ── Suprafață ─────────────────────────────────────────────────────
    mp_patterns = [
        r'(\d{2,4})\s*mp\b',
        r'(\d{2,4})\s*m[²2]\b',
        r'(\d{2,4})\s*metri\s*p[aă]tra[tț]i',
        r'suprafat[aă]\s*(?:util[aă]\s*)?(?:de\s*)?(\d{2,4})',
    ]
    for pattern in mp_patterns:
        m = re.search(pattern, lower)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 1000:
                result["suprafata_mp"] = val
                break

    # ── Etaj ─────────────────────────────────────────────────────────
    if re.search(r'\bparter\b', lower):
        result["etaj"] = "parter"
    elif re.search(r'\bultimul\s*etaj\b|\bult\.\s*etaj\b', lower):
        result["etaj"] = "ultim etaj"
    elif re.search(r'\bmansard[aă]\b', lower):
        result["etaj"] = "mansarda"
    else:
        m = re.search(r'\betaj\s*([1-9][0-9]?)\b', lower)
        if m:
            result["etaj"] = f"etaj {m.group(1)}"

    # ── Sector / Zonă București ───────────────────────────────────────
    m = re.search(r'sector(?:ul)?\s*([1-6])\b', lower)
    if m:
        result["zona"] = f"Sector {m.group(1)}"
    else:
        zone_map = {
            "floreasca": "Floreasca", "dorobanți": "Dorobanti",
            "dorobanti": "Dorobanti", "herăstrău": "Herastrau",
            "herastrau": "Herastrau", "aviației": "Aviatiei",
            "aviatiei": "Aviatiei", "pipera": "Pipera",
            "băneasa": "Baneasa", "baneasa": "Baneasa",
            "militari": "Militari", "drumul taberei": "Drumul Taberei",
            "berceni": "Berceni", "titan": "Titan",
            "iancului": "Iancului", "colentina": "Colentina",
            "pantelimon": "Pantelimon", "rahova": "Rahova",
            "cotroceni": "Cotroceni", "grozăvești": "Grozavesti",
            "grozavesti": "Grozavesti", "tineretului": "Tineretului",
            "unirii": "Unirii", "victoriei": "Victoriei",
        }
        for keyword, label in zone_map.items():
            if keyword in lower:
                result["zona"] = label
                break

    # ── Termen contract ───────────────────────────────────────────────
    if re.search(r'termen\s*lung|long\s*term', lower):
        result["termen"] = "lung"
    elif re.search(r'termen\s*scurt|short\s*term|sezon|vacan[tț]', lower):
        result["termen"] = "scurt"

    # ── Facilități ────────────────────────────────────────────────────
    facility_checks = {
        "parcare": [r'\bparcare\b', r'\bloc\s*de\s*parcare\b', r'\bgaraj\b'],
        "balcon":  [r'\bbalcon\b'],
        "terasa":  [r'\bteras[aă]\b'],
        "curte":   [r'\bcurte\b', r'\bgr[aă]din[aă]\b'],
        "centrala_proprie": [r'\bcentral[aă]\s*proprie\b', r'\bcentrală\s*proprie\b'],
        "ac":      [r'\baer\s*condi[tț]ionat\b', r'\bac\b'],
        "mobilat": [r'\bmobilat\b', r'\butilat\b'],
        "lift":    [r'\blift\b', r'\bascensor\b'],
        "renovat": [r'\brenovat\b', r'\bproasp[aă]t\s*zugr\b', r'\breamenajat\b'],
    }
    found = []
    for facility, patterns in facility_checks.items():
        if any(re.search(p, lower) for p in patterns):
            found.append(facility)
    if found:
        result["facilitati"] = ", ".join(found)

    # ── Nr. camere din tip (shortcut) ────────────────────────────────
    camere_map = {"garsoniera": 1, "studio": 1, "1 camera": 1,
                  "2 camere": 2, "3 camere": 3, "4 camere": 4}
    if "tip_proprietate" in result:
        result["camere"] = camere_map.get(result["tip_proprietate"])

    return result


def passes_keyword_filter(
    text: str,
    keywords: list,
    negative_keywords: list,
) -> bool:
    """
    Returneaza True daca postarea trece filtrele de keywords.
    Fara AI — exclusiv string matching case-insensitive.
    """
    lower = text.lower()

    if keywords:
        if not any(kw.lower() in lower for kw in keywords):
            return False

    if negative_keywords:
        if any(kw.lower() in lower for kw in negative_keywords):
            return False

    # Verifica daca postarea contine cel putin un pret sau tip proprietate
    # (filtrare minima pentru a elimina postari irelevante)
    has_price = bool(re.search(
        r'\d+\s*(€|euro|eur|ron|lei)\b', lower
    ))
    has_property = bool(re.search(
        r'\b(garsonier|camere?|apartament|casa|casă|vila|vilă|inchir|vânz|vand)\b',
        lower
    ))

    return has_price or has_property
