"""Mobile.de — anunturi auto (Germania). platform="mobile_de".

Mobile.de e protejat anti-bot (Imperva): requesturile simple primesc 403 sau o
pagina-challenge JS (HTTP 200 fara continut). Strategie: incercam intai curl_cffi
cu impersonate="chrome124" + set complet de headere (rapid, daca trece), apoi
cadem pe Playwright (executa JS, trece de challenge). Daca si Playwright e blocat,
e blocaj la nivel de IP — necesita proxy rezidential.

Datele publice disponibile: titlu, an, km, pret (EUR), locatie, URL, thumbnail.
"""
import asyncio
import re
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.scrapers.auto.listings._common import (
    MAX_LISTINGS, parse_price, extract_ld_offers,
    extract_year, extract_km, make_listing,
)
from app.scrapers.auto.listings.auto_categories import apply_confirmed_filters
from app.services.log_manager import log_manager

_SEARCH_URL = "https://suchen.mobile.de/fahrzeuge/search.html"

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


def _build_params(make_id: str, filters: dict, page: int) -> dict:
    # mobile.de (search.html) pagineaza prin pageNumber, nu prin offset.
    params = {"damageUnrepaired": "false", "isSearchRequest": "true"}
    if page > 1:
        params["pageNumber"] = page
    if make_id:
        params["makeModelVariant1.makeId"] = make_id
    if filters.get("price_max") is not None:
        params["price.max"] = int(float(filters["price_max"]))
    if filters.get("price_min") is not None:
        params["price.min"] = int(float(filters["price_min"]))
    if filters.get("year_min") is not None:
        params["minFirstRegistrationDate"] = int(filters["year_min"])
    # Campuri tehnice confirmate (mobile_de: fuel, gearbox, power kW, drivetrain).
    # NOTA: numele oficiale vin din Search API autentificat; pe interfata publica
    # (suchen.mobile.de) pot diferi — de verificat live (vezi NOTA din auto_categories.py).
    # Scanner-ul trimite "fuel" pentru fuel_type; "gearbox" coincide cu cheia campului.
    apply_confirmed_filters("mobile_de", filters, params, aliases={"fuel_type": "fuel"})
    return params


def _extract_price_mobile_de(card, ld_offers=None, card_idx=0) -> tuple:
    """Returneaza (pret: float | None, moneda). Nu cade niciodata pe textul cardului.

    Cand pagina e accesibila luam pretul intai din JSON-LD (asociat pe pozitie),
    apoi dintr-un element de pret dedicat.
    """
    # Strategy A — JSON-LD, asociat pe pozitie.
    if ld_offers and card_idx < len(ld_offers):
        offer = ld_offers[card_idx]
        p = parse_price(str(offer.get("price") or ""))
        if p:
            return p, offer.get("currency") or "EUR"

    # Strategy B — element de pret (data-price/content/text), niciodata tot cardul.
    el = (card.find(attrs={"data-testid": re.compile(r"price", re.I)})
          or card.find(class_=re.compile(r"price", re.I)))
    if el is not None:
        raw = el.get("data-price") or el.get("content") or el.get_text(" ", strip=True)
        p = parse_price(str(raw))
        if p:
            return p, "EUR"

    return None, "EUR"


def _parse_mobilede_html(html: str) -> list:
    """Parseaza HTML-ul de cautare (calea curl) -> dict-uri make_listing.
    Intoarce [] daca pagina e o pagina-challenge (fara carduri)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select(".cBox-body--resultitem")
        or soup.select('[data-testid="result-list-item"]')
        or soup.select("article")
        or soup.select("[data-listing-id]")
    )
    ld_offers = extract_ld_offers(soup)
    results = []
    for idx, card in enumerate(cards):
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = "https://suchen.mobile.de" + href

            title_el = card.find(["h2", "h3"]) or card.find(class_=re.compile(r"title|headline", re.I)) or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            card_text = card.get_text(" ", strip=True)
            # Pret din JSON-LD/element de pret; niciodata din textul cardului.
            pret, _ = _extract_price_mobile_de(card, ld_offers, idx)

            loc_el = card.find(class_=re.compile(r"location|seller", re.I))
            locatie = loc_el.get_text(" ", strip=True) if loc_el else None

            img = card.find("img")
            thumb = (img.get("src") or img.get("data-src")) if img else None

            results.append(make_listing(
                platform="mobile_de", external_id=card.get("data-listing-id"), titlu=titlu,
                year=extract_year(titlu) or extract_year(card_text), km=extract_km(card_text),
                pret=pret, moneda="EUR", locatie=locatie or "Germania",
                source_url=href, thumbnail_url=thumb,
            ))
            if len(results) >= MAX_LISTINGS:
                break
        except Exception as exc:
            print(f"[mobile_de] card parse error: {exc}")
            continue
    return results[:MAX_LISTINGS]


def _search_mobile_de_playwright(url: str, page: int) -> list:
    """Fallback Playwright — executa JS si trece de challenge-ul anti-bot.
    Mobile.de NU cere autentificare, deci nu e nevoie de sesiune salvata.
    Functie SINCRONA (sync_playwright); apelata din async prin asyncio.to_thread.
    """
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_manager.emit("auto_listings", "ERR", "Mobile.de: Playwright nu e instalat")
        return results

    # playwright-stealth 2.x expune clasa Stealth (use_sync); aplica stealth
    # automat fiecarei pagini noi. Daca lipseste, cadem pe sync_playwright simplu.
    try:
        from playwright_stealth import Stealth
        _ctx = lambda: Stealth().use_sync(sync_playwright())
    except Exception:
        _ctx = sync_playwright

    try:
        with _ctx() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="de-DE",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            pw_page = context.new_page()
            try:
                pw_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                pw_page.wait_for_timeout(3000)

                # Pagina de blocare (Imperva) → 0 rezultate, necesita proxy.
                body_text = pw_page.inner_text("body")[:300].lower()
                if any(m in body_text for m in (
                        "access denied", "zugriff verweigert", "captcha")):
                    log_manager.emit("auto_listings", "WARN",
                        "Mobile.de: blocat chiar și cu Playwright "
                        "— necesită proxy rezidențial")
                    return results

                CARD_SELECTORS = [
                    "article.cBox-body",
                    "[data-testid='result-listing']",
                    ".result-list-entry",
                    ".cBox-body--resultitem",
                    "article",
                ]
                cards = []
                for sel in CARD_SELECTORS:
                    cards = pw_page.query_selector_all(sel)
                    if len(cards) > 2:
                        log_manager.emit("auto_listings", "INFO",
                            f"Mobile.de: {len(cards)} carduri cu selector '{sel}'")
                        break

                if not cards:
                    log_manager.emit("auto_listings", "WARN",
                        "Mobile.de Playwright: niciun card găsit")
                    return results

                for card in cards[:MAX_LISTINGS]:
                    try:
                        title_el = (
                            card.query_selector("h2") or
                            card.query_selector("h3") or
                            card.query_selector("[class*='title']") or
                            card.query_selector("a")
                        )
                        title = title_el.inner_text().strip() if title_el else ""
                        if not title:
                            continue

                        price_val = None
                        price_attr = card.get_attribute("data-price")
                        if price_attr:
                            price_val = parse_price(str(price_attr))
                        if not price_val:
                            price_el = card.query_selector(
                                "[class*='price'], [data-testid*='price']")
                            if price_el:
                                raw = (
                                    price_el.get_attribute("data-price") or
                                    price_el.get_attribute("content") or
                                    price_el.inner_text().strip()
                                )
                                price_val = parse_price(str(raw))

                        link_el = card.query_selector("a[href]")
                        href = link_el.get_attribute("href") if link_el else ""
                        if href and href.startswith("/"):
                            href = "https://www.mobile.de" + href
                        ext_m = re.search(r"/(\d{6,})", href)
                        ext_id = ext_m.group(1) if ext_m else (href or None)

                        img_el = card.query_selector("img")
                        thumb = ""
                        if img_el:
                            thumb = (
                                img_el.get_attribute("src") or
                                img_el.get_attribute("data-src") or ""
                            )

                        card_text = card.inner_text()
                        year_m = re.search(r"\b(19|20)\d{2}\b", card_text)
                        year = int(year_m.group()) if year_m else None
                        km_m = re.search(r"(\d[\d\.]+)\s*km", card_text, re.IGNORECASE)
                        km = None
                        if km_m:
                            try:
                                km = int(km_m.group(1).replace(".", ""))
                            except ValueError:
                                pass

                        results.append(make_listing(
                            platform="mobile_de", external_id=ext_id, titlu=title,
                            year=year, km=km, pret=price_val, moneda="EUR",
                            locatie="Germania", source_url=href, thumbnail_url=thumb or None,
                        ))
                    except Exception:
                        continue
            except Exception as exc:
                log_manager.emit("auto_listings", "ERR",
                    f"Mobile.de Playwright eroare: {str(exc)[:100]}")
            finally:
                browser.close()
    except Exception as exc:
        log_manager.emit("auto_listings", "ERR",
            f"Mobile.de Playwright init: {str(exc)[:100]}")

    log_manager.emit("auto_listings", "OK",
        f"Mobile.de: {len(results)} rezultate pagina {page}")
    return results[:MAX_LISTINGS]


async def search_mobile_de(make_id: str = "", filters: dict = {}, page: int = 1) -> list:
    filters = filters or {}
    # Permite trimiterea numelui marcii in loc de ID (ex: "BMW").
    if make_id and not make_id.isdigit():
        make_id = MOBILE_DE_MAKE_IDS.get(make_id, MOBILE_DE_MAKE_IDS.get(make_id.title(), ""))

    params = _build_params(make_id, filters, page)
    url = _SEARCH_URL + "?" + urllib.parse.urlencode(params)
    log_manager.emit("auto_listings", "SCAN",
        f"Mobile.de: cautare make_id={make_id or '-'} pagina {page}")

    # 1) curl_cffi cu chrome124 + headere complete (rapid). Daca trece, gata.
    headers = {**MOBILE_DE_HEADERS, "Referer": "https://www.mobile.de/"}
    try:
        async with AsyncSession() as session:
            resp = await session.get(
                _SEARCH_URL, params=params, headers=headers,
                impersonate="chrome124", timeout=20,
            )
        if resp.status_code == 200:
            results = _parse_mobilede_html(resp.text)
            if results:
                log_manager.emit("auto_listings", "OK",
                    f"Mobile.de (headers): {len(results)} rezultate pagina {page}")
                return results
            # HTTP 200 dar fara carduri = pagina-challenge JS → fallback Playwright.
        else:
            print(f"[mobile_de] curl HTTP {resp.status_code} → fallback Playwright")
    except Exception as exc:
        print(f"[mobile_de] curl error: {exc} → fallback Playwright")

    # 2) Fallback Playwright (executa JS). Ruleaza intr-un thread ca sync_playwright
    # sa nu intre in conflict cu event loop-ul asyncio al apelantului.
    return await asyncio.to_thread(_search_mobile_de_playwright, url, page)
