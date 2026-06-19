import re


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
