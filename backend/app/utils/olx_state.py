"""DATE-2 — parserul UNIC pentru `window.__PRERENDERED_STATE__` de pe listarile OLX,
plus cei doi helperi de data ISO folositi de extractoarele de date.

De ce aici si nu intr-un scraper: aceeasi listare OLX e citita de TREI module cu
convenții de fus orar diferite — `services/radar/olx_scraper.py` (Radar, naiv local),
`scrapers/real_estate/olx_real_estate.py` (Imobiliare, string ISO) si
`scrapers/auto/listings/olx_auto.py` (Auto, naiv local). `olx_auto` refuza deliberat sa
importe din `app.services.radar.*` (decuplare de module, precedentul din `detail.py`),
deci singurul loc comun e `utils/` — tiparul REF-1. Modulul e PUR: fara retea, fara
importuri din `app.services` sau `app.scrapers`.

Structura confirmata pe fixture-urile din 2026-09-06 (`olx_listing_state.html`,
`olx_re_listing_state.html`): `__PRERENDERED_STATE__` e un STRING JSON escapat (deci
dublu-decodat), ad-urile stau in `state.listing.listing.ads[]`, iar cheia noastra e
token-ul `-ID<xxx>.html` din `url` — acelasi pe care il produc `_olx_id` din scrapere.
"""
import json
import re
from datetime import datetime
from typing import Optional

# Identic cu regex-ul din _extract_olx_categories (services/radar/olx_scraper.py):
# grupul prinde literalul JSON cu ghilimele, inclusiv escape-urile din interior.
_RX_STATE = re.compile(r'__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")', re.DOTALL)
_RX_AD_ID = re.compile(r"-ID([A-Za-z0-9]+)\.html")


def extract_olx_state(html: str) -> Optional[dict]:
    """`window.__PRERENDERED_STATE__` -> dict Python; `None` la orice esec.

    Dublu `json.loads`: primul scoate stringul din literalul JavaScript, al doilea
    parseaza continutul lui. OLX NU foloseste `__NEXT_DATA__`.
    """
    try:
        m = _RX_STATE.search(html or "")
        if not m:
            return None
        state = json.loads(json.loads(m.group(1)))
        return state if isinstance(state, dict) else None
    except Exception:
        return None


def extract_olx_ad_meta(html: str) -> dict:
    """{token_din_url: {"category_id", "created", "refreshed"}} din state-ul listarii.

    Cheile OLX citite, cu semantica lor:
      * `category.id`     -> `category_id` (string) — filtrarea pe subcategorie;
      * `createdTime`     -> `created`   — PRIMA publicare (`listed_at`);
      * `lastRefreshTime` -> `refreshed` — ultima repromovare (`refreshed_at`).
    Valorile de data raman STRINGURI ISO netransformate; fiecare modul isi aplica
    propria conventie de fus orar (naiv local la Radar/Auto, string ISO la Imobiliare).

    `pushupTime` este IGNORAT deliberat. Masurat pe cele doua fixture-uri: e prezent
    doar pe 9/52, respectiv 50/51 de ad-uri, iar acolo unde exista are exact aceeasi
    valoare ca `lastRefreshTime` (zero contradictii). `lastRefreshTime` e prezent pe
    100% din ad-uri, deci il acopera integral.

    Dict gol la orice esec (safe default: apelantul cade pe data de pe card).
    """
    state = extract_olx_state(html)
    if state is None:
        return {}
    try:
        ads = (state.get("listing") or {}).get("listing", {}).get("ads") or []
        rezultat: dict = {}
        for ad in ads:
            if not isinstance(ad, dict):
                continue
            mm = _RX_AD_ID.search(ad.get("url") or ad.get("urlPath") or "")
            if not mm:
                continue
            cat = ad.get("category")
            cat_id = cat.get("id") if isinstance(cat, dict) else None
            rezultat[mm.group(1)] = {
                "category_id": str(cat_id) if cat_id is not None else None,
                "created": ad.get("createdTime") or None,
                "refreshed": ad.get("lastRefreshTime") or None,
            }
        return rezultat
    except Exception:
        return {}


def normalize_iso(s) -> Optional[str]:
    """String ISO cu sufix `Z` -> acelasi moment scris `+00:00`; restul, neatins.

    `datetime.fromisoformat` accepta `Z` abia din Python 3.11; normalizarea aici tine
    lantul portabil pe orice versiune din proiect si face ca stringul PERSISTAT de
    Imobiliare sa fie mereu in aceeasi forma. `None`/gol -> `None`.
    """
    if not s:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    if txt[-1] in ("Z", "z"):
        txt = txt[:-1] + "+00:00"
    return txt


def iso_to_naive_local(s) -> Optional[datetime]:
    """String ISO -> datetime NAIV LOCAL (conventia Radar/Auto).

    Aceeasi semantica ca `_naiv_local` din `services/radar/facebook_scraper.py`
    (`astimezone().replace(tzinfo=None)`), dar pornind de la un STRING, nu de la un
    datetime: sursele OLX/Autovit dau text ISO. Corpul e copiat, nu importat, fiindca
    `_naiv_local` e privat intr-un modul Facebook din `services/radar/`, de unde
    `olx_auto`/`autovit` nu au voie sa importe.

    `_too_old` (RAD-1) compara `datetime.now()` naiv cu `listed_at`, deci un datetime
    aware ar arunca TypeError acolo — de aici conversia. Un input deja naiv se intoarce
    neschimbat (e local prin conventie). `None` la lipsa sau la text neparsabil.
    """
    txt = normalize_iso(s)
    if not txt:
        return None
    try:
        dt = datetime.fromisoformat(txt)
    except (TypeError, ValueError):
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt
