"""Enrichment on-demand al detaliului unui anunt auto (poze/descriere/vanzator/data).

MIRROR pe pattern-ul dovedit din Radar (fetch_X_listing_details din services/radar/*),
adaptat pentru Auto Anunturi. Logica de imagini/descriere e reprodusa (cu citarea sursei
per platforma) ca sa NU cuplam modulul auto de serviciul radar.

Semnatura comuna: fetch_X_detail(url) -> {"images": [...], "description": str|None,
"seller_name": str|None, "listed_at": datetime|None}. Facebook are session_path in plus.

REGULA: la orice esec / selector negasit -> camp None/[], FARA exceptie. Caller-ul
(endpoint) seteaza detail_fetched=True DOAR daca fetch-ul a intors ceva util (ca la Vinted).
Nu inventam selectoare/chei pe care nu le-am verificat live — cele neconfirmate raman None.
"""
import json
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi

from app.scrapers.auto.listings._common import IMPERSONATE, build_headers, safe_soup

_EMPTY = {"images": [], "description": None, "seller_name": None, "listed_at": None}

_RO_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}


def _fetch(url: str, referer: str) -> Optional[str]:
    """GET curl_cffi; None la orice eroare / non-200 (fara exceptie)."""
    if not url:
        return None
    try:
        r = cffi.get(url, headers=build_headers({"Referer": referer}),
                     impersonate=IMPERSONATE, timeout=25)
        return r.text if r.status_code == 200 else None
    except Exception as exc:
        print(f"[auto detail] fetch eroare {url[:60]}: {str(exc)[:80]}")
        return None


def _parse_ro_date(text: str) -> Optional[datetime]:
    """"4 iulie 2026 la 12:16" / "30 iunie 2026" -> datetime (confirmat live pe autovit.ro)."""
    if not text:
        return None
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(_RO_MONTHS) + r")\s+(\d{4})(?:\s+la\s+(\d{1,2}):(\d{2}))?",
        text, re.I)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), _RO_MONTHS[m.group(2).lower()], int(m.group(1)),
                        int(m.group(4)) if m.group(4) else 0, int(m.group(5)) if m.group(5) else 0)
    except (ValueError, KeyError):
        return None


# ── Autovit (CONFIRMAT LIVE) ─────────────────────────────────────────────────
# Imagini+descriere: aceeasi logica ca app.services.radar.autovit_scraper.
#   fetch_autovit_listing_details (apollo.olxcdn), dar cu selectorul de descriere ACTUAL
#   confirmat azi ([data-testid="content-description-section"]; cel vechi ad-description
#   nu mai exista). NOU vs Radar: data postarii + vanzator (confirmate live azi).
def _autovit_common(soup: BeautifulSoup) -> dict:
    imgs, seen = [], set()
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if "apollo.olxcdn.com" in src and not src.endswith(".svg"):
            up = re.sub(r";s=\d+x\d+", ";s=1000x1000", src)
            if up not in seen:
                seen.add(up); imgs.append(up)
    desc_el = (soup.find(attrs={"data-testid": "content-description-section"})
               or soup.find(attrs={"data-testid": "ad-description"})
               or soup.find(attrs={"data-cy": "ad_description"}))
    description = desc_el.get_text("\n", strip=True) or None if desc_el else None

    text = soup.get_text(" ", strip=True)
    listed_at = _parse_ro_date(text)
    # Vanzator: sub headingul "Informatii despre vanzator", numele e inaintea tipului
    # (Dealer / Persoana fizica / "Vanzator pe Autovit.ro"). Structura poate varia usor.
    seller_name = None
    ms = re.search(r"Informa[țt]ii despre v[aâ]nz[aă]tor\s+(.{1,60}?)\s+"
                   r"(?:Dealer|Persoan[aă] fizic[aă]|V[aâ]nz[aă]tor pe)", text, re.I)
    if ms:
        seller_name = ms.group(1).strip() or None
    return {"images": imgs, "description": description,
            "seller_name": seller_name, "listed_at": listed_at}


def fetch_autovit_detail(url: str) -> dict:
    html = _fetch(url, "https://www.autovit.ro/")
    return _autovit_common(safe_soup(html)) if html else dict(_EMPTY)


# ── OLX Auto ─────────────────────────────────────────────────────────────────
# OLX (grupul OLX) agrega anunturi Autovit — URL-urile de detaliu OLX Auto sunt frecvent
# pagini autovit.ro cu structura identica (confirmat live: acelasi apollo.olxcdn, aceeasi
# sectiune "Informatii despre vanzator", acelasi format de data). Reutilizam logica autovit;
# fallback pe selectorii OLX (olxcdn generic + ad-description) daca e o pagina OLX nativa.
def fetch_olx_auto_detail(url: str) -> dict:
    html = _fetch(url, "https://www.olx.ro/")
    if not html:
        return dict(_EMPTY)
    soup = safe_soup(html)
    out = _autovit_common(soup)  # acopera cazul (frecvent) de pagina autovit agregata
    if not out["images"]:  # pagina OLX nativa: imagini pe olxcdn.com generic
        imgs, seen = [], set()
        for img in soup.select("img"):
            src = (img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "")
            if ("olxcdn.com" in src or "olx-cdn.com" in src) and not src.startswith("data:"):
                up = re.sub(r";s=\d+x\d+", ";s=1000x1000", src)
                if up not in seen:
                    seen.add(up); imgs.append(up)
        out["images"] = imgs
    return out


# ── Mobile.de ────────────────────────────────────────────────────────────────
# Detaliu on-demand prin patchright (curl e blocat de Imperva, ca la search). Selectoare
# CONFIRMATE LIVE 2026-07 pe o pagina reala de detaliu:
#   - descriere: element cu data-testid ce CONTINE "description" (regex — testid-ul exact e
#     ofuscat dar contine mereu "description"); ~4700 char "Fahrzeugbeschreibung laut Anbieter".
#   - galerie: DOAR img.classistatic.de/api/v1/mo-prod/images/... (poze reale), NU
#     static.classistatic.de/static/... (chrome-ul paginii); variantele de marime au acelasi
#     UUID cu ?rule=mo-NNN -> dedup pe UUID + cerem varianta mare (?rule=mo-1600).
#   - seller_name/listed_at: NU apar curat (adresa/Handler-Suche/Erstzulassung nu sunt numele
#     vanzatorului / data anuntului) -> raman None. Nu ghicim.
# Lansare identica cu mobile_de_scraper.py::_search_mobile_de_playwright: channel=chrome ->
# fallback Chromium bundled, headless=False (constrangerea Imperva), context minimal,
# block-markers -> dict(_EMPTY). Fereastra headed ~5-8s la PRIMA deschidere (rezultat cache-uit).
def fetch_mobilede_detail(url: str) -> dict:
    if not url:
        return dict(_EMPTY)
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return dict(_EMPTY)

    html = None
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=False, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=False)
            pw_page = browser.new_context().new_page()
            try:
                pw_page.goto(url, wait_until="domcontentloaded", timeout=45000)
                pw_page.wait_for_timeout(5000)
                try:
                    pw_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                if any(m in pw_page.inner_text("body")[:400].lower()
                       for m in ("access denied", "zugriff verweigert", "captcha")):
                    return dict(_EMPTY)
                html = pw_page.content()
            finally:
                browser.close()
    except Exception as exc:
        print(f"[mobile_de detail] patchright eroare: {exc}")
        return dict(_EMPTY)
    if not html:
        return dict(_EMPTY)

    soup = safe_soup(html)
    desc_el = (soup.find(attrs={"data-testid": re.compile("description", re.I)})
               or soup.find(class_=re.compile(r"description|beschreibung", re.I)))
    description = (desc_el.get_text("\n", strip=True) or None) if desc_el else None

    imgs, seen = [], set()
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or ""
        if "img.classistatic.de" not in src or "/mo-prod/images/" not in src:
            continue
        base = src.split("?")[0]              # dedup pe UUID (nu pe varianta de marime)
        if base in seen:
            continue
        seen.add(base)
        imgs.append(base + "?rule=mo-1600")   # varianta mare
    return {"images": imgs, "description": description, "seller_name": None, "listed_at": None}


# ── AutoScout24 (__NEXT_DATA__, BEST-EFFORT, NEVERIFICAT pe un listing real) ──
# autoscout24.ro/lst e client-rendered (Next.js): listingurile + URL-urile lor sunt in
# __NEXT_DATA__, iar HTML-ul static contine DOAR linkuri /dealerinfo/. Din acest motiv
# scraper-ul de search stocheaza URL-uri de DEALER, nu de anunt — deci nu am putut verifica
# aceasta functie pe un URL de anunt real capturat din scraper. Implementare structurala
# best-effort; daca structura nu se potriveste -> None (nu inventam).
def _collect_key(node, key, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                out.append(v)
            _collect_key(v, key, out)
    elif isinstance(node, list):
        for v in node:
            _collect_key(v, key, out)


def _html_to_text(raw) -> Optional[str]:
    """Curata o descriere care poate veni cu HTML brut (AutoScout24 trimite descrierea
    in JSON cu <br>, <ul><li>, <p>). PASTREAZA structura: fiecare <li> devine o linie cu
    bullet, blocurile (<p>/<div>) devin linii separate — ca sa NU se lipeasca cuvintele
    (simplul strip de tag-uri ar concatena "Klima" + "Textul urmator"). Fara HTML ->
    doar strip. Returneaza None pentru gol.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    if "<" not in raw or ">" not in raw:
        return raw.strip() or None
    soup = safe_soup(raw)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
        li.insert_after("\n")
    for block in soup.find_all(["p", "div", "ul", "ol", "tr", "h1", "h2", "h3", "h4"]):
        block.insert_after("\n")
    lines = [ln.strip() for ln in soup.get_text().splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    return cleaned or None


def fetch_autoscout24_detail(url: str) -> dict:
    html = _fetch(url, "https://www.autoscout24.ro/")
    if not html:
        return dict(_EMPTY)
    soup = safe_soup(html)
    nd = soup.select_one("script#__NEXT_DATA__")
    if not nd or not nd.string:
        return dict(_EMPTY)
    try:
        data = json.loads(nd.string)
    except Exception:
        return dict(_EMPTY)

    images = []
    for lst in _next_lists(data, ("images", "galleryImages", "pictures")):
        uris = []
        for el in lst:
            if isinstance(el, str) and el.startswith("http"):
                uris.append(el)
            elif isinstance(el, dict):
                u = el.get("url") or el.get("uri") or el.get("src") or (el.get("mainImageUrl"))
                if isinstance(u, str) and u.startswith("http"):
                    uris.append(u)
        if len(uris) > len(images):
            images = uris

    description = _html_to_text(_first_str(data, ("description", "vehicleDescription", "sellerDescription")))
    seller_name = _first_str(data, ("companyName", "sellerName", "dealerName"))
    listed_at = None
    for k in ("firstRegistrationDate", "firstRegistration"):
        v = _first_str(data, (k,))
        if v:
            try:
                listed_at = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                listed_at = None
            break
    return {"images": images, "description": description,
            "seller_name": seller_name, "listed_at": listed_at}


def _next_lists(data, keys):
    for k in keys:
        out = []
        _collect_key(data, k, out)
        for v in out:
            if isinstance(v, list) and v:
                yield v


def _first_str(data, keys):
    for k in keys:
        out = []
        _collect_key(data, k, out)
        for v in out:
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


# ── Kleinanzeigen (CONFIRMAT LIVE pe un anunt real) ──────────────────────────
# Selectoare confirmate azi pe /s-anzeige/*: galerie img.kleinanzeigen.de,
# #viewad-description-text, #viewad-extra-info (data "DD.MM.YYYY"), .userprofile-vip a.
def fetch_kleinanzeigen_detail(url: str) -> dict:
    html = _fetch(url, "https://www.kleinanzeigen.de/")
    if not html:
        return dict(_EMPTY)
    soup = safe_soup(html)
    imgs, seen = [], set()
    for img in soup.select("#viewad-image, .galleryimage-element img, img[data-imgsrc], img"):
        src = img.get("src") or img.get("data-imgsrc") or img.get("data-src") or ""
        if "img.kleinanzeigen.de" in src and not src.startswith("data:") and src not in seen:
            seen.add(src); imgs.append(src)
    desc_el = soup.select_one("#viewad-description-text")
    description = desc_el.get_text("\n", strip=True) or None if desc_el else None
    seller_el = soup.select_one(".userprofile-vip a, .userprofile-vip-details-text a, "
                                "[data-liid='sellerName'] a")
    seller_name = seller_el.get_text(" ", strip=True) or None if seller_el else None
    listed_at = None
    date_el = soup.select_one("#viewad-extra-info")
    if date_el:
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_el.get_text(" ", strip=True))
        if m:
            try:
                listed_at = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                listed_at = None
    return {"images": imgs, "description": description,
            "seller_name": seller_name, "listed_at": listed_at}


# ── Facebook Auto (adaptat din radar.facebook_scraper.fetch_facebook_listing_detail) ──
# Mecanismul dovedit: cautare STRUCTURALA de chei JSON in <script> (redacted_description,
# listing_photos). EXTINS best-effort pentru vanzator/data — chei PLAUZIBILE (nu confirmate
# live in aceasta implementare, n-am sesiune FB de test): "creation_time"/"listing_time"
# pentru data, "marketplace_listing_seller"/"seller" pentru vanzator. Daca nu se gasesc -> None.
_SCRIPT_JSON_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)


def fetch_facebook_detail(url: str, session_path: Optional[str] = None) -> dict:
    # Reutilizeaza direct functia dovedita din Radar pentru descriere+galerie (session-aware).
    try:
        from app.services.radar.facebook_scraper import (
            fetch_facebook_listing_detail, is_facebook_session_valid, _load_cookies, _fetch as _fb_fetch)
    except Exception:
        return dict(_EMPTY)
    base = fetch_facebook_listing_detail(url, session_path)  # {"description", "images"}
    out = {"images": base.get("images") or [], "description": base.get("description"),
           "seller_name": None, "listed_at": None}
    # Extindere structurala pentru vanzator/data (best-effort, chei neconfirmate live).
    try:
        if not url or not is_facebook_session_valid(session_path):
            return out
        html, _ = _fb_fetch(url, _load_cookies(session_path))
        if not html:
            return out
        for block in _SCRIPT_JSON_RE.findall(html):
            try:
                data = json.loads(block)
            except Exception:
                continue
            if out["seller_name"] is None:
                for s in _collect_scalar(data, ("marketplace_listing_seller", "seller")):
                    name = s.get("name") if isinstance(s, dict) else (s if isinstance(s, str) else None)
                    if isinstance(name, str) and name.strip():
                        out["seller_name"] = name.strip(); break
            if out["listed_at"] is None:
                for t in _collect_scalar(data, ("creation_time", "listing_time")):
                    if isinstance(t, (int, float)) and t > 1_000_000_000:
                        try:
                            out["listed_at"] = datetime.utcfromtimestamp(int(t)); break
                        except (ValueError, OSError):
                            pass
    except Exception:
        pass
    return out


def _collect_scalar(node, keys):
    out = []
    for k in keys:
        _collect_key(node, k, out)
    return out


# Dispatch platforma -> functie (folosit de endpoint).
DETAIL_FETCHERS = {
    "autovit": fetch_autovit_detail,
    "olx_auto": fetch_olx_auto_detail,
    "mobile_de": fetch_mobilede_detail,
    "autoscout24": fetch_autoscout24_detail,
    "kleinanzeigen_auto": fetch_kleinanzeigen_detail,
    "facebook_auto": fetch_facebook_detail,
}
