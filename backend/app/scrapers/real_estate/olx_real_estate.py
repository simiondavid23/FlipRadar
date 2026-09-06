"""OLX.ro — anunturi imobiliare. platform="olx"."""
import json
import random
import re
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from curl_cffi.requests import AsyncSession

from app.scrapers.real_estate._common import (
    IMPERSONATE, MAX_RESULTS, build_headers, parse_price,
    extract_rooms, extract_surface, detect_currency, make_re_listing, norm_city_slug,
    url_dedup_key,
)
from app.scrapers.real_estate.re_categories import apply_re_filters, RE_FILTER_ALIASES
from app.services.log_manager import log_manager
from app.utils.listing_dates import iso_to_naive_local, normalize_iso
from app.utils.olx_state import extract_olx_ad_meta

_BASE = "https://www.olx.ro"

# IMO-1 — enrichment de detaliu DOAR pe anunturile noi (oglinda RP-3 din Radar).
# Cardul din lista are doar tokenul -ID.html; API-ul /api/v1/offers/{id}
# cere id-ul NUMERIC, prezent in __PRERENDERED_STATE__.ads[] pe pagina de lista.
# Adaptare locala dupa services/radar/olx_scraper (conventia: fara import cross-modul).
_ENRICH_CAP = 10                  # max fetch-uri de detaliu per scanare
_ENRICH_DELAY_RANGE = (1.0, 2.0)  # delay politicos intre fetch-uri


# OLX-IMO-1 — anunturile Storia incrucisate de OLX in propria lista.
# Masurat pe `olx_re_listing_state.html`: 25 din 51 de carduri nu trimit la OLX, ci la
# `storia.ro/ro/oferta/<slug>-ID<token>` (FARA `.html`). Le PASTRAM in feed — un keyword
# doar pe OLX nu are voie sa piarda jumatate din pagina — cu `external_id` prefixat.
_HOST_INCRUCISAT = "storia.ro"
_PREFIX_INCRUCISAT = "storia-"

# Tokenul `-ID<token>`, ancorat la finalul PATH-ului. `.html` e OPTIONAL: cardurile
# proprii OLX il au, cele Storia nu.
_RX_OLX_ID = re.compile(r"-ID([A-Za-z0-9]+?)(?:\.html)?$")


def _olx_id(href: str):
    """Tokenul `-ID<token>` al unui link de card OLX; None daca lipseste.

    Query-ul si fragmentul se taie INAINTE de match (cardurile proprii OLX poarta
    `?search_reason=search%7Cpromoted`), iar `.html` e optional — vezi `_RX_OLX_ID`.
    """
    cale = str(href or "").split("#")[0].split("?")[0].rstrip("/")
    m = _RX_OLX_ID.search(cale)
    return m.group(1) if m else None


def _external_id_card(href: str) -> Optional[str]:
    """PURA: `external_id`-ul unui card din lista OLX; None cand linkul n-are token.

    Cardurile proprii OLX -> tokenul brut (`kTodo`). Anunturile Storia incrucisate ->
    `storia-<token>` (`storia-HE6J`): prefixul le face vizibile ca atare si exclude prin
    constructie orice coliziune cu tokenii OLX, care nu contin `-`. Nu se poate ciocni
    nici cu `external_id`-ul scraperului Storia, care e NUMERIC (`10502931`).
    """
    tok = _olx_id(href)
    if not tok:
        return None
    if url_dedup_key(href).startswith(f"https://{_HOST_INCRUCISAT}/"):
        return _PREFIX_INCRUCISAT + tok
    return tok


def _pick_thumb(img) -> Optional[str]:
    """IMO-1 — URL-ul thumbnail-ului dintr-un tag <img> de card (functie PURA, testabila).

    Cardurile lazy-load au `src` placeholder (data:image/...); poza reala e in srcset.
    Ultimul candidat din srcset = rezolutia cea mai mare.
    """
    if not img:
        return None
    thumb = img.get("src") or img.get("data-src")
    if (not thumb or str(thumb).startswith("data:")) and img.get("srcset"):
        cand = img["srcset"].split(",")[-1].strip().split(" ")[0]
        thumb = cand or thumb
    return thumb


# OLX-STATE-1: `_extract_numeric_ids` a disparut de aici — id-ul numeric vine din
# `extract_olx_ad_meta` (app/utils/olx_state.py), din ACEEASI parsare de state ca
# datele. Era a doua parsare a aceluiasi HTML (~470 ms per pagina).


def _parse_iso_dt(s):
    """ISO 8601 cu offset ('2026-07-07T12:08:09+03:00') -> datetime NAIV local
    (consecvent cu conventia listed_at a scraperelor).

    HOTFIX CI — nu mai e o copie locala: deleaga la `iso_to_naive_local`, care
    converteste EXPLICIT la Europe/Bucharest, nu la fusul masinii (vezi nota din
    services/radar/olx_scraper.py::_parse_iso_dt).
    """
    return iso_to_naive_local(s)


def _first_int(text):
    """Primul numar intreg dintr-un text ("3 camere" -> 3); None daca nu exista."""
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None


def _first_float(text):
    """Primul numar (cu zecimale) dintr-un text ("54,5 m²" -> 54.5); None daca nu exista."""
    m = re.search(r"\d+(?:[.,]\d+)?", str(text or ""))
    return float(m.group().replace(",", ".")) if m else None


def _map_offer_details(data: dict) -> dict:
    """Mapeaza `data` din /api/v1/offers/{id} la cheile noastre (functie PURA, testabila
    pe fixture): descriere, images, zone, locatie_oras, suprafata_mp, etaj, camere, listed_at.

    Tolerant la chei lipsa/corupte: ce nu se poate mapa pur si simplu nu apare in dict,
    iar apelantul pastreaza ce avea deja de pe card.
    """
    out: dict = {}
    if not isinstance(data, dict):
        return out

    desc = data.get("description")
    if desc:
        txt = re.sub(r"<[^>]+>", " ", str(desc))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out["descriere"] = txt

    images = []
    for photo in (data.get("photos") or [])[:5]:
        link = photo.get("link") if isinstance(photo, dict) else None
        if not link:
            continue
        # Placeholder-ul {width}x{height} din API -> rezolutie concreta.
        images.append(str(link).replace("{width}x{height}", "1000x700"))
    if images:
        out["images"] = images

    loc = data.get("location") or {}
    if isinstance(loc, dict):
        district = (loc.get("district") or {}).get("name") if isinstance(loc.get("district"), dict) else None
        if district:
            out["zone"] = district   # cartierul — intrarea directa in normalize_zone
        city = (loc.get("city") or {}).get("name") if isinstance(loc.get("city"), dict) else None
        if city:
            out["locatie_oras"] = city

    for p in (data.get("params") or []):
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").lower()
        name = str(p.get("name") or "").lower()
        val = p.get("value") if isinstance(p.get("value"), dict) else {}
        vkey = val.get("key")
        label = val.get("label")
        try:
            if key == "m" or "suprafa" in name:
                v = _first_float(vkey) if vkey is not None else None
                if v is None:
                    v = _first_float(label)
                if v is not None:
                    out["suprafata_mp"] = v
            elif key == "floor" or "etaj" in name:
                if label:
                    out["etaj"] = str(label)
            elif key == "rooms" or "camere" in name:
                # Sonda IMO-DIAG (07.2026): OLX Imobiliare NU trimite cheia rooms in params
                # (doar compartimentare/price/m/constructie/floor). Ramura ramane ca plasa de
                # siguranta — se auto-activeaza daca OLX o adauga; camere vine azi din titlu/descriere.
                v = _first_int(vkey) if vkey is not None else None
                if v is None:
                    v = _first_int(label)
                if v is not None:
                    out["camere"] = v
        except (TypeError, ValueError):
            continue

    dt = _parse_iso_dt(data.get("created_time"))
    if dt:
        # STRING ISO naiv local — acelasi format pe care il emite deja scraperul din card.
        out["listed_at"] = dt.isoformat()
    return out


def _fetch_offer_details(numeric_id) -> dict:
    """GET /api/v1/offers/{id} -> dict mapat prin _map_offer_details; {} la esec."""
    if not numeric_id:
        return {}
    try:
        resp = curl_requests.get(
            f"{_BASE}/api/v1/offers/{numeric_id}",
            headers=build_headers({
                "Referer": _BASE + "/",
                "Accept": "application/json, text/plain, */*",
            }),
            impersonate=IMPERSONATE, timeout=20,
        )
        if resp.status_code != 200:
            return {}
        data = (resp.json() or {}).get("data") or {}
    except Exception as exc:
        print(f"[olx_re] offer details eroare ({numeric_id}): {exc}")
        return {}
    return _map_offer_details(data)


# Parser de data OLX — logica adaptata din services/radar/olx_scraper._parse_olx_date
# (copie locala, NU import cross-modul din radar/). `now` injectat pentru testabilitate.
_OLX_RO_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
    "ian": 1, "feb": 2, "mar": 3, "apr": 4,
    "iun": 6, "iul": 7, "aug": 8, "sep": 9, "oct": 10, "noi": 11, "dec": 12,
}


# DATE-2 — etichetele care marcheaza o REACTUALIZARE (regula DATE-1). Copie locala,
# ca si `_parse_olx_date`: `services/radar/olx_scraper` nu se importa din `scrapers/`.
_ETICHETE_REACTUALIZARE = ("reactualizat", "actualizat")


def _este_reactualizare(text) -> bool:
    """True daca textul de data al cardului e etichetat ca reactualizare.

    Data astfel etichetata merge in `refreshed_at` si NICIODATA in `listed_at`; altfel
    un anunt vechi repromovat ieri ar trece de filtrele de vechime ca si cum ar fi nou.
    """
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return any(e in t for e in _ETICHETE_REACTUALIZARE)


def _parse_olx_date(text, now: datetime):
    """Data din cardul OLX ("Azi la HH:MM" / "Ieri la HH:MM" / "d luna yyyy") -> datetime | None.

    `now` injectat (testabil). Diacriticele lunilor se normalizeaza NFKD->ascii inainte de match.
    Ora lipsa la formatul cu data -> 00:00. Text nerecunoscut/None -> None. Rezultat NAIV (aceeasi
    zona ca `now` — OLX afiseaza ora locala), consecvent cu coloanele TIMESTAMP naive (found_at).
    """
    if not text:
        return None
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().strip().lower()
    # SCRAPE-AUDIT: anunturile repromovate au prefixul "Reactualizat"/"Postat" —
    # fara stripare, startswith("azi"/"ieri") nu mai prindea si data se pierdea.
    for _pref in ("reactualizat", "postat", "adaugat"):
        if t.startswith(_pref):
            t = t[len(_pref):].strip()
    m_time = re.search(r"(\d{1,2}):(\d{2})", t)
    hour = int(m_time.group(1)) if m_time else 0
    minute = int(m_time.group(2)) if m_time else 0
    if t.startswith("azi"):
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t.startswith("ieri"):
        d = now - timedelta(days=1)
        return d.replace(hour=hour, minute=minute, second=0, microsecond=0)
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", t)
    if m:
        month = _OLX_RO_MONTHS.get(m.group(2))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                return None
    return None


def _olx_path(tip_anunt: str, tip_proprietate: str) -> str:
    rent = (tip_anunt or "").lower().startswith("inchiri")
    suffix = "de-inchiriat" if rent else "de-vanzare"
    tp = (tip_proprietate or "apartament").lower()
    if tp.startswith("cas"):
        return f"/imobiliare/case-{suffix}/"
    if tp.startswith("teren"):
        return "/imobiliare/terenuri/"
    if tp.startswith("comerc"):
        # CONFIRMAT LIVE 2026-07-06: categoria reala e /imobiliare/birouri-spatii-comerciale/
        # — o SINGURA categorie pt vanzare+inchiriere, FARA suffix. Vechiul
        # /imobiliare/spatii-comerciale-{de-vanzare|de-inchiriat}/ dadea HTTP 404.
        return "/imobiliare/birouri-spatii-comerciale/"
    # apartament / garsoniera
    return f"/imobiliare/apartamente-garsoniere-{suffix}/"


def _olx_build_url(filters: dict) -> tuple:
    """Construieste (url, params) pentru cautarea OLX Imobiliare. Functie pura, testabila.

    - baza: categoria din _olx_path(tip_anunt, tip_proprietate);
    - ORAS: daca filters["locatie"] e setat -> segment de path norm_city_slug(locatie) + "/".
      Confirmat live 2026-07-11 (sonda T3 bucuresti / T4 cluj-napoca / T5 +filter_float_price /
      T8 +q-text): path-ul de oras filtreaza corect si coexista cu pretul si cu q-.
    - CAMERE: NU se mai pune segment /N-camere/. Path-ul ar filtra EXACT N, dar semantica
      produsului e MINIM N => camerele se filtreaza LOCAL in post-filtrul scannerului (IM-1).
    - QUERY (cautare libera): daca filters["query"] e setat -> segment "q-" +
      norm_city_slug(query) + "/", DUPA oras (ordinea oras -> q- confirmata de sonda T8).
    - params: search[order]=created_at:desc + campurile confirmate (pret) via apply_re_filters.
    """
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url = _BASE + _olx_path(tip_anunt, tip_proprietate)
    if filters.get("locatie"):
        url = url.rstrip("/") + "/" + norm_city_slug(filters["locatie"]) + "/"
    if filters.get("query"):
        url = url.rstrip("/") + "/q-" + norm_city_slug(filters["query"]) + "/"

    params = {"search[order]": "created_at:desc"}
    # Pret via campuri confirmate (search[filter_float_price:from/to]) — vezi re_categories.
    apply_re_filters("olx_real_estate", filters, params, aliases=RE_FILTER_ALIASES)
    return url, params


async def search_olx_real_estate(filters: dict = {}, skip_enrich_ids: Optional[set] = None) -> list:
    filters = filters or {}
    tip_anunt = filters.get("tip_anunt", "vanzare")
    tip_proprietate = filters.get("tip_proprietate", "apartament")
    url, params = _olx_build_url(filters)

    headers = build_headers({"Referer": _BASE + "/"})
    log_manager.emit("real_estate", "SCAN", f"OLX Imobiliare: {tip_proprietate} {tip_anunt}")
    results = []
    html = ""
    try:
        async with AsyncSession() as session:
            resp = await session.get(url, params=params, headers=headers, impersonate=IMPERSONATE, timeout=20)
            if resp.status_code != 200:
                print(f"[olx_re] HTTP {resp.status_code}")
                log_manager.emit("real_estate", "ERR", f"OLX Imobiliare: HTTP {resp.status_code}")
                return []
            # IMO-1 — pastram HTML-ul: __PRERENDERED_STATE__ (id-urile numerice) se
            # citeste dupa parsarea cardurilor, iar `resp` nu mai e viu in afara sesiunii.
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        print(f"[olx_re] error: {exc}")
        log_manager.emit("real_estate", "ERR", f"OLX Imobiliare eroare: {str(exc)[:80]}")
        return []

    cards = soup.select('div[data-cy="l-card"]') or soup.select('[data-testid="l-card"]')
    # OLX-IMO-1 — id-ul numeric al fiecarui card (`<div id="305646457">`), paralel cu
    # `results`: e puntea catre meta pentru anunturile incrucisate (vezi mai jos).
    card_ids: list = []
    for card in cards:
        try:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = _BASE + href
            card_id = str(card.get("id") or "").strip()

            title_el = card.find("h4") or card.find("h6") or link
            titlu = title_el.get_text(strip=True) if title_el else ""
            if not titlu:
                continue

            price_el = card.find(attrs={"data-testid": "ad-price"}) or card.find("p")
            price_raw = price_el.get_text(" ", strip=True) if price_el else ""
            pret = parse_price(price_raw)
            moneda = detect_currency(price_raw)

            loc_el = card.find(attrs={"data-testid": "location-date"})
            locatie = None
            listed_at = None
            refreshed_at = None
            if loc_el:
                raw = loc_el.get_text(" ", strip=True)
                # Separatorul e " - "; split cu maxsplit=1 ca locatiile cu cratima interna
                # ("Cluj-Napoca") sa NU fie taiate gresit. Partea 0 = locatia, restul = data.
                parts = raw.split(" - ", 1)
                locatie = parts[0].strip()
                if len(parts) > 1:
                    # DATE-2 — FALLBACK. Cardul are o singura data cu doua semantici, deci
                    # eticheta decide coloana (regula DATE-1): „Reactualizat azi" pe un anunt
                    # de patru luni nu are voie sa treaca drept data publicarii. Sursa
                    # preferata ramane state-ul (mai jos), care le da separat.
                    dt = _parse_olx_date(parts[1], datetime.now())
                    if dt and _este_reactualizare(parts[1]):
                        refreshed_at = dt.isoformat()
                    elif dt:
                        listed_at = dt.isoformat()

            thumb = _pick_thumb(card.find("img"))

            results.append(make_re_listing(
                platform="olx", external_id=_external_id_card(href),
                tip_anunt=tip_anunt, tip_proprietate=tip_proprietate,
                camere=extract_rooms(titlu), suprafata_mp=extract_surface(titlu),
                pret=pret, moneda=moneda, locatie_oras=locatie,
                titlu=titlu, source_url=href, thumbnail_url=thumb,
                listed_at=listed_at, refreshed_at=refreshed_at,
            ))
            card_ids.append(card_id)
            if len(results) >= MAX_RESULTS:
                break
        except Exception as exc:
            print(f"[olx_re] card parse error: {exc}")
            continue

    # DATE-2 — cele doua date, separate, din __PRERENDERED_STATE__ (aceeasi pagina, fara
    # request extra). Bat data de pe card: acolo `createdTime` si `lastRefreshTime` sunt
    # comprimate intr-un singur text. Exemplu masurat pe fixture: primul anunt e publicat
    # pe 19.06 si repromovat pe 03.09 — cardul arata doar a doua data.
    # Conventia Imobiliare: STRING ISO (scannerul face fromisoformat), cu `Z` normalizat.
    meta = extract_olx_ad_meta(html)
    # OLX-IMO-1 — legarea meta pe DOUA cai, in ordinea asta:
    #   1. tokenul din URL, cheia lui `extract_olx_ad_meta` — calea existenta, neatinsa;
    #   2. id-ul numeric de pe card, pentru anunturile incrucisate.
    # A doua e necesara fiindca acelasi anunt are DOUA identificatoare: state-ul il tine
    # sub tokenul OLX (`kGsBz`, din `url`-ul canonic olx.ro), iar cardul trimite la
    # tokenul Storia (`HE6J`, din `externalUrl`). Nu lipseste nimic din meta — masurat,
    # are toate cele 51 de ad-uri; doar cheia difera. `numeric_id` e prezent pe 51/51 si
    # da acelasi ad ca tokenul pe toate cele 26 unde exista amandoua, deci calea 2 e o
    # rezerva coerenta, nu o a doua sursa de adevar.
    prin_numeric = {str(m["numeric_id"]): m
                    for m in meta.values() if m.get("numeric_id") is not None}
    metas = [meta.get(r.get("external_id") or "") or prin_numeric.get(cid) or {}
             for r, cid in zip(results, card_ids)]
    for r, m in zip(results, metas):
        if not m:
            continue
        creat = normalize_iso(m.get("created"))
        reactualizat = normalize_iso(m.get("refreshed"))
        if creat:
            r["listed_at"] = creat
        if reactualizat:
            r["refreshed_at"] = reactualizat

    print(f"[olx_re] {len(results)} anunturi ({tip_proprietate} {tip_anunt})")
    log_manager.emit("real_estate", "OK", f"OLX Imobiliare: {len(results)} anunturi gasite")

    # IMO-1 — enrichment doar pe anunturile NOI (necunoscute scannerului), plafonat.
    # OLX-STATE-1: id-ul numeric vine din `meta`, calculat mai sus — `_extract_numeric_ids`
    # era a doua parsare a aceluiasi state (~470 ms per pagina).
    skip = skip_enrich_ids or set()
    enriched = 0
    for r, m in zip(results, metas):
        if enriched >= _ENRICH_CAP:
            break
        ext = r.get("external_id")
        nid = m.get("numeric_id")
        if not ext or ext in skip or not nid:
            continue
        det = _fetch_offer_details(nid)
        if not det:
            continue
        enriched += 1
        for k, v in det.items():
            if k == "images":
                # pozele API-ului au prioritate; thumbnail-ul din card ramane fallback
                r["images"] = v or ([r.get("thumbnail_url")] if r.get("thumbnail_url") else [])
            elif v is not None and not r.get(k):
                r[k] = v
        time.sleep(random.uniform(*_ENRICH_DELAY_RANGE))
    if enriched:
        log_manager.emit("real_estate", "OK", f"OLX Imobiliare: {enriched} anunțuri îmbogățite (detaliu)")

    return results[:MAX_RESULTS]
