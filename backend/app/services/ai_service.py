"""Client AI comun pentru FlipRadar — furnizor comutabil per utilizator (PKG-2).

Clientul Groq singleton a fost inlocuit cu un client OpenAI-compatibil rezolvat
per utilizator (`get_ai_client`): Groq sau Google Gemini, prin acelasi API
OpenAI-compatibil. Cheia vine din `users.ai_api_key` (fallback `GROQ_API_KEY` din
env, doar pentru provider `groq` — compat cu instanta istorica). Consumat de
review-urile AI per anunt (radar/ai_reviewer.py), extractia auto (routers/auto.py)
si extractia imobiliara (real_estate/extractor.py).
"""
import json
import asyncio
from openai import OpenAI
from app.config import GROQ_API_KEY


class AIConfigError(Exception):
    """Configuratie AI lipsa/invalida — mesajul e destinat utilizatorului."""


PROVIDERS = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
    },
}


def resolve_ai_config(user):
    """(provider, api_key, model) pentru user. Prioritate cheie:
    users.ai_api_key > GROQ_API_KEY din env (compat, doar provider groq)
    > AIConfigError cu mesaj de indrumare."""
    provider = ((getattr(user, "ai_provider", None) or "groq")).strip().lower()
    if provider not in PROVIDERS:
        raise AIConfigError(f"Furnizor AI necunoscut: {provider}")
    key = (getattr(user, "ai_api_key", None) or "").strip()
    if not key and provider == "groq":
        key = (GROQ_API_KEY or "").strip()
    if not key:
        raise AIConfigError(
            "Nicio cheie AI configurata. Alege furnizorul si introdu cheia "
            "in Setari — sectiunea Functii AI.")
    model = ((getattr(user, "ai_model", None) or "").strip()
             or PROVIDERS[provider]["default_model"])
    return provider, key, model


def get_ai_client(user):
    provider, key, model = resolve_ai_config(user)
    return OpenAI(api_key=key, base_url=PROVIDERS[provider]["base_url"]), model


def clean_json_response(text: str) -> str:
    """FlipRadar — BUG 7: extrage JSON valid din raspunsul AI in 4 fallback-uri
    ordonate. Primul pas care reuseste returneaza rezultatul; ultima solutie este
    regex-ul original care escapeaza caracterele de control din valorile string."""
    import re, json

    # Pas 1: parsare directa
    try:
        return json.dumps(json.loads(text.strip()), ensure_ascii=False)
    except Exception:
        pass

    # Pas 2: extrage blocul {...} si parseaza
    match = re.search(r'\{[\s\S]*\}', text)
    extracted = match.group(0) if match else text.strip()
    try:
        return json.dumps(json.loads(extracted), ensure_ascii=False)
    except Exception:
        pass

    # Pas 3: parsare toleranta (strict=False) pe blocul extras
    try:
        return json.dumps(json.loads(extracted, strict=False), ensure_ascii=False)
    except Exception:
        pass

    # Pas 4: ultima solutie — regex-ul original aplicat pe blocul extras, care
    # escapeaza newline/tab/CR din interiorul valorilor string inainte de parsare.
    fixed = re.sub(
        r'(?<=": ")(.*?)(?="[,\}])',
        lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'),
        extracted,
        flags=re.DOTALL,
    )
    try:
        return json.dumps(json.loads(fixed, strict=False), ensure_ascii=False)
    except Exception:
        return extracted


async def extract_auto_features_from_description(description: str, existing_data: dict = {}, *, user) -> dict:
    """Extrage informatii structurate din descrierea unui anunt auto (client AI per user)."""
    if not description or len(description) < 50:
        return {}

    # get_ai_client INAINTE de try, ca AIConfigError (config lipsa) sa propage,
    # nu sa fie inghitita de `except Exception: return {}` de mai jos.
    client, model = get_ai_client(user)

    prompt = f"""Extrage urmatoarele informatii DIN TEXTUL DE MAI JOS.
REGULA CRITICA: Daca o informatie NU este mentionata explicit in text, scrie null.
Nu face presupuneri. Nu inventa informatii.

TEXT (max 2500 caractere):
{description[:2500]}

Returneaza STRICT JSON valid:
{{
    "itp_valid_until": null,
    "timing_belt_changed_at_km": null,
    "oil_change_at_km": null,
    "brake_pads_changed": null,
    "tires_info": null,
    "num_owners": null,
    "service_history": null,
    "accidents_denied": null,
    "defects_mentioned": null,
    "recent_works": null,
    "import_from": null,
    "urgent_sale": null,
    "warranty_months": null,
    "aftermarket_modifications": null,
    "reason_for_sale": null,
    "allows_test_drive": null
}}"""

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        raw = clean_json_response(response.choices[0].message.content)
        extracted = json.loads(raw)

        # Cross-validare: km_curea > km_actuali = warning
        warnings = []
        actual_km = existing_data.get("km")
        if extracted.get("timing_belt_changed_at_km") and actual_km:
            try:
                if int(extracted["timing_belt_changed_at_km"]) > int(actual_km):
                    warnings.append("km_curea_distributie > km_actuali - posibil typo")
            except (TypeError, ValueError):
                pass

        if warnings:
            extracted["_warnings"] = warnings
        return extracted
    except Exception:
        return {}
