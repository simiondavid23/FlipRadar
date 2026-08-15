"""Facebook Auto — anunturi de vehicule din Facebook Marketplace.

RESCRIS (2026-07-05): inlocuim Playwright + citirea vizuala (inner_text pe linii,
fragila si nefiltrata pe keyword — intorcea Opel Mokka / camioane MAN / jante) cu
pattern-ul DOVEDIT din Radar Piata (services/radar/facebook_scraper.py): curl_cffi +
cookie-urile din sesiunea salvata + citire STRUCTURATA din JSON-ul server-rendered
(<script type="application/json">). Playwright NU se mai foloseste nicaieri aici.

Reutilizam DIRECT piesele dovedite din Radar (import cross-modul; radar/facebook_scraper
NU importa nimic din scrapers/auto -> fara dependinta circulara): is_facebook_session_valid,
_load_cookies, _build_search_url, _fetch, _iter_listing_objects, _parse_price,
_parse_location, _is_active, _deep_first, _BASE.

Task 1 — diagnostic live (2026-07-05): obiectele de listare din feed-ul de cautare NU au
chei structurate de vehicul (cautare recursiva dupa vehicle_year/vehicle_mileage/
vehicle_fuel_type/... = NICIUNA). Cheile reale: marketplace_listing_title, listing_price
(amount corect, ex "11500.00"), location, primary_listing_photo, marketplace_listing_
category_id, seller, creation_time. Deci an/km se extrag din TITLU cu regex
(extract_year/extract_km din _common), ca la Kleinanzeigen/AutoScout24.

Categoria vehicule = marketplace_listing_category_id "807311116002614" ("Auto, Moto si
Ambarcatiuni") — confirmat live (== id-ul din PLATFORM_CATEGORIES['facebook'] SI ==
category_id de pe anunturile reale de masini). Filtram client-side pe ea ca sa scapam de
jante/piese/necorelate pe care le intoarce cautarea fuzzy FB.
"""
import os
from datetime import datetime
from typing import Optional

from app.scrapers.auto.listings._common import extract_year, extract_km, fold_auto
from app.services.log_manager import log_manager
# Piese DOVEDITE din Radar Piata (curl_cffi, fara Playwright). Import sigur — radar/
# facebook_scraper nu importa nimic din scrapers/auto.
from app.services.radar.facebook_scraper import (
    is_facebook_session_valid, _load_cookies, _build_search_url, _fetch,
    _iter_listing_objects, _parse_price, _parse_location, _is_active, _deep_first, _BASE,
    # FB-5: ancora interim si conversia de fus, tinute intr-un singur loc (modulul FB
    # canonic), ca Radar si Auto sa nu aiba doua implementari care pot diverge.
    _ancora_configurata, _naiv_local,
)
# FB-5: nucleul logat-out. Alias monkeypatch-abil pe modulul asta; calea de sesiune
# (A4) nu il foloseste deloc.
from app.scrapers.facebook import search as nucleu_search

def _is_session_valid(session_path: str) -> bool:
    """Delegat la validatorul Radar (fisier existent + cookie c_user + varsta < 30 zile).
    Pastrat ca API public — /api/auto-listings/stats il importa pentru statusul sesiunii."""
    return is_facebook_session_valid(session_path)


def _vehicles_category_id() -> str:
    """Id-ul categoriei 'Auto, Moto si Ambarcatiuni' din PLATFORM_CATEGORIES['facebook'].
    Confirmat live: 807311116002614 (== marketplace_listing_category_id de pe masini)."""
    try:
        from app.services.radar.categories import PLATFORM_CATEGORIES
        for c in PLATFORM_CATEGORIES.get("facebook", []):
            lbl = (c.get("label") or "").lower()
            if c.get("value") and "auto" in lbl and "moto" in lbl:
                return str(c["value"])
    except Exception:
        pass
    return "807311116002614"


def _aplica_model_supapa(results: list, model_tok: str, model_raw: str,
                         make_raw: str) -> tuple:
    """Post-filtru de MODEL cu SUPAPA (A5.1): daca modelul ar goli o lista care CHIAR
    avea anunturi ale marcii, nu se aplica — mai bine anunturile marcii decat un feed
    gol si tacut, fiindca titlurile FB scriu "320d", nu "Seria 3". O lista deja goala
    nu are ce salva: supapa nu inventeaza rezultate.

    Extras la FB-5 ca ambele cai (sesiune si logout) sa aiba EXACT acelasi
    comportament — singura refactorizare facuta codului de sesiune.
    Intoarce (results, skipped_model).
    """
    skipped_model = 0
    if model_tok and results:
        kept = [r for r in results if model_tok in fold_auto(r["title"])]
        if kept:
            skipped_model = len(results) - len(kept)
            results = kept
        else:
            log_manager.emit("auto_listings", "WARN",
                f"Facebook Auto: modelul '{model_raw}' nu apare in niciun titlu — se pastreaza "
                f"cele {len(results)} anunturi ale marcii {make_raw or '(oricare)'}; "
                f"verifica scrierea modelului")
    return results, skipped_model


def _search_logout(query: str, filters: dict) -> list:
    """Calea LOGAT-OUT (FB_MOD=logout): search prin nucleul FB-1, fara sesiune.

    Filtrele pastreaza ORDINEA si regulile caii de sesiune: categorie de vehicule
    (regula proprie a modulului — absenta categoriei NU exclude, dar o categorie
    diferita da; e alta decat A6/A7 de la Radar, deliberat), marca dura, pretul, apoi
    an/km din titlu si supapa de model prin helperul comun.

    `seller_name` e None: vanzatorul NU exista logat-out (masurat) — lipsa la sursa,
    nu esec de parsare.
    """
    ancora = _ancora_configurata("FB_AUTO_ANCORA", "auto_listings")
    log_manager.emit("auto_listings", "SCAN", f'Facebook Auto logat-out "{query}"')

    max_price = filters.get("price_max")
    try:
        max_price_f = float(max_price) if max_price not in (None, "") else None
    except (ValueError, TypeError):
        max_price_f = None

    veh_cat = _vehicles_category_id()
    make_raw = str(filters.get("make") or "").strip()
    make_tok = fold_auto(make_raw).strip()
    model_raw = str(filters.get("model") or "").strip()
    model_tok = fold_auto(model_raw).strip()

    canonice = nucleu_search(query, ancora.lat, ancora.lon, raza_km=65.0,
                             fb_slug=ancora.fb_slug) or []

    results = []
    vazute = set()
    skipped_cat = skipped_make = 0
    for c in canonice:
        title = (c.get("title") or "").strip()
        if not title:
            continue
        cat_id = c.get("category_id")
        if cat_id is not None and str(cat_id) != veh_cat:
            skipped_cat += 1
            continue
        if make_tok and make_tok not in fold_auto(title):
            skipped_make += 1
            continue

        price = c.get("price")
        if max_price_f and price is not None and price > max_price_f:
            continue

        ext = str(c.get("external_id") or "")
        if not ext or ext in vazute:
            continue
        vazute.add(ext)

        # An/km din TITLU — nici pe calea logat-out nu exista chei structurate.
        image_url = c.get("image_url") or ""
        results.append({
            "external_id":   f"fb_{ext}",
            "platform":      "facebook_auto",
            "title":         title,
            "price":         price,
            "currency":      c.get("currency"),
            "year":          extract_year(title),
            "km":            extract_km(title),
            "location":      c.get("location"),
            "url":           c.get("source_url"),
            "source_url":    c.get("source_url"),
            "thumbnail_url": image_url,
            "image_url":     image_url,
            "seller_name":   None,
            "listed_at":     _naiv_local(c.get("listed_at")),
            "description":   None,
        })

    results, skipped_model = _aplica_model_supapa(results, model_tok, model_raw, make_raw)

    if skipped_cat:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_cat} anunturi excluse (nu sunt categoria vehicule)")
    if skipped_make:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_make} anunturi excluse (titlul nu contine marca '{make_raw}')")
    if skipped_model:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_model} anunturi excluse (titlul nu contine modelul '{model_raw}')")
    log_manager.emit("auto_listings", "OK",
        f'Facebook Auto logat-out: {len(results)} rezultate pentru "{query}"')
    return results


def search_facebook_auto(query: str = "", filters: dict = {}, page: int = 1,
                         max_scrolls: int = 10, session_path: Optional[str] = None) -> list:
    """Cauta vehicule pe Facebook Marketplace prin curl_cffi + JSON structurat.

    Semnatura pastrata compatibila cu apelul din auto_listings_scanner
    (query/filters/page). `page`/`max_scrolls` sunt NO-OP (un singur fetch aduce tot
    feed-ul server-rendered); page>1 -> [] (semnal „gata", ca la Radar).

    FB-AUDIT A2: `session_path` vine de la apelant, rezolvat PER USER cu
    resolve_facebook_session_path. Nu mai exista descoperire pe disc aici — fara cale,
    scanul nu ruleaza (mai bine 0 rezultate decat scan pe contul altui user).

    FB-5 (A4): dispecer pe `FB_MOD`. `logout` = nucleul logat-out; ORICE altceva,
    inclusiv variabila absenta, = calea de sesiune de pana acum, neschimbata.
    Implicitul ramane `sesiune` deliberat (o singura ancora per apel pana la FB-6).
    """
    filters = filters or {}
    query = (query or "").strip()
    if not query:
        return []
    if page and page > 1:
        return []

    mod = (os.getenv("FB_MOD") or "sesiune").strip().lower()
    if mod == "logout":
        return _search_logout(query, filters)
    if mod != "sesiune":
        log_manager.emit("auto_listings", "WARN",
            f"Facebook Auto: FB_MOD='{mod}' necunoscut — folosesc calea de sesiune.")
    return _search_sesiune(query, filters, page, max_scrolls, session_path)


def _search_sesiune(query: str = "", filters: dict = {}, page: int = 1,
                    max_scrolls: int = 10, session_path: Optional[str] = None) -> list:
    """Calea de sesiune, FB_MOD=sesiune — mutata verbatim din search_facebook_auto
    la FB-5 (singura schimbare: supapa de model a devenit apel la
    `_aplica_model_supapa`, folosit identic de ambele cai)."""
    filters = filters or {}
    query = (query or "").strip()
    if not query:
        return []
    if page and page > 1:
        return []

    if not session_path or not is_facebook_session_valid(session_path):
        log_manager.emit("auto_listings", "WARN",
            "Facebook Auto: sesiune expirata/inexistenta. Reautentifica din Setari Radar -> Facebook.")
        return []

    cookies = _load_cookies(session_path)
    min_price = filters.get("price_min")
    max_price = filters.get("price_max")
    try:
        max_price_f = float(max_price) if max_price not in (None, "") else None
    except (ValueError, TypeError):
        max_price_f = None

    url = _build_search_url(query, min_price, max_price)
    log_manager.emit("auto_listings", "SCAN", f'Facebook Auto "{query}"')

    html, final_url = _fetch(url, cookies)
    if html is None:
        return []
    low = (final_url or "").lower()
    if "login" in low or "checkpoint" in low:
        log_manager.emit("auto_listings", "WARN",
            "Facebook Auto: redirect login/checkpoint — sesiune posibil expirata.")
        return []

    veh_cat = _vehicles_category_id()
    # A5 (audit FB): cautarea Marketplace e fuzzy — "BMW Seria 3" aduce si alte marci
    # si modele, iar singurul filtru de pana acum era categoria de vehicule. Marca si
    # modelul vin din filters — scanner-ul le concateneaza in `query`, dar le pastreaza
    # si separat (asa citeste si autovit modelul). Fail-open cand lipsesc/sunt goale.
    #
    # A5.1 — cele doua filtre NU sunt simetrice, deliberat:
    #   MARCA  = filtru dur. Apare aproape mereu in titlu si prinde exact zgomotul
    #            documentat sus (Opel Mokka, camioane MAN, jante de alta marca).
    #   MODEL  = filtru cu SUPAPA (vezi mai jos, dupa bucla). Pe autovit modelul e in
    #            path-ul URL, deci site-ul filtreaza si titlurile il contin; pe Facebook
    #            nu exista filtru server-side, iar un anunt legitim de "Seria 3" se
    #            numeste de regula "BMW 320d Touring" — fara tokenul cerut.
    make_raw = str(filters.get("make") or "").strip()
    make_tok = fold_auto(make_raw).strip()
    model_raw = str(filters.get("model") or "").strip()
    model_tok = fold_auto(model_raw).strip()
    by_id: dict[str, dict] = {}
    for o in _iter_listing_objects(html):
        oid = str(o.get("id"))
        if oid and oid not in by_id:
            by_id[oid] = o

    results = []
    skipped_cat = 0
    skipped_make = 0
    for oid, o in by_id.items():
        if not _is_active(o):
            continue
        title = (o.get("marketplace_listing_title") or "").strip()
        if not title:
            continue
        # Filtru categorie: doar vehicule (scapa de jante/piese/necorelate din cautarea fuzzy).
        cat_id = o.get("marketplace_listing_category_id")
        if cat_id is not None and str(cat_id) != veh_cat:
            skipped_cat += 1
            continue
        # Post-filtru de MARCA (A5.1) — dupa categorie, inainte sa construim rezultatul.
        # Modelul se aplica dupa bucla, ca sa poata avea supapa pe lista intreaga.
        if make_tok and make_tok not in fold_auto(title):
            skipped_make += 1
            continue

        price, currency = _parse_price(o)
        if max_price_f and price is not None and price > max_price_f:
            continue

        # An/km din TITLU — FB search NU expune chei structurate de vehicul (vezi Task 1).
        year = extract_year(title)
        km = extract_km(title)

        image_url = ((o.get("primary_listing_photo") or {}).get("image") or {}).get("uri")
        seller = o.get("marketplace_listing_seller") or {}
        ct = _deep_first(o, "creation_time")
        listed_at = None
        if isinstance(ct, (int, float)) and ct > 1_000_000_000:
            try:
                listed_at = datetime.fromtimestamp(ct)
            except (OverflowError, OSError, ValueError):
                listed_at = None

        results.append({
            "external_id":   f"fb_{oid}",
            "platform":      "facebook_auto",
            "title":         title,
            "price":         price,
            "currency":      currency,
            "year":          year,
            "km":            km,
            "location":      _parse_location(o),
            "url":           f"{_BASE}/marketplace/item/{oid}/",
            "source_url":    f"{_BASE}/marketplace/item/{oid}/",
            "thumbnail_url": image_url or "",
            "image_url":     image_url or "",
            "seller_name":   (seller.get("name") if isinstance(seller, dict) else None),
            "listed_at":     listed_at,
            "description":   None,
        })

    results, skipped_model = _aplica_model_supapa(results, model_tok, model_raw, make_raw)

    if skipped_cat:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_cat} anunturi excluse (nu sunt categoria vehicule)")
    if skipped_make:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_make} anunturi excluse (titlul nu contine marca '{make_raw}')")
    if skipped_model:
        log_manager.emit("auto_listings", "INFO",
            f"Facebook Auto: {skipped_model} anunturi excluse (titlul nu contine modelul '{model_raw}')")
    log_manager.emit("auto_listings", "OK",
        f'Facebook Auto: {len(results)} rezultate pentru "{query}"')
    return results
