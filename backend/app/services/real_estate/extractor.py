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
                 groq_enabled: bool = True) -> dict:
    """
    Fallback to Groq LLM when regex misses critical fields.
    Only called when price OR rooms is missing.
    Respects AI features toggle.
    """
    if not groq_enabled:
        return existing
    if existing.get("price") and existing.get("rooms"):
        return existing  # regex got what we need

    try:
        from groq import Groq
        import json
        import os
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        prompt = (
            "Extrage din textul următor: pret (număr), moneda (EUR/RON), "
            "camere (număr întreg sau 1 pentru garsonieră/studio), "
            "suprafata_mp (număr), etaj (text), zona (string). "
            "Răspunde DOAR cu JSON valid, fără explicații. "
            "Dacă nu găsești un câmp, folosește null.\n"
            f"Text: {text[:800]}"
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
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
        print(f"[Extractor] Groq fallback error: {exc}")
        return existing
