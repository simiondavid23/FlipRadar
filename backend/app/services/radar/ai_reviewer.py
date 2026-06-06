"""AI review pentru un listing — text scurt in romana generat cu Groq.

Reutilizam clientul Groq din services/ai_service.py (acelasi GROQ_API_KEY).
Daca apelul esueaza, returnam "" — orchestratorul continua fara review.
"""
from typing import Optional

from app.services.ai_service import client, MODEL


def generate_ai_review(
    title: str,
    description: Optional[str],
    price: float,
    resale_price: float,
    platform: str,
    score: Optional[str],
    condition: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """Genereaza review-ul AI pentru un listing. Returneaza "" la eroare."""
    desc_raw = (description or "").strip()
    desc_for_prompt = desc_raw if desc_raw else "Nu există descriere"
    try:
        margin_value = float(resale_price or 0) - float(price or 0)
        margin_pct = (margin_value / float(resale_price)) * 100.0 if resale_price else 0.0
    except (TypeError, ValueError):
        margin_value = 0.0
        margin_pct = 0.0

    missing_desc_note = ""
    if len(desc_raw) < 20:
        missing_desc_note = (
            "ATENȚIE: Vânzătorul nu a scris nicio descriere — tratează asta "
            "ca semnal de risc.\n\n"
        )

    prompt = (
        "Ești un expert în flipping pe piețele second-hand din România.\n"
        "Analizează CONCRET acest anunț. Fii direct și specific — evită fraze "
        "vagi precum \"descrierea este vagă\" sau \"merită contactat\".\n\n"
        "DATE ANUNȚ:\n"
        f"- Titlu: {title}\n"
        f"- Platformă: {platform}\n"
        f"- Preț cerut: {price} RON\n"
        f"- Preț estimat revânzare: {resale_price} RON\n"
        f"- Marjă: {margin_value:.0f} RON ({margin_pct:.0f}%)\n"
        f"- Scor deal: {score or '—'}\n"
        f"- Condiție declarată: {condition or 'nespecificată'}\n"
        f"- Locație: {location or 'nespecificată'}\n"
        f"- Descriere vânzător: {desc_for_prompt}\n\n"
        f"{missing_desc_note}"
        "Răspunde în exact 4 propoziții scurte în română:\n"
        "1. [DESCRIERE] Ce îți spune sau nu îți spune descrierea despre starea reală "
        "a produsului? Dacă nu există descriere, spune explicit că absența ei este "
        "un semnal de risc.\n"
        f"2. [PREȚ] Față de prețul de revânzare de {resale_price} RON, prețul de "
        f"{price} RON este bun/acceptabil/scump? Menționează marja concretă.\n"
        "3. [RISC] Care este cel mai mare risc specific al acestui anunț?\n"
        "4. [DECIZIE] Contactezi sau nu? Dacă da, ce întrebare specifică pui "
        "vânzătorului ca prim mesaj?"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=500,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"[AiReviewer] Eroare Groq: {exc}")
        return ""
