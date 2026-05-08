import re
import json
from groq import Groq
from app.config import GROQ_API_KEY

# Configure Groq client
client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.3-70b-versatile"


def clean_json_response(text: str) -> str:
    """Clean AI response to extract valid JSON.
    Removes markdown code blocks, control characters, and other formatting."""
    # Remove ```json ... ``` or ``` ... ``` blocks
    cleaned = re.sub(r'```(?:json)?\s*', '', text)
    cleaned = cleaned.strip()
    # Try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        raw_json = match.group(0)
    else:
        raw_json = cleaned

    # Try parsing directly first
    try:
        parsed = json.loads(raw_json)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    # Fix control characters inside string values (newlines, tabs in JSON strings)
    # Replace actual newlines/tabs inside JSON string values with escaped versions
    fixed = re.sub(r'(?<=": ")(.*?)(?="[,\}])', lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'), raw_json, flags=re.DOTALL)
    try:
        parsed = json.loads(fixed)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    # Last resort: remove all control characters except \n between { }
    fixed2 = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f]', '', raw_json)
    # Replace unescaped newlines inside string values
    # Strategy: use strict=False in json.loads
    try:
        parsed = json.loads(fixed2, strict=False)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    return raw_json


async def chat_with_gemini(message: str, system_prompt: str = "", history: list = None) -> str:
    """Send a message to Groq and get a response."""
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": message})
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Eroare la comunicarea cu AI: {str(e)}"


async def analyze_product_with_ai(
    product_name: str,
    category: str = "",
    price: float = 0,
    source: str = "",
    currency: str = "EUR",
    user_name: str = "",
) -> str:
    """Analyze a product for profitability using AI."""
    greeting = f"Analizezi acest produs pentru {user_name}." if user_name else ""
    prompt = f"""Esti un expert in comert online si revanzarea produselor pe marketplace-uri din Romania si UE (eMAG, Altex, OLX, Okazii, magazine proprii etc.). Calculezi profitabilitati cu cifre concrete, NU oferi raspunsuri vagi.

{greeting}
Analizeaza urmatorul produs si construieste o evaluare COMPLETA + NUMERICA pentru revanzare:

Produs: {product_name}
Categorie: {category if category else "Nespecificata"}
Pret achizitie: {price if price else "Nespecificat"} {currency}
Magazin sursa: {source if source else "Nespecificat"}

Cerinte stricte la calculul cifrelor:
- TOATE preturile in EUR (converteste din RON la curs ~5 RON/EUR daca e cazul).
- pret_vanzare_estimat: pretul realist la care s-ar putea revinde pe piata RO/UE, dupa o cercetare scurta a categoriei. Daca nu ai informatii, estimeaza conservator (markup 20-50% peste pretul de achizitie).
- profit_brut_eur: pret_vanzare_estimat - pret_achizitie_eur (cifra concreta in EUR).
- costuri_operationale_eur: estimare pentru ambalare + transport + comision platforma (5-15% din pret_vanzare).
- profit_net_eur: profit_brut_eur - costuri_operationale_eur (cifra concreta).
- marja_neta_pct: (profit_net_eur / pret_vanzare_estimat) * 100, rotunjit la 1 zecimala.
- roi_pct: (profit_net_eur / pret_achizitie_eur) * 100, rotunjit la 1 zecimala.
- Toate cifrele trebuie sa fie consistente intre ele (sa se verifice matematic).

Raspunde STRICT in format JSON valid (fara markdown, fara ```), cu urmatoarea structura:
{{
    "scor_profitabilitate": <numar 1-10, bazat pe ROI + demand + competitie>,
    "verdict": "<RECOMANDAT/NEUTRU/NERECOMANDAT>",
    "pret_achizitie_eur": <pret achizitie in EUR>,
    "pret_vanzare_estimat": <numar in EUR>,
    "profit_brut_eur": <numar in EUR>,
    "costuri_operationale_eur": <numar in EUR>,
    "profit_net_eur": <numar in EUR>,
    "marja_neta_pct": <numar, ex: 18.5>,
    "roi_pct": <numar, ex: 35.2>,
    "nivel_competitie": "<scazut/mediu/ridicat>",
    "explicatie_competitie": "<o propozitie despre cati vanzatori similari sunt si pe ce platforme>",
    "demand_score": <numar 1-10>,
    "explicatie_demand": "<o propozitie despre cererea estimata>",
    "sezonalitate": "<tot_anul/primavara_vara/toamna_iarna/sarbatori>",
    "explicatie_sezonalitate": "<o propozitie despre cand se vinde cel mai bine>",
    "factori_risc": [
        "<risc 1 concret>",
        "<risc 2 concret>"
    ],
    "platforme_recomandate": [
        "<platforma 1, ex: eMAG Marketplace>",
        "<platforma 2, ex: OLX>"
    ],
    "sfaturi": [
        "<sfat actionabil 1>",
        "<sfat actionabil 2>",
        "<sfat actionabil 3>"
    ],
    "explicatie_verdict": "<explicatie scurta 2-3 propozitii a verdictului, cu referire la cifrele de mai sus>"
}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content
        return clean_json_response(raw)
    except Exception as e:
        return json.dumps({"error": f"Eroare la analiza: {str(e)}"})


async def generate_product_listing(
    product_name: str,
    category: str = "",
    features: str = "",
    price: float = 0,
    currency: str = "EUR",
    user_name: str = "",
) -> str:
    """Generate an optimized product listing for online marketplaces."""
    byline = f"Pregatesti listingul pentru {user_name}, un vanzator care foloseste FlipRadar pentru a gasi produse profitabile pentru revanzare." if user_name else ""
    prompt = f"""Esti un expert in copywriting si SEO pentru marketplace-uri online (eMAG Marketplace, OLX, Okazii, magazine proprii Shopify/WooCommerce).
{byline}
Genereaza un listing complet si optimizat SEO pentru urmatorul produs:

Produs: {product_name}
Categorie: {category if category else "Nespecificata"}
Caracteristici: {features if features else "Nespecificate"}
Pret orientativ: {price if price else "Nespecificat"} {currency}

Raspunde STRICT in format JSON valid (fara markdown, fara ```), cu urmatoarea structura:
{{
    "titlu": "<titlu optimizat SEO, max 200 caractere, cu cuvinte cheie relevante>",
    "bullet_points": [
        "<bullet point 1 - beneficiu principal>",
        "<bullet point 2 - caracteristica cheie>",
        "<bullet point 3 - material/calitate>",
        "<bullet point 4 - utilizare/compatibilitate>",
        "<bullet point 5 - garantie/bonus>"
    ],
    "descriere": "<descriere completa 300-500 cuvinte, cu paragrafe, optimizata SEO>",
    "cuvinte_cheie": ["<cuvant1>", "<cuvant2>", "<cuvant3>", "<cuvant4>", "<cuvant5>"],
    "sfaturi_listing": [
        "<sfat 1 pentru optimizare>",
        "<sfat 2 pentru optimizare>"
    ]
}}"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content
        return clean_json_response(raw)
    except Exception as e:
        return json.dumps({"error": f"Eroare la generare: {str(e)}"})


async def generate_ai_report(user_data: dict) -> str:
    """Generate an AI-powered activity report tailored to the current user."""
    prompt = f"""Esti un analist de business specializat in comertul online si revanzarea produselor pe marketplace-uri din Romania si UE.
Raportul este destinat utilizatorului {user_data.get("username", "Utilizator")}. Foloseste-i numele si da recomandari CONCRETE bazate pe activitatea lui reala (produsele lui, inventarul lui, vanzarile lui), nu sfaturi generice.

Date utilizator:
- Nume: {user_data.get("username", "Utilizator")}
- Produse in baza de date (global): {user_data.get("total_products", 0)}
- Produse in watchlist: {user_data.get("watchlist_count", 0)}
- Alerte active: {user_data.get("active_alerts", 0)}
- Alerte declansate: {user_data.get("triggered_alerts", 0)}
- Inregistrari de pret: {user_data.get("total_price_records", 0)}
- Produse watchlist (detalii): {user_data.get("watchlist_products", "[]")}
- Articole in inventar: {user_data.get("inventory_count", 0)}
- Inventar (detalii): {user_data.get("inventory_products", "[]")}
- Vanzari totale: {user_data.get("sales_count", 0)}
- Vanzari recente: {user_data.get("recent_sales", "[]")}

Genereaza un raport in format JSON valid (fara markdown, fara ```):
{{
    "rezumat_general": "<paragraf rezumat 3-4 propozitii despre activitatea utilizatorului>",
    "statistici_cheie": [
        "<statistica relevanta 1>",
        "<statistica relevanta 2>",
        "<statistica relevanta 3>"
    ],
    "produse_recomandate": "<analiza si recomandari bazate pe produsele din watchlist>",
    "alerte_status": "<analiza alertelor si ce ar trebui sa faca utilizatorul>",
    "recomandari": [
        "<recomandare actionabila 1>",
        "<recomandare actionabila 2>",
        "<recomandare actionabila 3>",
        "<recomandare actionabila 4>"
    ],
    "tendinte": "<observatii despre tendinte bazate pe datele disponibile>",
    "scor_activitate": <numar 1-100 reprezentand cat de activ e utilizatorul>,
    "urmatorul_pas": "<cel mai important lucru pe care ar trebui sa il faca utilizatorul>"
}}"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content
        return clean_json_response(raw)
    except Exception as e:
        return json.dumps({"error": f"Eroare la generare raport: {str(e)}"})