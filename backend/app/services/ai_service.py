import re
import json
import asyncio
from groq import Groq
from app.config import GROQ_API_KEY

# Configurare client Groq
client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.3-70b-versatile"


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


async def chat_with_groq(message: str, system_prompt: str = "", history: list = None) -> str:
    """Trimite un mesaj la Groq și returnează răspunsul."""
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": message})

        # FlipRadar — BUG 5: ruleaza apelul blocant Groq intr-un thread separat,
        # ca sa nu blocheze event loop-ul async.
        response = await asyncio.to_thread(
            client.chat.completions.create,
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
    resale_price: float | None = None,
    market_context: str = "",
) -> str:
    """Analizează un produs pentru revânzare pe piețele second-hand din România.

    Adaptat pentru OLX / Vinted / Facebook Marketplace — nu menționează Amazon
    sau alte marketplace-uri în afara scopului suportat.
    """
    greeting = f"Analizezi acest produs pentru {user_name}." if user_name else ""

    if resale_price and price and price > 0:
        marja_value = float(resale_price) - float(price)
        roi_value = (marja_value / float(price)) * 100.0
        resale_line = f"PRET ESTIMAT REVANZARE: {resale_price} {currency}"
        margin_line = (
            f"MARJA BRUTA ESTIMATA: {round(marja_value, 2)} {currency} "
            f"({round(roi_value, 1)}% ROI)"
        )
    else:
        resale_line = "PRET ESTIMAT REVANZARE: necunoscut"
        margin_line = "MARJA BRUTA ESTIMATA: necunoscuta — propune o sugestie de pret"

    prompt = f"""Esti un expert in flipping si arbitraj pe pietele second-hand din Romania.
Analizeaza acest produs pentru potentialul de revanzare pe OLX, Vinted sau Facebook Marketplace.

{greeting}

PRODUS: {product_name}
CATEGORIE: {category if category else "Nespecificata"}
PRET ACHIZITIE: {price if price else "Nespecificat"} {currency}
{resale_line}
{margin_line}
SURSA ACHIZITIE: {source if source else "Nespecificat"}

Analizeaza tinand cont de:
- Cererea tipica pentru aceasta categorie pe piata second-hand din Romania
- Viteza de vanzare estimata (cate zile pana la vanzare)
- Nivelul de concurenta pe OLX / Vinted / Facebook Marketplace pentru produse similare
- Sezonalitatea categoriei in Romania
- Riscurile specifice: dificultate de vanzare, depreciere rapida, produse greu de expediat
- Daca pretul de achizitie lasa marja reala dupa costurile de livrare (~15-25 RON pentru curier in Romania)

Returneaza STRICT JSON valid fara text in afara JSON-ului si fara markdown:
{{
    "verdict": "RECOMANDAT" | "NERECOMANDAT" | "CU REZERVE",
    "score": <numar intreg 1-10>,
    "roi_estimat": <numar reprezentand procentul ROI, 0 daca resale_price necunoscut>,
    "viteza_vanzare": "rapida (1-7 zile)" | "medie (1-4 saptamani)" | "lenta (1-3 luni)",
    "nivel_concurenta": "scazut" | "mediu" | "ridicat",
    "sezonalitate": "<text scurt, max 15 cuvinte>",
    "riscuri": ["<risc 1>", "<risc 2>", "<risc 3>"],
    "platforme_recomandate": ["OLX", "Vinted", "Facebook Marketplace"],
    "sfat_pret_revanzare": "<text scurt cu sugestie de pret daca resale_price lipseste, altfel comentariu despre prezentul pret>",
    "recomandare_finala": "<text de 2-3 propozitii cu recomandarea concreta>",
    "sumar": "<o singura propozitie rezumat>",
    "scor_profitabilitate": <numar 1-10 — alias pentru score, pentru compatibilitate UI>,
    "demand_score": <numar 1-10>,
    "explicatie_demand": "<o propozitie despre cererea estimata>",
    "nivel_competitie": "<scazut | mediu | ridicat — alias pentru nivel_concurenta>",
    "explicatie_competitie": "<o propozitie despre concurenta pe OLX/Vinted>",
    "explicatie_sezonalitate": "<o propozitie despre cand se vinde cel mai bine>",
    "factori_risc": ["<copie din riscuri>"],
    "explicatie_verdict": "<explicatie 2-3 propozitii a verdictului>",
    "pret_achizitie_eur": <pret achizitie convertit in EUR (foloseste curs ~5 RON/EUR daca este RON)>,
    "pret_vanzare_estimat": <pret estimat de revanzare in EUR>,
    "profit_brut_eur": <profit brut estimat in EUR>,
    "costuri_operationale_eur": <estimare costuri livrare + ambalare in EUR>,
    "profit_net_eur": <profit net dupa costuri in EUR>,
    "marja_neta_pct": <procentaj marja neta, 1 zecimala>,
    "roi_pct": <procentaj ROI, 1 zecimala>,
    "sfaturi": ["<sfat actionabil 1>", "<sfat actionabil 2>", "<sfat actionabil 3>"]
}}"""

    # FlipRadar — ITEM 14: ancoram analiza in date reale de piata cand sunt disponibile.
    if market_context:
        prompt += f"\n{market_context}"

    try:
        # FlipRadar — BUG 5: apel blocant Groq rulat in thread separat.
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content
        return clean_json_response(raw)
    except Exception as e:
        return json.dumps({"error": f"Eroare la analiza: {str(e)}"})


# FlipRadar — ITEM 13: cauta specificatii tehnice online cand utilizatorul nu le ofera.
async def fetch_product_specs_online(product_name: str, category: str = "") -> str:
    import httpx
    from bs4 import BeautifulSoup
    query = f"{product_name} {category} specificatii tehnice".strip()
    encoded = query.replace(" ", "+")
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        snippets = soup.find_all("a", class_="result__snippet")
        context = " | ".join(s.text.strip() for s in snippets[:3])
        return context[:1500]
    except Exception:
        return ""


async def generate_product_listing(
    product_name: str,
    category: str = "",
    features: str = "",
    price: float = 0,
    currency: str = "EUR",
    user_name: str = "",
    product_condition: str = "Nou",
    target_platform: str = "OLX",
) -> str:
    """Generează un anunț optimizat de produs pentru piețele second-hand."""
    byline = (
        f"Pregatesti anuntul pentru {user_name}, un vanzator care foloseste FlipRadar "
        f"pentru a gasi produse de revanzare pe piata second-hand din Romania."
    ) if user_name else ""

    condition_clean = (product_condition or "Nou").strip()
    platform_clean = (target_platform or "OLX").strip()

    if condition_clean.lower().startswith("second"):
        condition_instructions = (
            "Produsul este SECOND HAND. Fii transparent in anunt despre uzura: mentioneaza "
            "starea reala (urme de utilizare normale, fara defecte majore daca e cazul), "
            "evidentiaza raportul calitate/pret si motivul pentru care merita cumparat la "
            "acest pret fata de unul nou."
        )
        price_instructions = (
            "Sugereaza un pret realist pentru un produs second hand, cu mentiunea ca produsul "
            "este verificat si functional."
        )
    elif condition_clean.lower().startswith("negociabil"):
        condition_instructions = (
            "Produsul este NEGOCIABIL. Mentioneaza explicit in anunt ca pretul este negociabil "
            "si invita cumparatorul sa propuna o oferta."
        )
        price_instructions = (
            "Sugereaza un pret de listing usor mai mare decat cel dorit (cu ~10-15%) pentru a "
            "lasa marja de negociere. Mentioneaza in anunt 'pret negociabil'."
        )
    else:
        condition_instructions = (
            "Produsul este NOU (sigilat sau in ambalaj original). Mentioneaza acest aspect "
            "clar in anunt si evidentiaza beneficiile cumpararii unui produs nou (garantie, "
            "ambalaj original, fara uzura)."
        )
        price_instructions = "Sugereaza un pret competitiv comparativ cu alte oferte similare."

    if platform_clean.lower() == "vinted":
        platform_instructions = (
            "Stilul anuntului trebuie sa fie CASUAL si SCURT, specific platformei Vinted. "
            "Foloseste un ton prietenos, putine bullet point-uri, descriere de 100-200 cuvinte. "
            "Evidentiaza marimea (daca e haine), starea si motivul vanzarii."
        )
    elif "facebook" in platform_clean.lower():
        platform_instructions = (
            "Stilul anuntului trebuie sa fie CONVERSATIONAL, fara bullet points, specific "
            "platformei Facebook Marketplace. Foloseste paragrafe scurte, ton prietenos, "
            "include detalii practice: livrare/ridicare, locatie, contact rapid."
        )
    else:
        platform_instructions = (
            "Stilul anuntului trebuie sa fie STRUCTURAT, cu specificatii tehnice clare, "
            "specific platformei OLX. Include sectiuni: descriere, specificatii, conditii "
            "de livrare. Foloseste bullet points pentru caracteristici."
        )

    prompt = f"""Esti un expert in copywriting pentru piete second-hand din Romania: OLX, Vinted si Facebook Marketplace.
{byline}
Genereaza un anunt complet si optimizat pentru urmatorul produs:

Produs: {product_name}
Categorie: {category if category else "Nespecificata"}
Caracteristici: {features if features else "Nespecificate"}
Pret orientativ: {price if price else "Nespecificat"} {currency}
Stare produs: {condition_clean}
Platforma tinta: {platform_clean}

INSTRUCTIUNI STARE PRODUS:
{condition_instructions}
{price_instructions}

INSTRUCTIUNI PLATFORMA:
{platform_instructions}

Raspunde STRICT in format JSON valid (fara markdown, fara ```), cu urmatoarea structura:
{{
    "titlu": "<titlu adaptat platformei {platform_clean}, max 200 caractere, cu cuvinte cheie relevante>",
    "bullet_points": [
        "<bullet point 1 - beneficiu principal>",
        "<bullet point 2 - caracteristica cheie>",
        "<bullet point 3 - material/calitate>",
        "<bullet point 4 - utilizare/compatibilitate>",
        "<bullet point 5 - garantie/bonus>"
    ],
    "descriere": "<descriere adaptata stilului platformei {platform_clean}, intre 150-500 cuvinte in functie de platforma>",
    "cuvinte_cheie": ["<cuvant1>", "<cuvant2>", "<cuvant3>", "<cuvant4>", "<cuvant5>"],
    "sfaturi_listing": [
        "<sfat 1 specific platformei {platform_clean}>",
        "<sfat 2 pentru cresterea sanselor de vanzare>"
    ]
}}"""

    # FlipRadar — ITEM 13: daca utilizatorul a oferit caracteristici prea scurte,
    # cautam specificatii tehnice online si le adaugam ca context optional in prompt.
    if len((features or "").strip()) < 40:
        specs = await fetch_product_specs_online(product_name, category)
        if specs:
            prompt += f"\nInformatii tehnice gasite online (foloseste-le daca sunt relevante si corecte):\n{specs}"

    try:
        # FlipRadar — BUG 5: apel blocant Groq rulat in thread separat.
        response = await asyncio.to_thread(
            client.chat.completions.create,
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
    """Generează un raport de activitate cu AI, personalizat pentru utilizatorul curent."""
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
        # FlipRadar — BUG 5: apel blocant Groq rulat in thread separat.
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content
        return clean_json_response(raw)
    except Exception as e:
        return json.dumps({"error": f"Eroare la generare raport: {str(e)}"})


async def extract_auto_features_from_description(description: str, existing_data: dict = {}) -> dict:
    """Extrage informatii structurate din descrierea unui anunt auto."""
    if not description or len(description) < 50:
        return {}

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
            model=MODEL,
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