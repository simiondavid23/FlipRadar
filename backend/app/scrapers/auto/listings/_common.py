"""Comune pentru scraperele de anunturi auto (OLX Auto, Autovit, Mobile.de,
AutoScout24, Facebook, Kleinanzeigen). curl_cffi (impersonate="chrome131") + BS4.
"""
import json
import random
import re
from typing import Optional

from bs4 import BeautifulSoup

IMPERSONATE = "chrome131"
MAX_LISTINGS = 30

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def build_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    if extra:
        headers.update(extra)
    return headers


def safe_soup(html: str) -> BeautifulSoup:
    """BeautifulSoup(html.parser) cu reparare de charref-uri malformate.

    Python 3.14 html.parser crapa cu ValueError pe un charref fara ';' (ex "&#8203"
    lipit de urmatorul caracter). E o problema de versiune Python, NU specifica unui
    site — orice platforma poate emite acelasi pattern. De aceea reparam preventiv,
    la TOATE scraperele auto: adaugam ';'-ul lipsa inainte de parsare. Nu schimba
    nimic pe HTML valid; doar salveaza HTML-ul invalid care altfel ar crapa parserul.
    """
    return BeautifulSoup(re.sub(r"&#(\d+)(?![\d;])", r"&#\1;", html or ""), "html.parser")


def thumb_from_img(img) -> str:
    """Primul URL http real dintr-un tag <img> (BS4) sau "" daca nu exista.

    Ordinea candidatilor: src, data-src, data-imgsrc (Kleinanzeigen),
    primul URL din srcset, primul URL din data-srcset.
    Filtre: trebuie sa inceapa cu http, fara "no_thumbnail", fara ".svg".
    Sursa pattern-ului: olx_auto.py (filtrul placeholder existent) + kleinanzeigen_auto.py
    (data-imgsrc existent). srcset: primul segment inainte de virgula, primul token
    inainte de spatiu (ex: "https://x/a.jpg 1x, https://x/b.jpg 2x" -> ".../a.jpg").

    `img` poate fi None -> "". Nu arunca niciodata exceptie (safe default "").
    """
    try:
        if img is None:
            return ""
        candidates = [img.get("src"), img.get("data-src"), img.get("data-imgsrc")]
        for attr in ("srcset", "data-srcset"):
            val = img.get(attr)
            if isinstance(val, str) and val.strip():
                # primul URL din srcset: segment inainte de "," apoi token inainte de " "
                candidates.append(val.split(",")[0].strip().split(" ")[0].strip())
        for cand in candidates:
            if not isinstance(cand, str):
                continue
            c = cand.strip()
            low = c.lower()
            if low.startswith("http") and "no_thumbnail" not in low and ".svg" not in low:
                return c
        return ""
    except Exception:
        return ""


# Limite realiste de pret pentru masini. Un singur prag superior generos acopera
# ambele monede: EUR (~300k max pe piata RO) si RON (~1.5M ≈ 300k EUR × ~5 RON/EUR).
# Sub minim = nu e pret; peste maxim = garbage (ex: tot textul cardului concatenat).
_PRICE_MIN = 200
_PRICE_MAX = 1_500_000


def parse_price(text) -> Optional[float]:
    """Extrage un pret numeric dintr-un text.

    Interval valid: 200 – 1.500.000 (acopera atat EUR cat si RON).
    Accepta: "1.500 EUR", "15.000,00 lei", "3500", "€ 8.900".
    Returneaza None pentru valori lipsa, zero sau in afara intervalului realist
    — nu mai produce niciodata numere uriase (overflow) din text concatenat.
    """
    if not text:
        return None

    text = str(text).strip()

    # Format romanesc: punct = separator de mii, virgula = separator zecimal.
    if "," in text and "." in text:
        # ex: "15.000,00" -> "15000.00"
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        # virgula zecimala ("1500,00") vs mii ("1,500"): >2 cifre dupa virgula = mii
        comma_pos = text.rfind(",")
        digits_after = len(re.sub(r"[^\d]", "", text[comma_pos + 1:]))
        text = text.replace(",", ".") if digits_after <= 2 else text.replace(",", "")
    elif "." in text:
        # punct ca separator de mii ("1.500" -> "1500") doar cand sunt 3 cifre dupa
        dot_pos = text.rfind(".")
        digits_after = len(re.sub(r"[^\d]", "", text[dot_pos + 1:]))
        if digits_after == 3:
            text = text.replace(".", "")

    # Primul numar din textul curatat.
    numeric_match = re.search(r"\d[\d\s]*(?:\.\d+)?", text)
    if not numeric_match:
        return None
    try:
        value = float(numeric_match.group().replace(" ", ""))
    except ValueError:
        return None

    # Garda de plauzibilitate — respinge garbage-ul concatenat.
    if value <= _PRICE_MIN or value > _PRICE_MAX:
        return None
    return value


def extract_ld_offers(soup) -> list:
    """Oferte ordonate {name, price, currency} din JSON-LD (schema.org).

    Acopera structurile uzuale de liste de produse de pe site-urile auto:
      itemListElement[].item.offers.price / .priceCurrency   (AutoScout24)
      itemListElement[].offers.price
      itemListElement[].item.priceSpecification.price
    Intoarce prima lista care contine cel putin un pret; [] daca nu gaseste.
    Permite scraperelor sa ia pretul curat din JSON-LD in loc sa-l parseze din
    textul cardului (sursa overflow-urilor).
    """
    def _offer_of(entry):
        if not isinstance(entry, dict):
            return {"name": "", "price": None, "currency": "EUR"}
        item = entry.get("item") if isinstance(entry.get("item"), dict) else entry
        offers = item.get("offers") or entry.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            offers = {}
        spec = item.get("priceSpecification") or offers.get("priceSpecification") or {}
        return {
            "name": str(item.get("name") or entry.get("name") or ""),
            "price": offers.get("price") or spec.get("price") or item.get("price"),
            "currency": (offers.get("priceCurrency") or spec.get("priceCurrency")
                         or item.get("priceCurrency") or "EUR"),
        }

    def _iter_lists(node):
        if isinstance(node, dict):
            il = node.get("itemListElement")
            if isinstance(il, list) and il:
                yield il
            for value in node.values():
                yield from _iter_lists(value)
        elif isinstance(node, list):
            for value in node:
                yield from _iter_lists(value)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (ValueError, TypeError):
            continue
        for item_list in _iter_lists(data):
            offers = [_offer_of(entry) for entry in item_list]
            if any(o["price"] for o in offers):
                return offers
    return []


def parse_int(raw) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    digits = re.sub(r"[^\d]", "", str(raw))
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


def extract_year(text: Optional[str]) -> Optional[int]:
    """Primul an plauzibil (1980-2099) dintr-un text."""
    if not text:
        return None
    m = re.search(r"\b(19[89]\d|20\d{2})\b", text)
    return int(m.group(0)) if m else None


def extract_km(text: Optional[str]) -> Optional[int]:
    """Extrage kilometrajul ('123.000 km', '85 000 km', '200000 km') dintr-un text.

    Regex-ul e strans INTENTIONAT: un km e fie grupat cu UN singur delimitator la
    fiecare 3 cifre ('123.000', '85 000', '1.234.567'), fie o secventa continua de
    2-7 cifre. Vechiul `[\\d.\\s]{2,}` permitea spatii nelimitate si LIPEA doua numere
    diferite din text (ex. ID anunt + km) intr-o valoare gigantica ce crapa INSERT-ul
    (NumericValueOutOfRange, ex km=11202035000). In plus, orice rezultat > 1.500.000
    (nerealist pentru un vehicul) e respins ca garbage -> None.
    """
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})+|\d{2,7})\s*km", text, re.I)
    if not m:
        return None
    km = parse_int(m.group(1))
    if km is not None and km > 1_500_000:
        return None
    return km


def normalize_fuel(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "benzin" in t or "petrol" in t:
        return "benzina"
    if "diesel" in t or "motorina" in t:
        return "diesel"
    if "hibrid" in t or "hybrid" in t:
        return "hibrid"
    if "electric" in t:
        return "electric"
    if "gpl" in t or "lpg" in t:
        return "gpl"
    return None


def normalize_gearbox(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "automat" in t or "automatic" in t:
        return "automata"
    if "manual" in t:
        return "manuala"
    return None


def make_listing(
    *,
    platform: str,
    external_id: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    km: Optional[int] = None,
    engine_type: Optional[str] = None,
    gearbox: Optional[str] = None,
    body_type: Optional[str] = None,
    color: Optional[str] = None,
    pret: Optional[float] = None,
    moneda: str = "EUR",
    locatie: Optional[str] = None,
    titlu: Optional[str] = None,
    descriere: Optional[str] = None,
    source_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> dict:
    """Forma standard a unui anunt auto, aliniata cu modelul AutoListing."""
    return {
        "platform": platform,
        "external_id": external_id,
        "make": make,
        "model": model,
        "year": year,
        "km": km,
        "engine_type": engine_type,
        "gearbox": gearbox,
        "body_type": body_type,
        "color": color,
        "pret": pret,
        "moneda": moneda,
        "locatie": locatie,
        "titlu": titlu,
        "descriere": descriere,
        # Cheie EN pentru extractoarele ML (BMWCollector._features citeste
        # r.get("description")). Anunturile de tip list-view nu au descriere,
        # deci ramane "" — downstream-ul nu se rupe.
        "description": descriere or "",
        "source_url": source_url,
        "thumbnail_url": thumbnail_url,
    }
