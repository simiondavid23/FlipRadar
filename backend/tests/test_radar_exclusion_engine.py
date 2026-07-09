"""RP-2 — engine de excluderi v2 (diacritice + word-boundary + excepții + fraze)."""
import pytest

from app.services.radar.exclusion_engine import check_exclusion, normalize


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
