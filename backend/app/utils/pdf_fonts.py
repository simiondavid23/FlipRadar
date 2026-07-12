"""Fonturi Unicode pentru PDF-urile generate cu reportlab (GE-5).

Helvetica (WinAnsi) nu contine diacriticele romanesti ă/ș/ț, deci textul introdus de
utilizatori apare corupt. Inregistram DejaVu Sans (impachetat in repo) o singura data;
daca TTF-urile lipsesc sau inregistrarea esueaza, cadem inapoi pe Helvetica ca
generarea de PDF sa nu crape niciodata."""
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts"
)
_REGULAR = "DejaVuSans"
_BOLD = "DejaVuSans-Bold"
_registered = False
_available = False


def ensure_pdf_fonts() -> tuple[str, str]:
    """Returneaza (font_regular, font_bold). Inregistrare la primul apel, idempotenta."""
    global _registered, _available
    if not _registered:
        _registered = True
        try:
            pdfmetrics.registerFont(TTFont(_REGULAR, os.path.join(_FONTS_DIR, "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont(_BOLD, os.path.join(_FONTS_DIR, "DejaVuSans-Bold.ttf")))
            _available = True
        except Exception:
            _available = False
    return (_REGULAR, _BOLD) if _available else ("Helvetica", "Helvetica-Bold")
