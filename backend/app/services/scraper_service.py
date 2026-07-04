import asyncio
import json
import random
import re
import time
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from app.utils.category_mapper import infer_category_from_name
from app.services.log_manager import log_manager


_ALTEX_HEADERS = {
    "Origin": "https://altex.ro",
    "Referer": "https://altex.ro/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

_SOLE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://sole.ro",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}

_FARMACIATEI_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://comenzi.farmaciatei.ro/",
    "Upgrade-Insecure-Requests": "1",
}

_EMAG_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.emag.ro/",
    "Upgrade-Insecure-Requests": "1",
}

_PCGARAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.pcgarage.ro/",
    "Upgrade-Insecure-Requests": "1",
}

_IMPERSONATE = "chrome131"

# Pagination safety caps (per-site) so a runaway query can't hammer a shop.
_MAX_PAGES_EMAG = 10         # eMAG serves ~72-78 cards per page
_MAX_PAGES_PCGARAGE = 15     # PCGarage serves ~20 cards per page
_MAX_PAGES_FARMACIATEI = 10  # Farmacia Tei serves ~60 cards per page
_MAX_ALTEX_SIZE = 100        # Fenrir API accepts size up to 100 in one call


def _altex_image_url(thumbnail: Optional[str]) -> str:
    if not thumbnail:
        return ""
    if thumbnail.startswith("http"):
        return thumbnail
    return f"https://s13emagst.akamaized.net/products/altex/media/catalog/product{thumbnail}"


def _altex_product_url(url_key: Optional[str], sku: Optional[str]) -> str:
    if not url_key or not sku:
        return "https://altex.ro/"
    return f"https://altex.ro/{url_key}/cpd/{sku}/"


_ALTEX_BAD_PATH_CHARS = re.compile(r'[/\\"\'<>{}|`]')


def _sanitize_altex_query(query: str) -> str:
    cleaned = _ALTEX_BAD_PATH_CHARS.sub(" ", query or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


_ALTEX_SKU_FROM_URL_RE = re.compile(r"/cpd/([^/?#]+)/?", re.IGNORECASE)


def _altex_sku_from_url(source_url: Optional[str]) -> Optional[str]:
    if not source_url:
        return None
    match = _ALTEX_SKU_FROM_URL_RE.search(source_url)
    return match.group(1) if match else None


def _sync_scrape_altex(query: str, max_results: int) -> list:
    """Apelează API-ul intern Fenrir al Altex (folosit de propriul frontend React).

    API-ul acceptă `size` până la ~100 într-un singur apel, deci nu e nevoie de
    buclă de paginare: cerem min(max_results, 100) dintr-o singură lovitură.
    """
    safe_query = _sanitize_altex_query(query)
    if not safe_query:
        return [{"error": "Query gol pentru Altex dupa sanitizare."}]
    encoded = urllib.parse.quote(safe_query)
    size = min(max(max_results, 1), _MAX_ALTEX_SIZE)
    url = f"https://fenrir.altex.ro/v2/catalog/search/{encoded}?size={size}"
    try:
        response = curl_requests.get(
            url,
            headers=_ALTEX_HEADERS,
            impersonate=_IMPERSONATE,
            timeout=20,
        )
    except Exception as exc:
        return [{"error": f"Eroare conexiune Altex: {exc}"}]

    if response.status_code != 200:
        return [{"error": f"Altex a returnat status {response.status_code}"}]

    try:
        data = response.json()
    except Exception as exc:
        return [{"error": f"Raspuns invalid de la Altex: {exc}"}]

    raw_products = data.get("products") or []
    products = []
    for item in raw_products[:max_results]:
        try:
            name = item.get("name") or ""
            if not name:
                continue
            price = float(item.get("price") or 0)
            url_key = item.get("url_key")
            sku = item.get("sku")
            in_stock = bool(item.get("stock_status")) and not item.get("is_eol")
            ean = item.get("ean_codes") or ""

            # --- Detectare reducere ---
            # Altex expune:
            #   price         -> prețul curent (posibil redus)
            #   regular_price -> prețul de listă (egal cu `price` când nu e în promoție)
            #   discount_type -> "none" când nu există reducere activă,
            #                    altfel ex: "percentage"
            original_price: Optional[float] = None
            is_on_sale = False
            try:
                regular_price = float(item.get("regular_price") or 0)
            except (TypeError, ValueError):
                regular_price = 0.0
            discount_type = (item.get("discount_type") or "none").lower()
            if (
                regular_price > 0
                and price > 0
                and regular_price > price
                and discount_type != "none"
            ):
                is_on_sale = True
                original_price = regular_price

            # FlipRadar — categorie: preferam categoria din raspunsul Fenrir,
            # cu inferenta din nume (KEYWORD_MAP) ca fallback.
            main_cat, sub_cat = infer_category_from_name(name, "altex")
            fenrir_cat = item.get("category_name")
            if not fenrir_cat:
                raw_cats = item.get("categories")
                if isinstance(raw_cats, str):
                    fenrir_cat = raw_cats
                elif isinstance(raw_cats, list) and raw_cats:
                    c0 = raw_cats[0]
                    fenrir_cat = c0.get("name") if isinstance(c0, dict) else (c0 if isinstance(c0, str) else None)
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "altex.ro",
                "source_url": _altex_product_url(url_key, sku),
                "image_url": _altex_image_url(item.get("image") or item.get("thumbnail")),
                "in_stock": in_stock,
                "ean": ean if ean else None,
                "sku": sku or None,
                "category": fenrir_cat or main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "altex.ro"}]
    return products


def _parse_sole_price(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sole_product_url(item: dict) -> str:
    rel = item.get("url") or ""
    if rel.startswith("http"):
        return rel
    return f"https://sole.ro/{rel.lstrip('/')}"


def _sole_image_url(item: dict) -> str:
    image = item.get("image") or item.get("photo") or ""
    if not image:
        return ""
    if image.startswith("http"):
        return image
    return f"https://static.sole.ro/{image.lstrip('/')}"


def _sync_scrape_sole(query: str, max_results: int) -> list:
    """POST la sole.ro/cauta/<query> care returnează JSON consumat de frontend-ul lor Vue.

    Notă: sole.ro limitează `perpage` pe server — valori mari (60, 100, 200) returnează
    0 produse. Trimitem maxim-ul cerut de utilizator, dar ne bazăm pe răspunsul
    unei singure pagini; potrivirea reală e limitată de ce returnează sole.
    """
    encoded = urllib.parse.quote(query.strip())
    url = f"https://sole.ro/cauta/{encoded}"
    headers = dict(_SOLE_HEADERS)
    headers["Referer"] = url
    try:
        response = curl_requests.post(
            url,
            headers=headers,
            data={"filterstring": "", "perpage": max_results, "order": 3},
            impersonate=_IMPERSONATE,
            timeout=20,
        )
    except Exception as exc:
        return [{"error": f"Eroare conexiune Sole.ro: {exc}"}]

    if response.status_code != 200:
        return [{"error": f"Sole.ro a returnat status {response.status_code}"}]

    try:
        data = response.json()
    except Exception as exc:
        return [{"error": f"Raspuns invalid de la Sole.ro: {exc}"}]

    raw_products = data.get("products") or []
    products = []
    for item in raw_products[:max_results]:
        try:
            name = item.get("product") or item.get("productoverwrite") or ""
            if not name:
                continue
            in_stock = bool(item.get("instock")) and not item.get("sold_out")
            sole_code = item.get("code") or None

            price = _parse_sole_price(item.get("price"))

            # --- Detectare reducere ---
            # sole.ro expune pentru fiecare produs:
            #   price        -> prețul curent (posibil redus)
            #   oldprice     -> prețul de listă (0 sau == price când nu e promoție)
            #   ispromo      -> 1 când produsul e marcat ca promoție
            #   save_percent -> procent economisit ca întreg (0 când nu e promoție)
            original_price: Optional[float] = None
            is_on_sale = False
            old_price = _parse_sole_price(item.get("oldprice"))
            is_promo_flag = bool(item.get("ispromo")) or str(item.get("ispromo") or "").strip() == "1"
            try:
                save_pct = int(item.get("save_percent") or 0)
            except (TypeError, ValueError):
                save_pct = 0

            if (
                old_price > 0
                and price > 0
                and old_price > price
                and (is_promo_flag or save_pct > 0)
            ):
                is_on_sale = True
                original_price = old_price

            main_cat, sub_cat = infer_category_from_name(name, "sole")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "sole.ro",
                "source_url": _sole_product_url(item),
                "image_url": _sole_image_url(item),
                "in_stock": in_stock,
                "ean": None,
                "sku": sole_code,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "sole.ro"}]
    return products


def _parse_farmaciatei_price(price_text: str) -> float:
    """Parsează prețuri de forma '29,00 LEI' sau '17,00 LEI' -> 29.00."""
    if not price_text:
        return 0.0
    cleaned = re.sub(r"[^0-9,\.]", "", price_text).replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _farmaciatei_page_url(encoded_query: str, page: int) -> str:
    """Paginarea Farmacia Tei folosește un path cu virgulă: `/cauti/q/p,2`."""
    base = f"https://comenzi.farmaciatei.ro/cauti/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p,{page}"


def _parse_farmaciatei_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate Farmacia Tei."""
    products = []
    for item in soup.select("div.product-item.product-details"):
        try:
            title_a = item.select_one("a.item-title")
            if not title_a:
                continue
            name = title_a.get_text(strip=True)
            if not name:
                continue
            source_url = title_a.get("href", "") or ""

            img = item.select_one("a.product-image-listing img")
            image_url = img.get("src", "") if img else ""

            btn = item.select_one("button.cd-add-to-cart")
            oos_span = item.select_one("span.product-block-out-of-stock")
            in_stock = oos_span is None and btn is not None

            # --- Extragere preț cu detectare reducere ---
            # Pe pagina farmaciatei.ro:
            #   span.old-price      -> prețul original (prezent doar când e în promoție)
            #   span.regular-price  -> prețul afișat curent (redus dacă e promoție)
            #   button[data-price]  -> istoric prețul de catalog/original,
            #                          deci preferăm regular-price când e disponibil.
            price = 0.0
            original_price: Optional[float] = None
            is_on_sale = False

            regular_el = item.select_one("span.regular-price")
            old_el = item.select_one("span.old-price")

            if regular_el:
                price = _parse_farmaciatei_price(regular_el.get_text())
            if old_el:
                original_price = _parse_farmaciatei_price(old_el.get_text())

            if price <= 0:
                # Fallback-uri când noul markup nu este prezent
                if btn and btn.get("data-price"):
                    try:
                        price = float(btn.get("data-price"))
                    except (TypeError, ValueError):
                        price = 0.0
                if price <= 0:
                    price_span = item.select_one("span.price:not(.text-muted)") or item.select_one("span.price")
                    if price_span:
                        price = _parse_farmaciatei_price(price_span.get_text())

            if (
                original_price is not None
                and price > 0
                and original_price > price
            ):
                is_on_sale = True
            else:
                # Fără reducere reală -> nu expunem un original_price egal cu cel curent
                original_price = None

            pid = btn.get("data-pid") if btn else None
            main_cat, sub_cat = infer_category_from_name(name, "farmaciatei")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "farmaciatei.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": pid,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_farmaciatei(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe farmaciatei.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_FARMACIATEI + 1):
        url = _farmaciatei_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_FARMACIATEI_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune Farmacia Tei: {exc}"}]
            break

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"Farmacia Tei a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare Farmacia Tei: {exc}"}]
            break

        page_products = _parse_farmaciatei_page(soup)
        if not page_products:
            break

        new_this_page = 0
        for p in page_products:
            # Deduplicare după sku; fallback pe source_url când lipsește.
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            # Pagina a returnat doar duplicate -> am ajuns la sfârșitul rezultatelor utile.
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "farmaciatei.ro"}]
    return products


def _parse_emag_price(text: str) -> float:
    """Parsează prețuri în format românesc de tip '1.299,99 Lei' sau '12999' -> float.

    Gestionează separatorul de mii '.' și separatorul zecimal ',' de la eMAG.
    Unele elemente de preț separă partea întreagă de cea zecimală în span-uri diferite;
    funcția operează pe textul combinat după get_text() din BeautifulSoup.
    """
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d,\.]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned:
        # Format românesc: "1.299,99" -> parte întreagă "1299", zecimale "99"
        last_comma = cleaned.rfind(",")
        integer_part = cleaned[:last_comma].replace(".", "")
        decimal_part = cleaned[last_comma + 1:]
        normalized = f"{integer_part}.{decimal_part}" if decimal_part else integer_part
    else:
        # Fără virgulă: punctele sunt probabil separatori de mii ("1.299" -> "1299")
        normalized = cleaned.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def _emag_page_url(encoded_query: str, page: int) -> str:
    """Paginarea eMAG: /search/<q>/p2/, /search/<q>/p3/, etc."""
    base = f"https://www.emag.ro/search/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_emag_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate eMAG."""
    products = []
    # Markup-ul cardurilor eMAG este destul de stabil, dar folosește clase generice;
    # încercăm cei mai specifici selectori mai întâi, cu fallback pe cei mai generali.
    cards = (
        soup.select("div.card-item.js-product-data")
        or soup.select("div.card-item")
        or soup.select("[data-product-id]")
    )

    for item in cards:
        try:
            title_a = (
                item.select_one("a.card-v2-title")
                or item.select_one(".card-v2-title-wrapper a")
                or item.select_one("h2 a")
                or item.select_one("a[href*='/pd/']")
            )
            name = ""
            if title_a:
                name = title_a.get_text(strip=True)
            if not name:
                name = (item.get("data-name") or "").strip()
            if not name:
                continue

            source_url = title_a.get("href", "") if title_a else ""
            if source_url and not source_url.startswith("http"):
                source_url = f"https://www.emag.ro{source_url}"

            img = item.select_one("img.card-v2-thumbnail-image") or item.select_one("img")
            image_url = ""
            if img:
                image_url = img.get("src") or img.get("data-src") or img.get("data-original") or ""

            # --- Extragere preț ---
            # eMAG randează noul preț în `.product-new-price` și prețul vechi
            # (tăiat) în `.product-old-price` când e în promoție.
            price = 0.0
            new_price_el = item.select_one(".product-new-price")
            if new_price_el:
                price = _parse_emag_price(new_price_el.get_text(separator="", strip=True))
            if price <= 0 and item.get("data-price"):
                try:
                    price = float(item.get("data-price"))
                except (TypeError, ValueError):
                    price = 0.0

            original_price: Optional[float] = None
            is_on_sale = False
            old_price_el = item.select_one(".product-old-price")
            if old_price_el:
                old_price = _parse_emag_price(old_price_el.get_text(separator="", strip=True))
                if old_price > 0 and price > 0 and old_price > price:
                    original_price = old_price
                    is_on_sale = True

            # eMAG marchează produsele indisponibile cu un badge de stoc pe card
            in_stock = item.select_one(".badge-no-stock") is None and item.select_one(".product-stock-status-out") is None

            product_id = item.get("data-product-id") or item.get("data-offer-id") or None

            main_cat, sub_cat = infer_category_from_name(name, "emag")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "emag.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": product_id,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_emag(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe eMAG.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_EMAG + 1):
        url = _emag_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_EMAG_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune eMAG: {exc}"}]
            break

        print(f"[DEBUG TEMP] {url} -> status={response.status_code} len={len(response.text)}")  # DEBUG TEMP

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"eMAG a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare eMAG: {exc}"}]
            break

        page_products = _parse_emag_page(soup)
        if not page_products:
            # DEBUG TEMP — status 200 dar 0 produse extrase: arata fragment + semne de blocare
            if response.status_code == 200:
                _snippet = re.sub(r"\s+", " ", response.text[:500]).strip()
                _found = [k for k in (
                    "captcha", "access denied", "blocked", "robot",
                    "verify you are human", "cloudflare", "imperva", "datadome",
                ) if k in response.text.lower()]
                print(f"[DEBUG TEMP] 0 produse extrase, status 200. Continut suspect: {_found}. Fragment: {_snippet}")
            # END DEBUG TEMP
            break

        new_this_page = 0
        for p in page_products:
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "emag.ro"}]
    return products


def _pcgarage_page_url(encoded_query: str, page: int) -> str:
    """Paginarea PCGarage: /cauta/<q>/p2/, /cauta/<q>/p3/, etc."""
    base = f"https://www.pcgarage.ro/cauta/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_pcgarage_page(soup: BeautifulSoup) -> list:
    """Extrage dictionarele de produse dintr-o pagină de rezultate PCGarage."""
    products = []
    for card in soup.select("div.product_box"):
        try:
            name_a = card.select_one(".product_box_name a") or card.select_one("h2 a")
            if not name_a:
                continue
            # Textul titlului cardului conține evidențieri <b> pentru termenul căutat;
            # atributul title conține numele curat al produsului.
            name = (name_a.get("title") or name_a.get_text(" ", strip=True)).strip()
            if not name:
                continue
            source_url = name_a.get("href", "") or ""
            if source_url and not source_url.startswith("http"):
                source_url = f"https://www.pcgarage.ro{source_url}"

            # Imagine: preferăm <picture><source srcset> când e prezent, fallback pe <img>.
            image_url = ""
            src_el = card.select_one(".product_box_image picture source")
            if src_el:
                srcset = src_el.get("srcset") or ""
                image_url = srcset.split(",")[0].strip().split(" ")[0]
            if not image_url:
                img = card.select_one(".product_box_image img")
                if img:
                    image_url = img.get("src") or img.get("data-src") or ""

            # Preț: ".pb-price p.price" -> "7.799,98 RON" (format românesc).
            price = 0.0
            price_el = card.select_one(".pb-price p.price") or card.select_one(".pb-price")
            if price_el:
                price = _parse_emag_price(price_el.get_text(strip=True))

            # Prețul vechi (când e promoție) — verificăm mai mulți selectori ca măsură
            # de precauție, deoarece PCGarage uneori livrează markup promo cu preț tăiat.
            original_price: Optional[float] = None
            is_on_sale = False
            old_el = (
                card.select_one(".pb-old-price")
                or card.select_one(".old_price")
                or card.select_one(".pb-price del")
                or card.select_one(".pb-price s")
            )
            if old_el:
                old_price = _parse_emag_price(old_el.get_text(strip=True))
                if old_price > 0 and price > 0 and old_price > price:
                    original_price = old_price
                    is_on_sale = True

            # Disponibilitate: "instock" / "insupplierstock" -> disponibil; "outofstock" -> indisponibil.
            in_stock = True
            avail_el = card.select_one(".product_box_availability")
            if avail_el and "outofstock" in " ".join(avail_el.get("class", [])):
                in_stock = False

            sku: Optional[str] = None
            rates = card.select_one("a.rates_installments[href*='pid=']")
            if rates:
                m = re.search(r"pid=(\d+)", rates.get("href", ""))
                if m:
                    sku = m.group(1)

            main_cat, sub_cat = infer_category_from_name(name, "pcgarage")
            products.append({
                "name": name,
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "currency": "RON",
                "source": "pcgarage.ro",
                "source_url": source_url,
                "image_url": image_url,
                "in_stock": in_stock,
                "ean": None,
                "sku": sku,
                "category": main_cat,
                "subcategory": sub_cat,
            })
        except Exception:
            continue
    return products


def _sync_scrape_pcgarage(query: str, max_results: int) -> list:
    """Scrapeaza rezultatele de căutare de pe PCGarage.ro pe mai multe pagini."""
    encoded = urllib.parse.quote(query.strip())
    products: list = []
    seen_codes: set = set()

    for page in range(1, _MAX_PAGES_PCGARAGE + 1):
        url = _pcgarage_page_url(encoded, page)
        try:
            response = curl_requests.get(
                url,
                headers=_PCGARAGE_HEADERS,
                impersonate=_IMPERSONATE,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare conexiune PCGarage: {exc}"}]
            break

        print(f"[DEBUG TEMP] {url} -> status={response.status_code} len={len(response.text)}")  # DEBUG TEMP

        if response.status_code != 200:
            if page == 1:
                return [{"error": f"PCGarage a returnat status {response.status_code}"}]
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            if page == 1:
                return [{"error": f"Eroare parsare PCGarage: {exc}"}]
            break

        page_products = _parse_pcgarage_page(soup)
        if not page_products:
            # DEBUG TEMP — status 200 dar 0 produse extrase: arata fragment + semne de blocare
            if response.status_code == 200:
                _snippet = re.sub(r"\s+", " ", response.text[:500]).strip()
                _found = [k for k in (
                    "captcha", "access denied", "blocked", "robot",
                    "verify you are human", "cloudflare", "imperva", "datadome",
                ) if k in response.text.lower()]
                print(f"[DEBUG TEMP] 0 produse extrase, status 200. Continut suspect: {_found}. Fragment: {_snippet}")
            # END DEBUG TEMP
            break

        new_this_page = 0
        for p in page_products:
            key = p.get("sku") or p.get("source_url") or p.get("name")
            if key and key in seen_codes:
                continue
            if key:
                seen_codes.add(key)
            products.append(p)
            new_this_page += 1
            if len(products) >= max_results:
                break

        if len(products) >= max_results:
            break
        if new_this_page == 0:
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "pcgarage.ro"}]
    return products


def fetch_ean_from_url(source_url: str) -> Optional[str]:
    """Încearcă să preia EAN-ul/GTIN-ul din pagina de detalii a unui produs.

    Suportă: farmaciatei.ro (JSON-LD gtin13 / sku),
    sole.ro (text simplu "Cod EAN:"), altex.ro (JSON-LD gtin13).
    Returnează None dacă nu se găsește sau în caz de eroare.
    """
    if not source_url:
        return None
    try:
        response = curl_requests.get(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ro-RO,ro;q=0.9",
            },
            impersonate=_IMPERSONATE,
            timeout=15,
            allow_redirects=True,
        )
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "html.parser")

        # Încearcă date structurate JSON-LD
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                ld = json.loads(script.string or "")
                items = ld if isinstance(ld, list) else [ld]
                for obj in items:
                    if isinstance(obj, dict):
                        gtin = obj.get("gtin13") or obj.get("gtin") or obj.get("gtin12") or ""
                        if gtin and len(gtin) >= 8:
                            return gtin.strip()
                        sku = obj.get("sku") or ""
                        if sku and sku.isdigit() and len(sku) >= 8:
                            return sku.strip()
            except Exception:
                continue

        # Fallback: caută EAN în text simplu (acoperă sole.ro și farmaciatei.ro)
        text = soup.get_text()
        for pattern in (
            r"[Cc]od\s*EAN[:\s]+(\d{8,14})",      # sole.ro: "Cod EAN: 880973..."
            r"EAN[:\s]+(\d{8,14})",                 # generic "EAN: ..."
            r"[Cc]od\s+produs[:\s]+(\d{8,14})",     # farmaciatei.ro: "Cod produs: 500015..."
            r"GTIN[:\s]+(\d{8,14})",                 # generic GTIN
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)

    except Exception:
        pass
    return None


async def fetch_ean_from_url_async(source_url: str) -> Optional[str]:
    """Wrapper async pentru fetch_ean_from_url."""
    return await asyncio.to_thread(fetch_ean_from_url, source_url)


def _emit_catalog(shop_name: str, query: str, products: list) -> None:
    """Loghează în modulul `catalog` rezultatul unei scanări de magazin."""
    n = sum(1 for p in (products or []) if not (isinstance(p, dict) and p.get("message")))
    log_manager.emit("catalog", "SCAN", f"Scanare {shop_name} · {n} produse verificate pentru '{query}'")
    if n:
        log_manager.emit("catalog", "OK", f"{shop_name}: {n} produse găsite")


async def scrape_altex(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_altex, query, max_results)
    _emit_catalog("Altex", query, res)
    return res


async def scrape_sole(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_sole, query, max_results)
    _emit_catalog("Sole", query, res)
    return res


async def scrape_farmaciatei(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_farmaciatei, query, max_results)
    _emit_catalog("FarmaciaTei", query, res)
    return res


async def scrape_emag(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_emag, query, max_results)
    _emit_catalog("eMAG", query, res)
    return res


async def scrape_pcgarage(query: str, max_results: int = 100) -> list:
    """Wrapper async — curl_cffi este sincron, rulează într-un thread."""
    res = await asyncio.to_thread(_sync_scrape_pcgarage, query, max_results)
    _emit_catalog("PCGarage", query, res)
    return res


_SCRAPERS_BY_SOURCE = {
    "altex.ro": _sync_scrape_altex,
    "sole.ro": _sync_scrape_sole,
    "farmaciatei.ro": _sync_scrape_farmaciatei,
    "emag.ro": _sync_scrape_emag,
    "pcgarage.ro": _sync_scrape_pcgarage,
}


def refresh_price_from_source(
    source: Optional[str],
    source_url: Optional[str],
    product_name: Optional[str],
    sku: Optional[str] = None,
) -> Optional[float]:
    """Re-fetch the current price for a product from its source magazin.

    Returneaza un float (pretul nou in moneda magazinului) sau None daca nu
    am putut gasi produsul. Strategie: lansam o cautare cu SKU (mai precisa)
    sau cu numele si gasim rezultatul cu acelasi source_url.
    """
    if not source or not source_url:
        return None
    scraper = _SCRAPERS_BY_SOURCE.get(source.lower())
    if not scraper:
        return None
    if not sku and source.lower() == "altex.ro":
        sku = _altex_sku_from_url(source_url)
    query = (sku or product_name or "").strip()
    if not query:
        return None
    try:
        # 20 rezultate sunt suficiente: produsul cautat ar trebui in primele
        # cateva, mai ales cand cautam dupa SKU sau dupa nume specific.
        results = scraper(query[:80], 20)
    except Exception:
        return None
    if not results:
        return None
    # Strategia 1: potrivire exactă pe source_url (cea mai precisă când URL-urile
    # rămân stabile pe site).
    norm_url = source_url.rstrip("/")
    for r in results:
        if not isinstance(r, dict):
            continue
        r_url = (r.get("source_url") or "").rstrip("/")
        if r_url and r_url == norm_url:
            price = r.get("price")
            try:
                price = float(price)
                return price if price > 0 else None
            except (TypeError, ValueError):
                continue
    # Strategia 2 (fallback): potrivire după primele 40 de caractere din nume,
    # case-insensitive. Acoperă cazurile în care site-ul și-a schimbat
    # structura URL-urilor sau când source-ul și source_url-ul stocate au
    # mici inconsistențe (ex: salvare manuală cu URL trunchiat).
    if product_name:
        prefix = product_name.strip()[:40].lower()
        if prefix:
            for r in results:
                if not isinstance(r, dict):
                    continue
                r_name = (r.get("name") or "").strip().lower()
                if r_name and r_name.startswith(prefix):
                    price = r.get("price")
                    try:
                        price = float(price)
                        if price > 0:
                            return price
                    except (TypeError, ValueError):
                        continue
    # DEBUG TEMP — ambele strategii de potrivire au esuat; pentru emag/pcgarage arata de ce
    if source.lower() in ("emag.ro", "pcgarage.ro"):
        _first = results[0] if results else None
        if isinstance(_first, dict) and ("error" in _first or "message" in _first):
            print(f"[DEBUG TEMP] Nepotrivit: query='{query[:80]}' rezultate={len(results)} primul_rezultat={_first}")
        else:
            _top5 = [(r.get("name"), r.get("source_url")) for r in results[:5] if isinstance(r, dict)]
            print(f"[DEBUG TEMP] Nepotrivit: query='{query[:80]}' rezultate={len(results)} top5={_top5}")
    # END DEBUG TEMP
    return None


def find_cross_shop_matches(
    name: str,
    ean: Optional[str],
    exclude_source: Optional[str],
    max_results: int = 20,
) -> dict:
    """Caută același produs pe celelalte magazine (toate din _SCRAPERS_BY_SOURCE
    minus sursa de origine). Returnează:
        {"ean_matches": [...], "name_candidates": [...]}

    Strategie (adaptată la realitatea scraperelor): căutăm pe NUME pe fiecare
    magazin — singura interogare fiabilă, fiindcă doar Altex expune `ean` în
    rezultatele de căutare. Apoi:
      - dacă un rezultat are EAN-ul identic cu al produsului  -> ean_matches
        (potrivire sigură -> se atașează automat ca sursă);
      - altfel, dacă există EXACT un candidat relevant pe nume -> name_candidates
        (sugestie ce așteaptă confirmarea userului). 0 sau 2+ = prea ambiguu, sărim.

    Secvențial, cu delay aleator între magazine (același pattern anti-blocare ca
    refresh_price_from_source). Nu paralelizează.
    """
    ean_matches: list = []
    name_candidates: list = []
    query = (name or "").strip()
    if not query:
        return {"ean_matches": ean_matches, "name_candidates": name_candidates}

    ean_norm = (ean or "").strip().lstrip("0")
    exclude = (exclude_source or "").strip().lower()

    for source, scraper in _SCRAPERS_BY_SOURCE.items():
        if source == exclude:
            continue
        time.sleep(random.uniform(0.6, 1.4))  # anti-blocare, ca la refresh_price_from_source
        try:
            raw = scraper(query[:80], max_results)
        except Exception as exc:
            log_manager.emit("catalog", "WARN",
                             f"Cross-shop {source}: eroare scraper ({str(exc)[:60]})")
            continue
        _emit_catalog(source, query, raw)

        real = [r for r in raw
                if isinstance(r, dict) and "error" not in r and "message" not in r]
        if not real:
            continue

        # 1) Potrivire confirmată prin EAN (doar magazinele care expun `ean` în
        #    rezultate, ex. Altex). Re-verificăm egalitatea strict, ca să nu
        #    atașăm din greșeală rezultate cu EAN gol.
        if ean_norm:
            confirmed = [r for r in real
                         if (r.get("ean") or "").strip().lstrip("0") == ean_norm]
            if confirmed:
                ean_matches.append({**confirmed[0], "source": source})
                continue

        # 2) Candidat unic pe nume -> sugestie. filter_by_relevance păstrează doar
        #    produsele al căror nume conține toți tokenii semnificativi din query.
        relevant = filter_by_relevance(real, query)
        clear = [r for r in relevant
                 if isinstance(r, dict) and "error" not in r and "message" not in r]
        if len(clear) == 1:  # un singur candidat clar; 0 sau 2+ = prea ambiguu, sărim
            name_candidates.append({**clear[0], "source": source})

    return {"ean_matches": ean_matches, "name_candidates": name_candidates}


def _tokenize_query(query: str) -> list:
    """Extrage tokenii semnificativi (minuscule, lungime >= 3) dintr-un query utilizator.

    Tokenii scurți ("de", "la", "it") sunt eliminați pentru ca cuvintele de umplutură
    să nu strice potrivirea de relevanță.
    """
    return [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) >= 3]


def filter_by_relevance(products: list, query: str) -> list:
    """Elimină produsele al căror nume nu conține toți tokenii semnificativi din query.

    Multe motoare de căutare din magazine românești cad silențios pe rezultate
    "înrudite" fuzzy când query-ul exact nu are potriviri (ex: căutând "purito
    sleeping pack" pe eMAG returnează creme Vichy fără legătură). Acest filtru
    păstrează doar produsele al căror nume conține TOȚI tokenii semnificativi ca
    substring (case-insensitive), potrivind intenția utilizatorului pentru query-uri
    specifice brand+produs fără a tăia prea mult query-urile cu un singur cuvânt.

    Intrările sentinel de eroare/mesaj trec nefiltrate. Dacă toate produsele reale
    sunt filtrate, emitem un mesaj sintetic "fără rezultate relevante" pentru ca UI-ul
    să aibă totuși ceva de randat.
    """
    tokens = _tokenize_query(query)
    if not tokens:
        return products

    sentinels = [p for p in products if "error" in p or "message" in p]
    real = [p for p in products if "error" not in p and "message" not in p]

    filtered = [
        p for p in real
        if all(tok in (p.get("name") or "").lower() for tok in tokens)
    ]

    if filtered:
        return filtered
    if sentinels:
        return sentinels
    if real:
        # Am avut rezultate reale dar niciuna nu a potrivit toți tokenii → fim expliciți.
        return [{"message": "Nu s-au gasit rezultate relevante pentru aceasta cautare."}]
    return []


_FUZZY_FALLBACK_THRESHOLD = 5


def filter_by_code(products: list, code: str, field: str) -> list:
    """Păstrează produsele al căror `field` (ean sau sku) se potrivește cu `code`.

    Trei categorii per rezultat:
      - câmpul populat și se potrivește  -> potrivire exactă de încredere
      - câmpul populat dar diferit        -> eliminat (semn de fallback fuzzy, ex:
        eMAG returnând SKU-uri fără legătură pentru un SKU necunoscut)
      - câmpul este None                  -> avem încredere în scraper, DAR doar când
        sunt puține astfel de rezultate. Multe rezultate cu câmpul None la rând indică
        că magazinul a căzut pe potrivire keyword-fuzzy pentru un query numeric (eMAG
        returnează ~50 produse aleatorii când un EAN nu e în catalogul său).
    """
    code_norm = (code or "").strip().lstrip("0")
    if not code_norm:
        return products

    sentinels = [p for p in products if isinstance(p, dict) and ("error" in p or "message" in p)]
    real = [p for p in products if isinstance(p, dict) and "error" not in p and "message" not in p]

    matched_with_field = []
    matched_without_field = []
    for p in real:
        v = (p.get(field) or "").strip().lstrip("0")
        if not v:
            matched_without_field.append(p)
        elif v == code_norm:
            matched_with_field.append(p)

    if matched_with_field:
        return matched_with_field

    if matched_without_field and len(matched_without_field) <= _FUZZY_FALLBACK_THRESHOLD:
        return matched_without_field

    if sentinels:
        return sentinels
    return [{"message": f"Nu s-au gasit produse cu {field.upper()}={code} pe aceasta sursa."}]
