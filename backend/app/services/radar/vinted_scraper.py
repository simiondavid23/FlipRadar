"""Scraper pentru Vinted Romania prin API-ul intern v2/catalog/items.

Vinted nu accepta requesturi anonime — avem nevoie de cookie-ul de sesiune
copiat din browserul logat al userului (Application -> Cookies -> access_token_web).
Cookie-ul se stocheaza in radar_settings.vinted_cookie si se trimite ca header
"Cookie" la fiecare cerere.
"""
import re
import time
from datetime import datetime
from typing import Optional

from curl_cffi import requests as curl_requests

from app.services.radar.base_scraper import build_headers, rate_limit_backoff, is_excluded, get_proxy_config
from app.services.radar.categories import VINTED_CATEGORY_IDS


_IMPERSONATE = "chrome110"
_API_URL = "https://www.vinted.ro/api/v2/catalog/items"


def get_vinted_token(cookie_str: str) -> Optional[str]:
    """Extrage access_token_web din string-ul de cookie copiat din browser."""
    if not cookie_str:
        return None
    m = re.search(r"access_token_web=([^;]+)", cookie_str)
    if m:
        return m.group(1).strip()
    # Daca userul a copiat doar valoarea, presupunem ca asta e
    if "=" not in cookie_str and len(cookie_str) > 20:
        return cookie_str.strip()
    return None


def _condition_label(api_label: Optional[str]) -> Optional[str]:
    if not api_label:
        return None
    t = api_label.lower()
    if "nou" in t or "new" in t:
        return "nou"
    if "bun" in t or "good" in t or "satisf" in t or "purtat" in t or "rezonab" in t:
        return "second hand"
    return None


def search_vinted(
    keyword: str,
    max_price: float,
    condition: str = "all",
    exclude_words: Optional[list[str]] = None,
    cookie_str: Optional[str] = None,
    min_price: Optional[float] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Cauta pe Vinted prin API-ul intern si returneaza listinguri standard."""
    exclude_words = exclude_words or []
    keyword_clean = (keyword or "").strip()
    if not keyword_clean:
        return []
    if not cookie_str:
        print("[VintedScraper] Cookie Vinted lipseste — skip.")
        return []

    params = {
        "search_text": keyword_clean,
        "per_page": 48,
        "order": "newest_first",
    }
    if max_price and max_price > 0:
        params["price_to"] = int(max_price)
        params["currency"] = "RON"
    if min_price and min_price > 0:
        params["price_from"] = int(min_price)
        params["currency"] = "RON"
    if category:
        cat_id = VINTED_CATEGORY_IDS.get(category)
        if cat_id:
            # Vinted accepta repetate `catalog_ids[]=...` — curl_cffi gestioneaza
            # automat listele transmise ca tuple/list.
            params["catalog_ids[]"] = cat_id

    headers = build_headers({
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie_str,
        "Referer": "https://www.vinted.ro/",
        "X-Requested-With": "XMLHttpRequest",
    })

    proxy_cfg = get_proxy_config()
    request_kwargs = {
        "headers": headers, "params": params,
        "impersonate": _IMPERSONATE, "timeout": 20,
    }
    if proxy_cfg:
        request_kwargs["proxies"] = {"http": proxy_cfg["http"], "https": proxy_cfg["https"]}

    data = None
    for attempt in range(3):
        try:
            resp = curl_requests.get(_API_URL, **request_kwargs)
            if resp.status_code in (401, 403):
                print(f"[VintedScraper] Cookie expirat ({resp.status_code}) — necesita reconectare.")
                # Santinela: semnaleaza caller-ului ca eroarea e de autentificare
                # (cookie expirat), spre deosebire de un simplu rezultat gol.
                return [{"__vinted_auth_error": True}]
            if resp.status_code == 200:
                data = resp.json()
                break
            if resp.status_code == 429:
                delay = rate_limit_backoff(attempt)
                print(f"[VintedScraper] 429 rate limit, retry {attempt+1}/3 dupa {delay:.1f}s")
                time.sleep(delay)
                continue
            print(f"[VintedScraper] HTTP {resp.status_code}")
            return []
        except Exception as exc:
            print(f"[VintedScraper] Eroare ({attempt+1}/3): {exc}")
            time.sleep(rate_limit_backoff(attempt))

    if not data:
        return []

    items = data.get("items") or []
    results = []
    for it in items:
        try:
            title = (it.get("title") or "").strip()
            if not title:
                continue
            if is_excluded(title, exclude_words):
                continue

            price_data = it.get("price") or {}
            if isinstance(price_data, dict):
                price = float(price_data.get("amount") or 0)
                currency = price_data.get("currency_code") or "RON"
            else:
                price = float(it.get("price_numeric") or 0)
                currency = it.get("currency") or "RON"

            if price <= 0:
                continue
            if max_price and price > max_price:
                continue
            if min_price and price < min_price:
                continue

            cond_text = it.get("status") or it.get("size_title")
            cond = _condition_label(cond_text)
            if condition == "new" and cond != "nou":
                continue
            if condition == "used" and cond != "second hand":
                continue

            photo = it.get("photo") or {}
            image_url = photo.get("url") or photo.get("full_size_url")
            images = [image_url] if image_url else []

            user = it.get("user") or {}
            seller_id = str(user.get("id")) if user.get("id") is not None else None
            seller_name = user.get("login") or user.get("name")

            url = it.get("url") or f"https://www.vinted.ro/items/{it.get('id')}"
            ext_id = f"vinted_{it.get('id')}"

            listed_at = None
            ts = it.get("created_at_ts") or it.get("photo", {}).get("high_resolution", {}).get("timestamp")
            if ts:
                try:
                    listed_at = datetime.fromtimestamp(int(ts))
                except (TypeError, ValueError, OSError):
                    listed_at = None

            results.append({
                "external_id": ext_id,
                "platform": "vinted",
                "title": title,
                "price": price,
                "currency": currency,
                "condition": cond,
                "location": user.get("country_title") or user.get("country_code"),
                "url": url,
                "images": images,
                "description": it.get("description"),
                "seller_name": seller_name,
                "seller_id": seller_id,
                "listed_at": listed_at,
            })
        except Exception as exc:
            print(f"[VintedScraper] Eroare la parsare item: {exc}")
            continue

    print(f"[VintedScraper] {len(results)} rezultate pentru '{keyword_clean}'")
    return results
