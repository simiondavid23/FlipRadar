"""Engine de excluderi v2 (RP-2) — opt-in per keyword (mod `advanced`).

Fata de `is_excluded` (substring simplu, folosit in modul `simple`), aici:
  - diacritics-insensitive (normalize NFD + strip combining);
  - termenii FARA spatiu se potrivesc pe cuvant intreg (word-boundary) -> „blocat"
    NU prinde „deblocat", „caut" NU prinde „cautat", „schimb" NU prinde „schimbator";
  - termenii CU spatiu (fraze) se potrivesc ca substring;
  - fraze-EXCEPTIE (DEFAULT + per keyword) neutralizeaza matching-ul: „telefon fara
    defecte" nu mai contine „defect" la potrivire.
Functii PURE (fara DB) — testabile table-driven.
"""
import re
import unicodedata


# Fraze care neutralizeaza excluderi (deja normalizate: fara diacritice, lowercase).
DEFAULT_EXCEPTIONS = [
    "fara defecte", "fara defect", "nu are defecte", "nu prezinta defecte",
    "0 defecte", "niciun defect", "fara probleme",
]


def normalize(s) -> str:
    """lowercase + eliminare diacritice (NFD, strip combining marks)."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFD", str(s))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def _apply_exceptions(text: str, exceptions) -> str:
    """Inlocuieste cu spatiu frazele-exceptie prezente in `text` (neutralizare).
    Cele mai lungi intai, ca „fara defecte" sa fie scoasa inainte de „fara defect"."""
    for exc in sorted((e for e in exceptions if e), key=len, reverse=True):
        if exc and exc in text:
            text = text.replace(exc, " ")
    return text


def _term_matches(term: str, text: str) -> bool:
    """Termen fara spatiu -> word-boundary; termen cu spatiu (fraza) -> substring.
    `term` si `text` sunt deja normalizate."""
    term = (term or "").strip()
    if not term:
        return False
    if " " in term:
        return term in text
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def check_exclusion(title, description, exclude_words, exclude_description_words,
                    exceptions=None) -> tuple[bool, str | None]:
    """(excluded, matched_rule). `exclude_words` se aplica pe titlu, iar
    `exclude_description_words` pe descriere. `exceptions` = fraze suplimentare
    (peste DEFAULT_EXCEPTIONS) care neutralizeaza matching-ul. matched_rule descrie
    regula care a prins (pentru tester)."""
    all_exceptions = [normalize(e) for e in (list(DEFAULT_EXCEPTIONS) + list(exceptions or []))]

    title_norm = _apply_exceptions(normalize(title), all_exceptions)
    desc_norm = _apply_exceptions(normalize(description), all_exceptions)

    for w in (exclude_words or []):
        if _term_matches(normalize(w), title_norm):
            return True, f'„{w}" (în titlu)'
    for w in (exclude_description_words or []):
        if _term_matches(normalize(w), desc_norm):
            return True, f'„{w}" (în descriere)'
    return False, None
