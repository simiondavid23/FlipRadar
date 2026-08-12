"""Helper partajat: numar cu separatori ambigui (mii vs zecimale) -> float.

Regula "feed" (Facebook Marketplace & co, unde acelasi feed amesteca formatul RO cu
cel EN): o virgula in GRUPURI DE 3 e separator de mii, orice alta virgula e zecimala;
punctul in grupuri de 3 e separator de mii. Cand apar ambele, ULTIMUL e zecimalul.

Bugul reparat de aceasta regula (SCRAPE-AUDIT, apoi R1 pe Radar): un replace orb
`.replace(".", "").replace(",", ".")` facea "RON1,500" -> 1.5, deci de 1000x mai mic,
TACUT si in gama care trece de filtre.

ATENTIE — NU e regula universala din proiect. `product_page_extractor._parse_price_any`
(RETAIL) trateaza deliberat virgula MEREU ca zecimala, fiindca magazinele romanesti
scriu "24,99"; acolo un grup de 3 nu apare in practica. Nu unifica cele doua.

Aceeasi regula, duplicata istoric si in `services/real_estate/extractor._clean_number`
si `scrapers/real_estate/facebook_real_estate._parse_price` — ambele au preprocesare
proprie si teste proprii, deci raman pe loc; acesta e locul canonic pentru cod NOU
(model REF-1: helper pur in app/utils, fara dependinte, deci fara ciclu de import).
"""
import re
from typing import Optional

_THOUSANDS_COMMA = re.compile(r"\d{1,3}(,\d{3})+")
_THOUSANDS_DOT = re.compile(r"\d{1,3}(\.\d{3})+")


def parse_number(token) -> Optional[float]:
    """Token numeric (eventual cu simboluri/valuta in jur) -> float, sau None.

    Nu extrage numarul dintr-un text cu MAI MULTE numere: curata tot ce nu e cifra
    sau separator, deci "1,500 - 2,000" ar deveni "1,5002,000". Apelantul da un
    singur numar (ex. prin re.search(r"[\\d.,]+", text)).
    """
    t = re.sub(r"[^\d.,]", "", str(token or ""))
    if not t or not any(ch.isdigit() for ch in t):
        return None
    if "," in t and "." in t:
        # Ultimul separator e cel zecimal: "1.234,56" -> RO, "1,234.56" -> EN.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if _THOUSANDS_COMMA.fullmatch(t) else t.replace(",", ".")
    elif "." in t:
        if _THOUSANDS_DOT.fullmatch(t):
            t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None
