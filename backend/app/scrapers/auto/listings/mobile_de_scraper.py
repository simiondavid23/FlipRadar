"""Mobile.de — anunturi auto (Germania). platform="mobile_de".

Mobile.de e protejat anti-bot: Akamai Bot Manager (identificat 2026-09; istoric Imperva).
Strategie: incercam intai curl_cffi (rapid), apoi cadem pe patchright cu Chrome real
(executa JS). MDE-1: calea HTTP e INCHISA — Akamai serveste o provocare JS de ~2,7 KB cu
HTTP 200 pe tot domeniul (CLS-1 o clasifica BLOCKED). Calea de browser trece complet.

Blocajul istoric NU era la nivel de IP: era detectie de AUTOMATIZARE — leak-uri CDP +
un user_agent hardcodat inconsistent cu Client Hints (Sec-Ch-Ua) trimise de Chrome real,
exact consistenta pe care o verifica zidul. Rezolvat prin patchright (patch la nivel de
binar) cu context MINIMAL fara stealth; confirmat live 2026-07 (pagina reala, zero markeri
de blocare). Proxy rezidential NU e necesar. Headless e detectat -> ruleaza
headed (pe VPS: xvfb-run).

Datele publice disponibile: titlu, an, km, pret (EUR), locatie, URL, thumbnail.
"""
import asyncio
import re
import urllib.parse

from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    MAX_LISTINGS, parse_price, extract_year, extract_km, make_listing,
    safe_soup, thumb_from_img,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters, AUTO_PLATFORM_CATEGORIES
from app.services.log_manager import log_manager
from app.services.radar.base_scraper import get_proxy_config

_SEARCH_URL = "https://suchen.mobile.de/fahrzeuge/search.html"
# „DE-14513 Teltow" din `seller-info`; se opreste la prima cifra (urmeaza „4 Sterne").
_RE_LOC_DE = re.compile(r"\bDE-(\d{5})\s+([^\d|•]+)")
# vehicleClass confirmat pe interfata publica (vc=Car). Doar valorile confirmate (Car/Motorbike).
_MOBILEDE_CATEGORIES = {c["value"] for c in AUTO_PLATFORM_CATEGORIES["mobile_de"] if c.get("value")}

# Set complet de headere de browser real — necesar ca mobile.de sa nu raspunda 403.
MOBILE_DE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;"
              "q=0.9,image/avif,image/webp,image/apng,*/*;"
              "q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", '
                 '"Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "upgrade-insecure-requests": "1",
    "cache-control": "max-age=0",
    "Connection": "keep-alive",
}

# Top marci -> makeId mobile.de (valori uzuale; pot necesita verificare per platforma).
MOBILE_DE_MAKE_IDS = {
    "Audi": "1900",
    "BMW": "3500",
    "Mercedes": "17200",
    "Mercedes-Benz": "17200",
    "Volkswagen": "25200",
    "Ford": "9000",
    "Opel": "19000",
    "Porsche": "20000",
    "Renault": "20700",
    "Peugeot": "19800",
    "Toyota": "24100",
    "Skoda": "22900",
    "Volvo": "25100",
    "Mazda": "16800",
    "Nissan": "18700",
    "Hyundai": "11600",
    "Kia": "13200",
    "Fiat": "8800",
    "Citroen": "5300",
    "Seat": "22500",
    "Honda": "11000",
    "Dacia": "6600",
}

# Aliase (chei lowercase) -> numele EXACT din MOBILE_DE_MAKE_IDS. DOAR pentru marci care
# EXISTA in dict (verificat): Volkswagen / Mercedes-Benz / Skoda. Nu inventam pt marci absente.
MOBILE_DE_MAKE_ALIASES = {
    "vw": "Volkswagen",
    "mercedes": "Mercedes-Benz",
    "mercedes benz": "Mercedes-Benz",
    "škoda": "Skoda",
}


# KA-1 — indexul case-insensitive, calculat O DATA la import (nu la fiecare apel).
_MAKE_IDS_LOWER = {k.lower(): v for k, v in MOBILE_DE_MAKE_IDS.items()}


def _resolve_make(make: str) -> str:
    """Numele marcii -> ID numeric mobile.de, sau "" daca nu se mapeaza. Functie pura.
    Ordine: strip -> alias pe lowercase -> potrivire case-insensitive -> "".
    (Un make_id deja numeric NU trece pe aici — search_mobile_de il paseaza direct.)

    KA-1: treapta finala era `.get(make.title())`, care rezolva "volkswagen" (-> cheia
    "Volkswagen") dar NU si "bmw": `.title()` da "Bmw", iar cheia din dictionar e "BMW".
    Masurat pe 2026-09-03: `_resolve_make("bmw")` intorcea "", deci `makeModelVariant1.
    makeId` nu se seta niciodata si cautarea mergea pe TOATE marcile, tacut. Cazul lovea
    orice cheie care nu e title-case.
    """
    make = (make or "").strip()
    if not make:
        return ""
    alias = MOBILE_DE_MAKE_ALIASES.get(make.lower())
    if alias:
        return MOBILE_DE_MAKE_IDS.get(alias, "")
    return _MAKE_IDS_LOWER.get(make.lower(), "")


def _build_params(make_id: str, filters: dict, page: int) -> dict:
    # mobile.de (search.html) pagineaza prin pageNumber, nu prin offset.
    params = {"damageUnrepaired": "false", "isSearchRequest": "true"}
    if page > 1:
        params["pageNumber"] = page
    if make_id:
        params["makeModelVariant1.makeId"] = make_id
    # Categorie -> vc (vehicleClass), doar valori confirmate (Car/Motorbike).
    cat = (filters.get("category") or "").strip()
    if cat in _MOBILEDE_CATEGORIES:
        params["vc"] = cat
    # Campuri confirmate pe interfata PUBLICA: fuel (ft, repeat), year (fr), price (p),
    # mileage (ml) — fr/p/ml sunt range-uri "MIN:MAX". ATENTIE: acestea INLOCUIESC complet
    # cheile vechi (price.min/price.max/minFirstRegistrationDate), nu se adauga pe langa ele.
    # Scanner-ul trimite "fuel"/"km_max" pentru fuel_type/mileage_max.
    apply_confirmed_filters("mobile_de", filters, params,
                            aliases={"fuel_type": "fuel", "mileage_max": "km_max"})
    return params


def _extract_price_mobile_de(card) -> tuple:
    """Returneaza (pret: float | None, moneda). Sursa reala confirmata pe DOM 2026-07:
    elementul [data-testid=price-label] al cardului (fallback main-price-label).

    JSON-LD pe mobile.de NU are Offer-uri per anunt (doar Organization + @graph), deci
    calea veche extract_ld_offers e moarta aici — nu mai cadem pe ea.
    """
    el = (card.select_one('[data-testid="price-label"]')
          or card.select_one('[data-testid="main-price-label"]'))
    if el is not None:
        p = parse_price(el.get_text(" ", strip=True))
        if p:
            return p, "EUR"
    return None, "EUR"


def _parse_mobilede_html(html: str) -> list:
    """Parseaza HTML-ul de rezultate (page.content() din patchright sau raspunsul curl) ->
    dict-uri make_listing. PRIMA validare pe DOM real din istoria parserului (2026-07):
    cardul e ANCORA <a href="/fahrzeuge/details.html?id=...>; selectorii/atributele vechi
    (.cBox-body--resultitem, [data-testid=result-list-item], [data-listing-id]) sunt MOARTE
    (mobile.de a trecut la clase ofuscate). [] daca pagina n-are carduri (challenge/gol).

    MDE-1 (masurat 2026-09-03, SONDA-MDE-B): ancora cardului a REZISTAT, dar ancora de
    TITLU a murit — `img.alt` e sirul gol pe toate cardurile si `aria-labelledby` nu mai
    exista, deci garda `if not titlu: continue` arunca tot. Efectul: pagina buna (1,36 MB,
    24 de carduri, zero markeri anti-bot) producea ZERO anunturi, tacut. Azi campurile
    stau pe `data-testid`, TOATE in interiorul ancorei (verificat: exact o ancora de
    detalii per <article>, deci ancora e containerul corect si cel mai ingust):
        [data-testid$="-title"]           -> "BMW X4 xDrive 20iA 184PS M-Paket ..."
        [data-testid="price-label"]       -> "27.999 €"
        [data-testid="listing-details"]   -> "EZ 01/2017 • 81.833 km • 135 kW (184 PS) • Benzin"
        [data-testid="seller-info"]       -> "Autohaus Klann GmbH DE-14513 Teltow 4 Sterne ( 172 )"
    Fallback-urile vechi (alt / aria-labelledby) RAMAN: DOM-ul din iulie e inca posibil
    pe alte pagini si e acoperit de testele AA-4.
    """
    soup = safe_soup(html)
    cards = (
        soup.select('a[href*="/fahrzeuge/details.html"]')   # confirmat pe DOM real 2026-07
        or soup.select(".cBox-body--resultitem")
        or soup.select('[data-testid="result-list-item"]')
        or soup.select("article")
        or soup.select("[data-listing-id]")
    )
    results, seen = [], set()
    fara_titlu = 0
    for card in cards:
        try:
            # cardul poate fi ANCORA insasi (selectorul nou) sau un container (fallback vechi)
            link = card if (card.name == "a" and card.get("href")) else card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = "https://suchen.mobile.de" + href
            # external_id din URL (?id=NNN) — data-listing-id nu mai exista pe DOM real.
            m = re.search(r"[?&]id=(\d+)", href)
            ext_id = m.group(1) if m else None
            if ext_id and ext_id in seen:
                continue

            # Titlu: `data-testid` care se termina in "-title" (DOM 2026-09), apoi
            # fallback-urile din iulie — alt-ul imaginii, apoi aria-labelledby.
            img = link.find("img")
            tnode = link.select_one('[data-testid$="-title"]')
            titlu = tnode.get_text(" ", strip=True) if tnode else ""
            if not titlu:
                titlu = (img.get("alt") or "").strip() if img else ""
            if not titlu:
                lb = link.get("aria-labelledby")
                lnode = link.find(id=lb) if lb else None
                titlu = lnode.get_text(" ", strip=True) if lnode else ""
            if not titlu:
                fara_titlu += 1
                continue
            if ext_id:
                seen.add(ext_id)

            # Specificatiile (an/km) stau in `listing-details`; il concatenam explicit,
            # ca extractia sa mearga si daca intr-un DOM viitor iese din card.
            card_text = card.get_text(" ", strip=True)
            spec = link.select_one('[data-testid="listing-details"]')
            if spec is not None:
                card_text = f"{card_text} {spec.get_text(' ', strip=True)}"
            pret, moneda = _extract_price_mobile_de(link)
            # Km: scoate consumul "N l/100km" INAINTE de extractie, altfel "5,7 l/100km"
            # produce km=100 fals (confirmat pe DOM real la un Neuwagen fara kilometraj).
            km_text = re.sub(r"\d[\d.,]*\s*l\s*/\s*100\s*km", " ", card_text, flags=re.I)

            results.append(make_listing(
                platform="mobile_de", external_id=ext_id, titlu=titlu,
                year=extract_year(titlu) or extract_year(card_text),
                km=extract_km(km_text), pret=pret, moneda=moneda,
                locatie=_locatie_din_card(link), source_url=href,
                thumbnail_url=thumb_from_img(img) or None,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[mobile_de] card parse error: {exc}")
            continue
    if fara_titlu and not results:
        # Semnalul lipsea la MDE-1: pagina buna, 24 de carduri, toate aruncate pe garda
        # de titlu — si niciun cuvant nicaieri. Acum ajunge in `zgomot`-ul auditului.
        print(f"[mobile_de] {fara_titlu} carduri fara titlu (markup schimbat?)")
    return results[:MAX_LISTINGS]


def _locatie_din_card(link) -> str:
    """„14513 Teltow" din `seller-info` („Autohaus Klann GmbH DE-14513 Teltow 4 Sterne").
    Numele dealerului NU se pastreaza — n-avem camp pentru el si nu-l vrem."""
    el = link.select_one('[data-testid="seller-info"]')
    if el is not None:
        m = _RE_LOC_DE.search(el.get_text(" ", strip=True))
        if m:
            return f"{m.group(1)} {m.group(2).strip()}"
    return "Germania"


def _search_mobile_de_playwright(url: str, page: int) -> list:
    """Fallback patchright — executa JS si trece de detectia anti-bot.

    Blocajul istoric era detectie de AUTOMATIZARE (leak-uri CDP + user_agent hardcodat
    inconsistent cu Client Hints), NU blocaj de IP. Rezolvat prin patchright cu Chrome real
    + context MINIMAL fara stealth; confirmat live 2026-07. Proxy rezidential NU e necesar.
    Functie SINCRONA; apelata din async prin asyncio.to_thread.
    """
    results = []
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("auto_listings", "ERR", "Mobile.de: patchright nu e instalat")
        return results

    proxy_cfg = get_proxy_config()
    context_kwargs = {}
    if proxy_cfg:
        proxy_arg = {"server": f"http://{proxy_cfg['host']}:{proxy_cfg['port']}"}
        if proxy_cfg["username"]:
            proxy_arg["username"] = proxy_cfg["username"]
            proxy_arg["password"] = proxy_cfg["password"]
        context_kwargs["proxy"] = proxy_arg
        log_manager.emit("auto_listings", "INFO", "Mobile.de patchright: folosesc proxy configurat")

    try:
        with sync_playwright() as p:
            # Chrome real (channel=chrome) — cheia consistentei UA/Client Hints; fallback pe
            # Chromium bundled de patchright daca Chrome nu e instalat (nu crapa scanul).
            try:
                browser = p.chromium.launch(headless=False, channel="chrome")
                log_manager.emit("auto_listings", "INFO", "Mobile.de: patchright cu Chrome real")
            except Exception:
                browser = p.chromium.launch(headless=False)
                log_manager.emit("auto_listings", "INFO",
                    "Mobile.de: Chrome real indisponibil, fallback Chromium bundled")
            # Context minimal intentionat: UA custom strica consistenta cu Client Hints
            # (Sec-Ch-Ua) verificata de zid; configul asta e cel validat live 2026-07.
            # headless=False obligatoriu: zidul detecteaza headless (confirmat live) — pe VPS
            # ruleaza cu xvfb-run; pe PC-ul de dev apare o fereastra Chrome la scanarile mobile.de.
            context = browser.new_context(**context_kwargs)
            pw_page = context.new_page()
            try:
                pw_page.goto(url, wait_until="domcontentloaded", timeout=45000)
                pw_page.wait_for_timeout(6000)
                try:
                    pw_page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass

                # Pagina de blocare -> 0 rezultate.
                body_head = pw_page.inner_text("body")[:400].lower()
                if any(m in body_head for m in ("access denied", "zugriff verweigert", "captcha")):
                    log_manager.emit("auto_listings", "WARN",
                        "Mobile.de: blocat (fingerprint automatizare) "
                        "— verifica versiunile patchright/Chrome")
                    return results

                # Parsam DIRECT din page.content() cu parserul BS4 unificat (acelasi ca la curl).
                # Bannerul GDPR NU ascunde cardurile din DOM (confirmat live) -> parsam intai fara
                # interactiune; DOAR daca nu apar carduri, refuzam tracking-ul (Ablehnen) o data.
                results = _parse_mobilede_html(pw_page.content())
                if not results:
                    for sel in ("button:has-text('Ablehnen')", "text=Ablehnen"):
                        try:
                            pw_page.click(sel, timeout=3000)
                            break
                        except Exception:
                            continue
                    pw_page.wait_for_timeout(1500)
                    results = _parse_mobilede_html(pw_page.content())
            except Exception as exc:
                log_manager.emit("auto_listings", "ERR",
                    f"Mobile.de patchright eroare: {str(exc)[:100]}")
            finally:
                browser.close()
    except Exception as exc:
        log_manager.emit("auto_listings", "ERR",
            f"Mobile.de patchright init: {str(exc)[:100]}")

    # OK-ul se emite in search_mobile_de (dupa post-filtrul de relevanta model/query).
    return results[:MAX_LISTINGS]


def _relevant_title(title: str, model: str, query: str) -> bool:
    """Plasa de siguranta de relevanta: titlul normalizat contine TOATE tokenurile din `model`
    SI din `query`. Normalizare pe ambele parti: lowercase, virgula->punct, spatii colapsate
    (deci '1,6 TDI' din anunt trece pentru query '1.6 TDI'). model+query goale -> True.
    """
    def _norm(s):
        return re.sub(r"\s+", " ", (s or "").lower().replace(",", ".")).strip()
    t = _norm(title)
    tokens = _norm(model).split() + _norm(query).split()
    return all(tok in t for tok in tokens)


async def search_mobile_de(make_id: str = "", model: str = "", query: str = "",
                           filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    # Permite trimiterea numelui marcii in loc de ID (ex: "BMW"/"vw"). Rezolvare pura cu aliase.
    if make_id and not make_id.isdigit():
        resolved = _resolve_make(make_id)
        if not resolved:
            log_manager.emit("auto_listings", "INFO",
                f"Mobile.de: marca '{make_id}' nu e in lista mapata — caut pe toate marcile")
        make_id = resolved

    params = _build_params(make_id, filters, page)
    # Model -> modelDescription (confirmat live 2026-07: 24/24 titluri contineau 'Passat').
    # Restrange la modelul cerut inainte de fetch; plasa de siguranta ramane post-filtrul.
    if model:
        params["makeModelVariant1.modelDescription"] = model
    # doseq=True: "ft" poate fi lista (query_repeat) -> ft=PETROL&ft=DIESEL; string-urile
    # raman intregi (doseq NU itereaza str-uri, doar liste/tuple).
    url = _SEARCH_URL + "?" + urllib.parse.urlencode(params, doseq=True)
    log_manager.emit("auto_listings", "SCAN",
        f"Mobile.de: cautare make_id={make_id or '-'} model='{model or '-'}' pagina {page}")

    # 1) curl_cffi cu chrome124 + headere complete (rapid). 2) fallback patchright.
    results = []
    headers = {**MOBILE_DE_HEADERS, "Referer": "https://www.mobile.de/"}
    proxy_cfg = get_proxy_config()
    req_kwargs = {"params": params, "headers": headers, "impersonate": "chrome124", "timeout": 20}
    if proxy_cfg:
        req_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}
        log_manager.emit("auto_listings", "INFO", "Mobile.de: folosesc proxy configurat")
    try:
        async with AsyncSession() as session:
            resp = await session.get(_SEARCH_URL, **req_kwargs)
        if resp.status_code == 200:
            results = _parse_mobilede_html(resp.text)   # gol daca e pagina-challenge -> fallback
        else:
            print(f"[mobile_de] curl HTTP {resp.status_code} → fallback patchright")
    except Exception as exc:
        print(f"[mobile_de] curl error: {exc} → fallback patchright")
    if not results:
        # Rulat intr-un thread ca sync_playwright sa nu intre in conflict cu event loop-ul asyncio.
        results = await asyncio.to_thread(_search_mobile_de_playwright, url, page)

    # 3) Post-filtru de relevanta pe titlu (model + query) — plasa de siguranta, indiferent daca
    # mobile.de a onorat modelDescription; feed-ul nu mai contine alte modele ale marcii.
    relevant = [r for r in results if _relevant_title(r.get("titlu") or "", model, query)]
    log_manager.emit("auto_listings", "OK",
        f"Mobile.de: {len(results)} rezultate pagina {page} "
        f"({len(relevant)} relevante dupa filtrul model/query)")
    return relevant
