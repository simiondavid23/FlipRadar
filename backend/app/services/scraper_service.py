import asyncio
import json
import re
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests


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
    """Call Altex's internal Fenrir API (used by their own React frontend).

    The API accepts `size` up to ~100 in a single call, so no pagination loop
    is needed: we request min(max_results, 100) in one shot.
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

            # --- Discount detection ---
            # Altex exposes:
            #   price         -> current (possibly discounted) price
            #   regular_price -> list price (equals `price` when not on sale)
            #   discount_type -> "none" when there's no active discount,
            #                    otherwise e.g. "percentage"
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
    """POST to sole.ro/cauta/<query> which returns JSON consumed by their Vue frontend.

    Note: sole.ro caps `perpage` server-side — elevated values (60, 100, 200)
    return 0 products. We therefore send the user-requested max but rely on
    the single-page response; real matching is capped by what sole returns.
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

            # --- Discount detection ---
            # sole.ro exposes on every product:
            #   price        -> current (possibly discounted) price
            #   oldprice     -> list price (equals 0 or == price when not on sale)
            #   ispromo      -> 1 when the product is flagged as on promo
            #   save_percent -> integer percent saved (0 when not on sale)
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
            })
        except Exception:
            continue

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "sole.ro"}]
    return products


def _parse_farmaciatei_price(price_text: str) -> float:
    """Parse prices like '29,00 LEI' or '17,00 LEI' -> 29.00."""
    if not price_text:
        return 0.0
    cleaned = re.sub(r"[^0-9,\.]", "", price_text).replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _farmaciatei_page_url(encoded_query: str, page: int) -> str:
    """Farmacia Tei pagination uses a comma-separated path: `/cauti/q/p,2`."""
    base = f"https://comenzi.farmaciatei.ro/cauti/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p,{page}"


def _parse_farmaciatei_page(soup: BeautifulSoup) -> list:
    """Extract product dicts from a Farmacia Tei search results page."""
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

            # --- Price extraction with discount detection ---
            # On farmaciatei.ro listing:
            #   span.old-price      -> original price (only present when on sale)
            #   span.regular-price  -> currently-displayed price (discounted if on sale)
            #   button[data-price]  -> historically the original/catalog price,
            #                          so we prefer regular-price when available.
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
                # Fallbacks when the new markup isn't present
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
                # No real discount -> don't expose an original_price that equals current
                original_price = None

            pid = btn.get("data-pid") if btn else None
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
            })
        except Exception:
            continue
    return products


def _sync_scrape_farmaciatei(query: str, max_results: int) -> list:
    """Scrape farmaciatei.ro search results across multiple pages."""
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
            # Dedupe by sku; fall back to source_url when missing.
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
            # Page returned only dupes -> we've reached the end of useful results.
            break

    if not products:
        return [{"message": "Nu s-au gasit produse pentru aceasta cautare.", "source": "farmaciatei.ro"}]
    return products


def _parse_emag_price(text: str) -> float:
    """Parse Romanian-formatted prices like '1.299,99 Lei' or '12999' -> float.

    Handles eMAG's thousands separator '.' and decimal separator ','.
    Some price elements split the integer and decimal into separate spans;
    this function works on the combined text after BeautifulSoup's get_text().
    """
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d,\.]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned:
        # Romanian: "1.299,99" -> integer "1299", decimal "99"
        last_comma = cleaned.rfind(",")
        integer_part = cleaned[:last_comma].replace(".", "")
        decimal_part = cleaned[last_comma + 1:]
        normalized = f"{integer_part}.{decimal_part}" if decimal_part else integer_part
    else:
        # No comma: dots are likely thousands separators ("1.299" -> "1299")
        normalized = cleaned.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def _emag_page_url(encoded_query: str, page: int) -> str:
    """eMAG pagination: /search/<q>/p2/, /search/<q>/p3/, etc."""
    base = f"https://www.emag.ro/search/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_emag_page(soup: BeautifulSoup) -> list:
    """Extract product dicts from an eMAG search results page."""
    products = []
    # eMAG product card markup is fairly stable but uses generic class names;
    # we try the most specific selectors first and fall back to broader ones.
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

            # --- Price extraction ---
            # eMAG renders new price as `.product-new-price` and the (struck-through)
            # old price as `.product-old-price` when on sale.
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

            # eMAG marks unavailable products with a stock badge on the card
            in_stock = item.select_one(".badge-no-stock") is None and item.select_one(".product-stock-status-out") is None

            product_id = item.get("data-product-id") or item.get("data-offer-id") or None

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
            })
        except Exception:
            continue
    return products


def _sync_scrape_emag(query: str, max_results: int) -> list:
    """Scrape eMAG.ro search results across multiple pages."""
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
    """PCGarage pagination: /cauta/<q>/p2/, /cauta/<q>/p3/, etc."""
    base = f"https://www.pcgarage.ro/cauta/{encoded_query}"
    if page <= 1:
        return base
    return f"{base}/p{page}/"


def _parse_pcgarage_page(soup: BeautifulSoup) -> list:
    """Extract product dicts from a PCGarage search results page."""
    products = []
    for card in soup.select("div.product_box"):
        try:
            name_a = card.select_one(".product_box_name a") or card.select_one("h2 a")
            if not name_a:
                continue
            # Card title text contains <b> highlights for the search term;
            # the title attribute has the clean product name.
            name = (name_a.get("title") or name_a.get_text(" ", strip=True)).strip()
            if not name:
                continue
            source_url = name_a.get("href", "") or ""
            if source_url and not source_url.startswith("http"):
                source_url = f"https://www.pcgarage.ro{source_url}"

            # Image: prefer <picture><source srcset> when present, fall back to <img>.
            image_url = ""
            src_el = card.select_one(".product_box_image picture source")
            if src_el:
                srcset = src_el.get("srcset") or ""
                image_url = srcset.split(",")[0].strip().split(" ")[0]
            if not image_url:
                img = card.select_one(".product_box_image img")
                if img:
                    image_url = img.get("src") or img.get("data-src") or ""

            # Price: ".pb-price p.price" -> "7.799,98 RON" (Romanian format).
            price = 0.0
            price_el = card.select_one(".pb-price p.price") or card.select_one(".pb-price")
            if price_el:
                price = _parse_emag_price(price_el.get_text(strip=True))

            # Old price (when on sale) — defensively check several selectors
            # since PCGarage sometimes ships promo markup with a struck-through price.
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

            # Availability: "instock" / "insupplierstock" -> available; "outofstock" -> not.
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
            })
        except Exception:
            continue
    return products


def _sync_scrape_pcgarage(query: str, max_results: int) -> list:
    """Scrape PCGarage.ro search results across multiple pages."""
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
    """Attempt to fetch the EAN/GTIN from a product detail page.

    Supports: farmaciatei.ro (JSON-LD gtin13 / sku),
    sole.ro (plain text "Cod EAN:"), altex.ro (JSON-LD gtin13).
    Returns None if not found or on error.
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

        # Try JSON-LD structured data
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

        # Fallback: look for EAN in plain text (covers sole.ro and farmaciatei.ro)
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
    """Async wrapper for fetch_ean_from_url."""
    return await asyncio.to_thread(fetch_ean_from_url, source_url)


async def scrape_altex(query: str, max_results: int = 100) -> list:
    """Async wrapper - curl_cffi is synchronous, run in a thread."""
    return await asyncio.to_thread(_sync_scrape_altex, query, max_results)


async def scrape_sole(query: str, max_results: int = 100) -> list:
    """Async wrapper - curl_cffi is synchronous, run in a thread."""
    return await asyncio.to_thread(_sync_scrape_sole, query, max_results)


async def scrape_farmaciatei(query: str, max_results: int = 100) -> list:
    """Async wrapper - curl_cffi is synchronous, run in a thread."""
    return await asyncio.to_thread(_sync_scrape_farmaciatei, query, max_results)


async def scrape_emag(query: str, max_results: int = 100) -> list:
    """Async wrapper - curl_cffi is synchronous, run in a thread."""
    return await asyncio.to_thread(_sync_scrape_emag, query, max_results)


async def scrape_pcgarage(query: str, max_results: int = 100) -> list:
    """Async wrapper - curl_cffi is synchronous, run in a thread."""
    return await asyncio.to_thread(_sync_scrape_pcgarage, query, max_results)


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
    # Strategie 1: match exact pe source_url (cel mai precis cand URL-urile
    # raman stabile pe site).
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
    # Strategie 2 (fallback): match dupa primele 40 caractere din nume,
    # case-insensitive. Acopera cazurile in care site-ul si-a schimbat
    # structura URL-urilor sau cand source-ul si source_url-ul stocate au
    # mici inconsistente (ex: salvare manuala cu URL trunchiat).
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
    return None


def _tokenize_query(query: str) -> list:
    """Extract significant tokens (lowercased, length >= 3) from a user query.

    Short tokens ("de", "la", "it") are dropped so filler words don't break
    the relevance match.
    """
    return [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) >= 3]


def filter_by_relevance(products: list, query: str) -> list:
    """Drop products whose name doesn't contain every significant query token.

    Many Romanian shop search engines silently fall back to fuzzy "related"
    results when the exact query has zero matches (e.g. searching "purito
    sleeping pack" on eMAG returns unrelated Vichy creams). This filter keeps
    only products whose name contains ALL significant query tokens as
    substrings (case-insensitive), which matches user intent for specific
    brand+product queries without over-pruning single-word queries.

    Error/message sentinel entries pass through unchanged. If every real
    product is filtered out, we emit a synthetic "no relevant results"
    message so the UI still has something to render.
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
        # We had real results but none matched all tokens → be explicit.
        return [{"message": "Nu s-au gasit rezultate relevante pentru aceasta cautare."}]
    return []
