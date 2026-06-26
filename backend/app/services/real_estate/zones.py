"""
Zone normalization for Romanian cities.
Maps free-text zone mentions → canonical zone names.
Includes full Bucharest metro station → zone mapping.
"""
import re
from typing import Optional

# ── București — 24 zone canonice ────────────────────────────────

BUCURESTI_ZONES = {
    "Floreasca": [
        "floreasca", "str floreasca", "piata floreasca", "bd floreasca",
        "bulevardul floreasca", "langa floreasca", "floreasca herastrau",
        "zona floreasca",
    ],
    "Dorobanți": [
        "dorobanti", "dorobanți", "piata dorobanti", "zona dorobanti",
        "calea dorobantilor", "dorobanti herastrau",
    ],
    "Herăstrău": [
        "herastrau", "parcul herastrau", "langa herastrau", "lac herastrau",
        "parcul regele mihai", "zona herastrau",
    ],
    "Aviatorilor": [
        "aviatorilor", "bd aviatorilor", "bulevardul aviatorilor",
        "langa aviatorilor", "primaverii", "piata primaverii",
    ],
    "Pipera / Aurel Vlaicu": [
        "pipera", "aurel vlaicu", "barbu vacarescu", "dimitrie pompeiu",
        "floreasca business", "floreasca park", "langa pipera",
    ],
    "Băneasa": [
        "baneasa", "băneasa", "langa baneasa", "aeroportul baneasa",
        "mall baneasa", "zona baneasa",
    ],
    "Victoriei / Romană": [
        "victoriei", "romana", "romană", "piata romana", "piata victoriei",
        "magheru", "bd magheru", "calea victoriei",
    ],
    "Kiseleff / Șosea": [
        "kiseleff", "sosea", "soseaua kiseleff", "arcul de triumf",
        "langa kiseleff", "sos kiseleff",
    ],
    "Unirii / Centru": [
        "unirii", "piata unirii", "centrul vechi", "old town", "lipscani",
        "universitate", "piata universitatii", "centru", "ultracentral",
        "izvor",
    ],
    "Timpuri Noi": [
        "timpuri noi", "mihai bravu", "bd mihai bravu",
        "langa timpuri noi", "zona timpuri noi",
    ],
    "Vitan / Dristor": [
        "vitan", "dristor", "mall vitan", "bd camil ressu",
        "zona vitan", "calea vitan",
    ],
    "Decebal / Nerva Traian": [
        "decebal", "nerva traian", "bd decebal",
        "bd pache protopopescu", "pache protopopescu",
    ],
    "Titan / IOR": [
        "titan", "ior", "parc ior", "theodor pallady",
        "langa titan", "zona titan", "nicolae grigorescu",
    ],
    "Iancului / Obor": [
        "iancului", "obor", "piata obor", "langa obor",
        "piata iancului", "piata muncii", "stefan cel mare",
        "bd stefan cel mare", "expoflora",
    ],
    "Colentina / Tei": [
        "colentina", "tei", "lac tei", "calea colentina", "fundeni",
    ],
    "Pantelimon / Republica": [
        "pantelimon", "republica", "calea pantelimon",
        "1 decembrie 1918", "costin georgian",
    ],
    "Berceni": [
        "berceni", "eroii revolutiei", "brancoveanu", "constantin brancoveanu",
        "piata sudului", "aparatorii patriei", "dimitrie leonida",
        "calea berceni", "zona berceni",
    ],
    "Tineretului": [
        "tineretului", "parcul tineretului", "bd tineretului",
        "langa tineretului",
    ],
    "Cotroceni / Eroilor": [
        "cotroceni", "eroilor", "13 septembrie", "langa cotroceni",
        "bd eroilor", "academia militara",
    ],
    "Grozăvești / Politehnica": [
        "grozavesti", "grozăvești", "politehnica", "regie",
        "campus regie", "langa poli", "campus politehnica",
    ],
    "Crângași / Giulești": [
        "crangasi", "crângași", "giulesti", "giulești", "pacii",
        "petrache poenaru",
    ],
    "Militari": [
        "militari", "gorjului", "bd timisoara", "preciziei",
        "lujerului", "pacii militari",
    ],
    "Drumul Taberei": [
        "drumul taberei", "raul doamnei", "constantin brancusi",
        "parc drumul taberei", "tudor vladimirescu", "favorit",
        "orizont", "romancierilor", "valley ialomitei", "dt",
    ],
    "1 Mai / Jiului": [
        "1 mai", "jiului", "grivita", "griviță", "basarab",
        "laminorului", "lac straulesti", "straulesti", "parc bazilescu",
    ],
    "Gara de Nord": [
        "gara de nord", "langa gara de nord", "zona gara",
        "gara de nord 1", "gara de nord 2",
    ],
}

# ── Metro stations → canonical zone ─────────────────────────────

BUCURESTI_METRO = {
    # M1
    "pantelimon":          "Pantelimon / Republica",
    "republica":           "Pantelimon / Republica",
    "costin georgian":     "Titan / IOR",
    "titan":               "Titan / IOR",
    "nicolae grigorescu":  "Titan / IOR",
    "dristor 1":           "Vitan / Dristor",
    "dristor 2":           "Vitan / Dristor",
    "mihai bravu":         "Timpuri Noi",
    "timpuri noi":         "Timpuri Noi",
    "piata unirii 1":      "Unirii / Centru",
    "unirii 1":            "Unirii / Centru",
    "izvor":               "Unirii / Centru",
    "eroilor":             "Cotroceni / Eroilor",
    "grozavesti":          "Grozăvești / Politehnica",
    "grozăvești":          "Grozăvești / Politehnica",
    "petrache poenaru":    "Crângași / Giulești",
    "crangasi":            "Crângași / Giulești",
    "crângași":            "Crângași / Giulești",
    "basarab":             "Gara de Nord",
    "gara de nord 1":      "Gara de Nord",
    "piata victoriei":     "Victoriei / Romană",
    "piata victoriei 1":   "Victoriei / Romană",
    "piata victoriei 2":   "Victoriei / Romană",
    "stefan cel mare":     "Iancului / Obor",
    "ștefan cel mare":     "Iancului / Obor",
    "obor":                "Iancului / Obor",
    "piata iancului":      "Iancului / Obor",
    "piata muncii":        "Iancului / Obor",
    # M2
    "pipera":              "Pipera / Aurel Vlaicu",
    "aurel vlaicu":        "Pipera / Aurel Vlaicu",
    "aviatorilor":         "Aviatorilor",
    "piata romana":        "Victoriei / Romană",
    "romană":              "Victoriei / Romană",
    "universitate":        "Unirii / Centru",
    "piata unirii 2":      "Unirii / Centru",
    "unirii 2":            "Unirii / Centru",
    "tineretului":         "Tineretului",
    "eroii revolutiei":    "Berceni",
    "brancoveanu":         "Berceni",
    "piata sudului":       "Berceni",
    "aparatorii patriei":  "Berceni",
    "dimitrie leonida":    "Berceni",
    # M3
    "preciziei":           "Militari",
    "pacii":               "Militari",
    "gorjului":            "Militari",
    "lujerului":           "Militari",
    "politehnica":         "Grozăvești / Politehnica",
    # M4
    "gara de nord 2":      "Gara de Nord",
    "grivita":             "1 Mai / Jiului",
    "1 mai":               "1 Mai / Jiului",
    "jiului":              "1 Mai / Jiului",
    "parc bazilescu":      "1 Mai / Jiului",
    "laminorului":         "1 Mai / Jiului",
    "lac straulesti":      "1 Mai / Jiului",
    # M5
    "raul doamnei":        "Drumul Taberei",
    "constantin brancusi": "Drumul Taberei",
    "valea ialomitei":     "Drumul Taberei",
    "parc drumul taberei": "Drumul Taberei",
    "romancierilor":       "Drumul Taberei",
    "tudor vladimirescu":  "Drumul Taberei",
    "favorit":             "Drumul Taberei",
    "orizont":             "Drumul Taberei",
    "academia militara":   "Cotroceni / Eroilor",
}

# ── Other cities ─────────────────────────────────────────────────

CITY_ZONES = {
    "cluj-napoca": {
        "Mărăști":   ["marasti", "mărăști", "calea dorobantilor cluj"],
        "Zorilor":   ["zorilor", "langa ubb", "gradini"],
        "Mănăștur":  ["manastur", "mănăștur", "piata flora"],
        "Centru":    ["centru", "piata unirii", "ultracentral cluj"],
        "Gheorgheni": ["gheorgheni", "zona gheorgheni"],
        "Florești":  ["floresti", "florești", "langa floresti"],
    },
    "iasi": {
        "Copou":      ["copou", "dealul copou", "langa copou"],
        "Tătărași":   ["tatarasi", "tătărași"],
        "Podu Roș":   ["podu ros", "podu roș"],
        "Centru":     ["centru", "piata unirii iasi", "ultracentral"],
        "Nicolina":   ["nicolina", "zona nicolina"],
        "Păcurari":   ["pacurari", "păcurari"],
    },
    "timisoara": {
        "Fabric":           ["fabric", "calea buziasului"],
        "Circumvalațiunii": ["circumvalatiunii", "giroc"],
        "Centru":           ["centru", "piata victoriei tm", "piata unirii tm"],
        "Freidorf":         ["freidorf", "calea torontalului"],
        "Calea Aradului":   ["calea aradului", "aradului"],
        "Dâmbovița":        ["dambovita", "zona dambovita"],
    },
    "brasov": {
        "Centru Civic": ["centru civic", "civic", "centrul brasovului"],
        "Astra":        ["astra", "calea bucuresti brasov"],
        "Bartolomeu":   ["bartolomeu", "triaj"],
        "Schei":        ["schei", "piata unirii brasov"],
        "Tractorul":    ["tractorul", "zona tractorului"],
        "Noua":         ["noua", "zona noua"],
    },
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _detect_city(text: str) -> str:
    t = _normalize_text(text)
    if any(w in t for w in ["bucuresti", "bucurești", "bucharest", "sector"]):
        return "bucuresti"
    if any(w in t for w in ["cluj", "napoca"]):
        return "cluj-napoca"
    if any(w in t for w in ["iasi", "iași"]):
        return "iasi"
    if any(w in t for w in ["timisoara", "timișoara"]):
        return "timisoara"
    if any(w in t for w in ["brasov", "brașov"]):
        return "brasov"
    return "bucuresti"  # default


def normalize_zone(raw_zone: str, city: str = None,
                   custom_aliases: dict = None) -> Optional[str]:
    """
    Returns canonical zone name or None if not recognized.
    custom_aliases: {"alias_text": "CanonicalZone", ...}
    """
    if not raw_zone:
        return None

    t = _normalize_text(raw_zone)
    if city:
        city = _normalize_text(city)
        if city in ("bucurești", "bucharest"):
            city = "bucuresti"
    else:
        city = _detect_city(t)

    # Check custom aliases first (user-defined)
    if custom_aliases:
        for alias, canonical in custom_aliases.items():
            if _normalize_text(alias) in t:
                return canonical

    # Check metro stations (București only)
    if city == "bucuresti":
        for station, zone in BUCURESTI_METRO.items():
            if station in t:
                return zone

        for zone_canonical, aliases in BUCURESTI_ZONES.items():
            for alias in aliases:
                if alias in t:
                    return zone_canonical

    # Other cities
    city_dict = CITY_ZONES.get(city, {})
    for zone_canonical, aliases in city_dict.items():
        for alias in aliases:
            if alias in t:
                return zone_canonical

    return None


def retroactive_normalize(db, custom_aliases: dict, model_class) -> int:
    """
    When user adds a new custom alias, retroactively normalize
    existing listings in DB that contain that alias.
    Returns count of updated records.
    """
    updated = 0
    try:
        listings = db.query(model_class).filter(
            model_class.zone_normalized.is_(None),
            model_class.zone_raw.isnot(None),
        ).all()
        for listing in listings:
            normalized = normalize_zone(
                listing.zone_raw, custom_aliases=custom_aliases)
            if normalized:
                listing.zone_normalized = normalized
                updated += 1
        db.commit()
    except Exception as exc:
        print(f"[ZoneNorm] retroactive error: {exc}")
        db.rollback()
    return updated
