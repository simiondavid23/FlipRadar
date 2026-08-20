"""RP-2 — engine de excluderi v2 (diacritice + word-boundary + excepții + fraze).

FBS-8 a adăugat `keyword_digits_match` (potrivirea cifrelor keyword-ului în titlu),
testată la finalul fișierului.
"""
import pytest

from app.services.radar.exclusion_engine import (
    check_exclusion, keyword_digits_match, normalize,
)


def test_normalize_strips_diacritics():
    assert normalize("Husă ÎNCĂLȚĂMINTE șțâ") == "husa incaltaminte sta"


# (title, description, exclude_words, exclude_desc, exceptions, expected_excluded)
_CASES = [
    ("Husă iPhone 12", None, ["husa"], None, None, True),          # diacritice: husa ~ Husă
    ("iPhone 12 Deblocat", None, ["blocat"], None, None, False),   # boundary: deblocat ≠ blocat
    ("iPhone blocat rețea", None, ["blocat"], None, None, True),   # cuvânt întreg
    ("Anunț cautat des", None, ["caut"], None, None, False),       # caut ≠ cautat
    ("caut iphone 12", None, ["caut"], None, None, True),
    ("Schimbător viteze", None, ["schimb"], None, None, False),    # schimb ≠ schimbător
    ("Ofer la schimb", None, ["schimb"], None, None, True),
    ("telefon fara defecte", None, ["defect"], None, None, False), # excepție DEFAULT neutralizează
    ("telefon cu defect minor", None, ["defect"], None, None, True),
    ("iPhone 12 pro impecabil", None, ["defect"], None, None, False),  # nimic de exclus
]


@pytest.mark.parametrize("title,desc,ew,edw,exc,expected", _CASES)
def test_check_exclusion_title(title, desc, ew, edw, exc, expected):
    excluded, rule = check_exclusion(title, desc, ew, edw, exc)
    assert excluded is expected
    if expected:
        assert rule and "titlu" in rule
    else:
        assert rule is None


def test_phrase_on_description():
    excluded, rule = check_exclusion(
        "iPhone 12", "Vând pentru piese, nu funcționează.", [], ["pentru piese"], None,
    )
    assert excluded is True
    assert "descriere" in rule


def test_custom_exception_neutralizes():
    # excepție per-keyword: „fara zgarieturi" neutralizează cuvântul „zgarieturi"
    ex, _ = check_exclusion("telefon fara zgarieturi", None, ["zgarieturi"], None, ["fara zgarieturi"])
    assert ex is False
    ex2, _ = check_exclusion("telefon cu zgarieturi vizibile", None, ["zgarieturi"], None, ["fara zgarieturi"])
    assert ex2 is True


def test_multiword_exclude_is_substring():
    # termen CU spațiu = frază -> substring (nu boundary strict pe fiecare cuvânt)
    ex, _ = check_exclusion("Vând iPhone pentru piese", None, ["pentru piese"], None, None)
    assert ex is True


# ── FBS-8: potrivirea cifrelor keyword-ului în titlu ─────────────────────────
# (keyword, title, expected, de_ce)
_DIGIT_CASES = [
    # Exemplele NORMATIVE, toate din datele reale măsurate la FBS-V2.
    ("iphone 15 pro max", "iPhone15 Pro Max GB", True,
     "lipit de litere e valid: anunț legitim din feed-ul real"),
    ("iphone 15 pro max", "Apple iphone 14promax//-", False,
     "alt model: nu conține grupul 15"),
    ("iphone 15 pro max", "Iphone 17 Pro max nou", False,
     "alt model: 17, nu 15"),
    ("iphone 15 pro max", "iphone 1500 lei super oferta", False,
     "GRANIȚĂ DE CIFRE: 15 înghițit de 1500 nu contează"),
    # LIMITĂ ASUMATĂ, nu accident: regula fixează CIFRELE, nu sufixele de gamă.
    # „15 Plus" poartă grupul 15, deci trece la o căutare de „15 pro max".
    # Rafinarea pe sufixe e o rundă viitoare — vezi docstring-ul funcției.
    ("iphone 15 pro max", "iPhone 15 Plus-89% Batery", True,
     "LIMITĂ ASUMATĂ: sufixul de gamă nu e verificat, doar cifrele"),

    # Keyword FĂRĂ cifre -> no-op complet, pe orice titlu.
    ("canapea extensibila", "Canapea extensibilă bej", True, "no-op: keyword fără cifre"),
    ("canapea extensibila", "Apple iphone 14promax//-", True,
     "no-op: fără cifre în keyword regula nu poate tăia nimic"),

    # Grupuri multiple: TOATE obligatorii.
    ("iphone 15 256gb", "iPhone 15 256GB ca nou", True, "ambele grupuri prezente"),
    ("iphone 15 256gb", "iPhone 15 128GB ca nou", False, "doar 15 prezent, 256 lipsește"),
    ("iphone 15 256gb", "iPhone 14 256GB ca nou", False, "doar 256 prezent, 15 lipsește"),

    # Diacritice în keyword (normalize NFD înainte de extragerea grupurilor).
    ("cămașă 15", "Camasa 15 marimea L", True, "diacritice în keyword, grup prezent"),
    ("cămașă 15", "Cămașă 20 mărimea L", False, "diacritice în keyword, grup absent"),

    # Grup repetat în titlu: o singură potrivire e de ajuns.
    ("iphone 15", "iPhone 15, 15 bucăți disponibile", True, "grup repetat în titlu"),

    # Granița taie la AMBELE capete, nu doar la dreapta.
    ("bmw 320", "BMW 3200 turbo", False, "înghițit la dreapta"),
    ("bmw 320", "BMW 0320 ceva", False, "înghițit la stânga"),
    ("bmw 320", "BMW x320d Touring", True, "litere lipite pe ambele părți: valid"),

    # Titlu absent / gol, cu grupuri prezente în keyword.
    ("iphone 15 pro max", None, False, "titlu None"),
    ("iphone 15 pro max", "", False, "titlu gol"),
    ("iphone 15 pro max", "   ", False, "titlu doar spații"),

    # Keyword absent / gol -> no-op (nu are grupuri de cifre).
    (None, "orice titlu", True, "keyword None"),
    ("", "orice titlu", True, "keyword gol"),
]


@pytest.mark.parametrize("keyword,title,expected,de_ce", _DIGIT_CASES)
def test_keyword_digits_match(keyword, title, expected, de_ce):
    assert keyword_digits_match(keyword, title) is expected, de_ce
