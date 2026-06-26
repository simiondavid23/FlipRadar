"""
Filtre de relevanță pentru colectorii ML.
Asigură că market_listings conține doar anunțuri de produse
complete, nu piese/accesorii.
"""

# ── Apple ─────────────────────────────────────────────────────────
APPLE_VALID_STARTS = (
    "iphone", "ipad", "macbook", "airpods", "apple watch",
    "vand iphone", "vand ipad", "vand macbook",
    "vanzare iphone", "vanzare ipad",
)

APPLE_ABSOLUTE_EXCLUDE = (
    "dezmembrez", "dezmembrare", "piese iphone", "piese ipad",
    "piese macbook", "lcd iphone", "touchscreen iphone",
    "geam iphone", "rama iphone", "carcasa iphone",
    "schimb display", "schimb ecran",
)

APPLE_PRICE_MIN_RON = 200.0


def is_relevant_apple(title: str, price: float = None) -> bool:
    t = (title or "").lower().strip()

    # Absolute exclusions — appear ONLY in parts listings
    if any(excl in t for excl in APPLE_ABSOLUTE_EXCLUDE):
        return False

    # Title must start with or contain the product name
    if not any(t.startswith(start) for start in APPLE_VALID_STARTS):
        # Allow "vand ...", "vanzare ...", "ofer ..."
        # but only if product name appears in first 30 chars
        first = t[:30]
        if not any(prod in first for prod in
                   ("iphone", "ipad", "macbook", "airpods")):
            return False

    # Price floor
    if price is not None and price < APPLE_PRICE_MIN_RON:
        return False

    return True


# ── BMW ───────────────────────────────────────────────────────────
BMW_PARTS_START_WORDS = (
    "piese ", "jante ", "far ", "bara ", "capota ", "hayon ",
    "usa ", "motor scos", "cutie viteze", "alternator ",
    "pompa ", "radiator ", "cauciuc ", "electromotor ",
    "cumpar ", "caut ", "schimb ", "dezmembrez", "dezmembrare",
)

BMW_ABSOLUTE_EXCLUDE = (
    "dezmembrez", "dezmembrare", "piese bmw",
    "motor scos", "cutie viteze scoasa",
)

BMW_PRICE_MIN_EUR = 500.0
BMW_YEAR_MIN = 1990


def is_relevant_bmw(
    title: str,
    price: float = None,
    year: int = None,
    has_year_and_km: bool = False,
) -> bool:
    t = (title or "").lower().strip()

    # Absolute exclusions
    if any(excl in t for excl in BMW_ABSOLUTE_EXCLUDE):
        return False

    # Must mention BMW somewhere in title
    if "bmw" not in t:
        return False

    # Title must not START with parts-indicating words
    if any(t.startswith(start) for start in BMW_PARTS_START_WORDS):
        return False

    # For Autovit listings: presence of year + km is primary signal
    # (complete cars always have these; parts listings never do)
    if has_year_and_km:
        return True  # skip further price/year checks for Autovit

    # Price and year floors for OLX/Mobile.de
    if price is not None and price < BMW_PRICE_MIN_EUR:
        return False
    if year is not None and year < BMW_YEAR_MIN:
        return False

    return True
