"""Facebook Marketplace — categoria Property Rentals (chirii imobiliare).

Reutilizeaza aceeasi sesiune autentificata ca facebook_auto_scraper (storage_state
Playwright salvat in data/facebook_session_{user_id}.json). Functie SINCRONA — la
fel ca facebook_auto, dispecerul din real_estate_scanner o apeleaza DIRECT, nu prin
asyncio.run (sync_playwright nu poate rula intr-un event loop asyncio).
"""
import json
import re
import urllib.parse
from typing import Optional

from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES, RE_PROPERTY_TYPES

_CATEGORY_SLUGS = {"vanzare": "propertyforsale", "inchiriere": "propertyrentals"}


def _category_url(tip_anunt: str) -> str:
    slug = _CATEGORY_SLUGS.get((tip_anunt or "inchiriere").lower(), "propertyrentals")
    return f"https://www.facebook.com/marketplace/category/{slug}/"


def _parse_price(raw: str) -> Optional[float]:
    """SCRAPE-AUDIT: replace-ul orb facea "RON 1,500" -> 1.5 (Marketplace foloseste
    frecvent formatul EN cu virgula de mii). Virgula in grupuri de 3 = mii."""
    cleaned = re.sub(r"[^\d.,]", "", raw or "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", cleaned):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


# SCRAPE-1d: o linie de card e candidat de PRET doar daca poarta valuta explicit.
# Vechiul criteriu re.match(r"^\d", line) lua orice linie care incepe cu o cifra —
# titlul "2 camere de inchiriat, mobilat" iesea ca price=2.0 si impingea pretul real
# in pozitia de titlu. Lookaround-ul (?<![^\W\d_]) = "nu e lipit de o litera" (unicode,
# deci si diacriticele romanesti): prinde "1500lei" dar nu "Aleile" sau "leilor".
_CUR_TOKEN = r"(?:€|(?<![^\W\d_])(?:euro|eur|ron|lei)(?![^\W\d_]))"
_EUR_CURRENCY_RE = re.compile(r"€|(?<![^\W\d_])(?:euro|eur)(?![^\W\d_])", re.IGNORECASE)

# FBM-1b, pasul 1: linie PUR pret — toata linia e numar + valuta (+ perioada
# optionala): "350 €", "€350", "RON 1,500", "1.500 lei / luna".
_PURE_PRICE_RE = re.compile(
    rf"^\s*(?P<pre>{_CUR_TOKEN})?\s*(?P<num>\d[\d.,\s]*?)\s*(?P<post>{_CUR_TOKEN})?"
    rf"\s*(?:[/·]|\bpe\b)?\s*(?:lun[aă]|luna|month|mo)?\s*$", re.IGNORECASE)

# FBM-1b, pasul 2: numarul LIPIT de valuta, in ambele ordini. Pe "2 camere, 350 €/luna"
# da 350, spre deosebire de _parse_price pe toata linia care lipea cifrele in "2,350".
_ADJACENT_PRICE_RE = re.compile(
    rf"(?P<pre_cur>{_CUR_TOKEN})\s*(?P<num_after>\d[\d.,]*)"
    rf"|(?P<num_before>\d[\d.,]*)\s*(?P<post_cur>{_CUR_TOKEN})", re.IGNORECASE)


def _parse_card_lines(lines: list) -> tuple:
    """Imparte liniile unui card Marketplace in (price, currency, title, location).

    Pas 1: prima linie PUR pret da pretul si se CONSUMA (nu mai poate ajunge titlu).
    Pas 2 (fallback, doar daca nu exista linie pur-pret): pretul se citeste din
    substringul lipit de valuta intr-o linie oarecare — e aproape sigur titlul cu
    pretul inclus, deci linia NU se consuma si ramane candidata la titlu.
    Moneda se decide pe pretul gasit, nu pe tot textul cardului.
    """
    price = None
    currency = None
    consumed = None

    for i, line in enumerate(lines):
        m = _PURE_PRICE_RE.match(line)
        if not m or not (m.group("pre") or m.group("post")):
            continue                      # fara valuta explicita nu e pret
        pv = _parse_price(m.group("num"))
        if pv is not None and pv > 0:
            price = pv
            currency = "EUR" if _EUR_CURRENCY_RE.search(line) else "RON"
            consumed = i
            break

    if price is None:
        for line in lines:
            m = _ADJACENT_PRICE_RE.search(line)
            if not m:
                continue
            pv = _parse_price(m.group("num_after") or m.group("num_before"))
            if pv is not None and pv > 0:
                price = pv
                tok = m.group("pre_cur") or m.group("post_cur")
                currency = "EUR" if _EUR_CURRENCY_RE.search(tok) else "RON"
                break

    title = ""
    location = None
    for i, line in enumerate(lines):
        if i == consumed:
            continue
        if not title and not re.match(r"^[\d.,]+$", line):
            title = line
            continue
        if not location:
            location = line
    return price, currency, title, location


# FBM-1c: browserul pornea fara nicio masca — user-agent "HeadlessChrome/141.0" si
# navigator.webdriver=true. Scanul ruleaza periodic din scheduler pe storage_state-ul
# contului REAL, deci fiecare rulare anunta "sunt bot" cu sesiunea utilizatorului
# (profil clasic de checkpoint pe cont). Masca e copiata de la facebook_group_scraper,
# care o are deja — tinem cele trei constante la nivel de modul ca sa fie verificabile
# fara browser.
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

_CONTEXT_KWARGS = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1366, "height": 768},
    "locale": "ro-RO",
}

_STEALTH_INIT_JS = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            window.chrome = {runtime: {}};
        """


def search_facebook_real_estate(query: str = "", filters: dict = {}) -> list:
    from app.services.log_manager import log_manager
    from app.scrapers.auto.listings.facebook_auto_scraper import (
        _find_session_file, _is_session_valid)
    filters = filters or {}

    # GUARD: nu porni scan pe o categorie NECONFIRMATA (ex. propertyforsale/vanzare —
    # intoarce doar Partner listings/electronice+chirii, nu vanzari imobiliare reale).
    # Vezi re_categories.RE_PROPERTY_TYPES["facebook_real_estate"]["categorie_tip_anunt"].
    tip_anunt = (filters.get("tip_anunt") or "inchiriere").lower()
    spec = RE_PROPERTY_TYPES["facebook_real_estate"]["categorie_tip_anunt"].get(tip_anunt)
    if not spec or not spec.get("confirmed"):
        log_manager.emit("real_estate", "WARN",
            f"Facebook RE: categoria pentru tip_anunt='{tip_anunt}' e neconfirmata "
            f"(vezi re_categories.RE_PROPERTY_TYPES) — scan omis, 0 rezultate.")
        return []

    session_path = _find_session_file()
    if not session_path or not _is_session_valid(session_path):
        log_manager.emit("real_estate", "WARN",
            "Facebook RE: sesiune expirata sau inexistenta. "
            "Reautentifica-te din Setari Radar → Facebook.")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("real_estate", "ERR", "Facebook RE: Playwright nu e instalat.")
        return []

    params = {}
    if query:
        params["query"] = query
    # Doar minPrice/maxPrice sunt confirmate (comportament existent). Filtrele de dormitoare/
    # bai/suprafata exista in UI dar au NUMELE param neverificat -> NECONECTATE (re_categories).
    apply_re_filters("facebook_real_estate", filters, params, aliases=RE_FILTER_ALIASES)
    url = _category_url(filters.get("tip_anunt")) + ("?" + urllib.parse.urlencode(params) if params else "")

    log_manager.emit("real_estate", "SCAN", f"Facebook RE Playwright: {query!r}")

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    storage = json.load(f)
                context = browser.new_context(storage_state=storage, **_CONTEXT_KWARGS)
            except Exception:
                context = browser.new_context(**_CONTEXT_KWARGS)
            # Ascunde indicatorii de automatizare (ambele ramuri de context).
            context.add_init_script(_STEALTH_INIT_JS)
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(4000)
                if "login" in page.url.lower():
                    log_manager.emit("real_estate", "WARN",
                        "Facebook RE: login wall — reconecteaza-te.")
                    return []
                for _ in range(2):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(800)

                items = page.query_selector_all('a[href*="/marketplace/item/"]')
                log_manager.emit("real_estate", "INFO",
                    f"Facebook RE: {len(items)} carduri gasite")

                seen = set()
                for it in items[:40]:
                    try:
                        href = it.get_attribute("href") or ""
                        full = href if href.startswith("http") else f"https://www.facebook.com{href}"
                        full = full.split("?")[0]
                        if "/marketplace/item/" not in full or full in seen:
                            continue
                        seen.add(full)
                        m = re.search(r"/marketplace/item/(\d+)", full)
                        if not m:
                            continue
                        ext_id = m.group(1)

                        text = (it.inner_text() or "").strip()
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        price, currency, title, location = _parse_card_lines(lines)
                        if not title:
                            continue
                        # Fara pret pe card nu putem aplica price_min/max ale keyword-ului
                        # (toleranta din _matches_re_keyword lasa sa treaca orice) —
                        # precedentul Radar/SCRAPE-1a: fara pret => skip. Chiriile au
                        # aproape intotdeauna pretul pe card.
                        if price is None or price <= 0:
                            continue
                        # Scannerul trimite cheia "pret_max" (nu "price_max"); acceptam ambele.
                        pmax = filters.get("pret_max") or filters.get("price_max")
                        if pmax and price and price > float(pmax):
                            continue

                        img_el = it.query_selector("img")
                        thumb = (img_el.get_attribute("src") or img_el.get_attribute("data-src")) if img_el else ""

                        results.append({
                            "external_id":   ext_id,
                            "title":         title,
                            "price":         price,
                            "currency":      currency,
                            "location":      location,
                            "url":           full,
                            "source_url":    full,
                            "thumbnail_url": thumb or "",
                            "platform":      "facebook_marketplace",
                        })
                        if len(results) >= 30:
                            break
                    except Exception:
                        continue
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        log_manager.emit("real_estate", "ERR",
            f"Facebook RE Playwright eroare: {str(exc)[:100]}")

    log_manager.emit("real_estate", "OK",
        f"Facebook RE: {len(results)} rezultate pentru {query!r}")
    return results
