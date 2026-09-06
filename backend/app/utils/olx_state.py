"""Parserul UNIC pentru `window.__PRERENDERED_STATE__` de pe listarile OLX.

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

OLX-STATE-1 — o SINGURA parsare per pagina. Pana acum fiecare modul parsa state-ul de
DOUA ori: o data prin `extract_olx_ad_meta` (categorie + date) si inca o data printr-o
copie locala a aceluiasi regex + dublu-decode — `_extract_olx_numeric_ids` la Radar,
`_extract_numeric_ids` la Imobiliare, `_photos_map_from_state` la Auto. Cele trei copii
au disparut; tot ce citeau vine acum din acelasi dict, dintr-o singura trecere prin
`ads[]`. Masurat: o parsare costa ~470 ms pe pagina de 3,3 MB.

Helperii de data (`iso_to_naive_local`, `normalize_iso`) au plecat in
`utils/listing_dates.py`: ii foloseau si Autovit, Storia si AutoScout24, module fara
nicio legatura cu OLX. NU exista re-export de compatibilitate — importurile s-au
corectat la sursa, deliberat, ca un import vechi sa pice zgomotos, nu tacut.
"""
import json
import re
from typing import Optional

# Grupul prinde literalul JSON cu ghilimele, inclusiv escape-urile din interior.
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
    """{token_din_url: {"category_id", "created", "refreshed", "numeric_id", "photos"}}.

    Cheile OLX citite, cu semantica lor:
      * `category.id`     -> `category_id` (str sau None) — filtrarea pe subcategorie;
      * `createdTime`     -> `created`   — PRIMA publicare (`listed_at`);
      * `lastRefreshTime` -> `refreshed` — ultima repromovare (`refreshed_at`);
      * `id`              -> `numeric_id` — id-ul cerut de `/api/v1/offers/{id}`, in
        forma BRUTA din JSON (int pe fixture), sau None cand ad-ul n-are `id`;
      * `photos`          -> `photos` — lista de URL-uri, in ordinea din state, BRUTE.

    Valorile de data raman STRINGURI ISO netransformate; fiecare modul isi aplica
    propria conventie de fus orar (naiv local la Radar/Auto, string ISO la Imobiliare).

    Doua alegeri de forma canonica, fiindca cele trei functii vechi nu erau simetrice:
      * `numeric_id` e prezent MEREU ca cheie, cu valoarea None cand lipseste. Vechile
        `_extract_olx_numeric_ids` / `_extract_numeric_ids` omiteau intrarea cu totul;
        ambii apelanti verificau oricum `is not None` / falsy inainte s-o foloseasca,
        deci diferenta nu se vede la call site.
      * `photos` sunt BRUTE si TOATE, nu doar prima normalizata la `;s=1000x1000`.
        Ridicarea thumbnail-ului e o decizie de AFISARE a lui `olx_auto`, nu o
        proprietate a state-ului: ramane acolo, in `_olx_upgrade_thumb`, aplicata pe
        `photos[0]`. Intrarile care nu sunt string se filtreaza.

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
            photos = ad.get("photos")
            rezultat[mm.group(1)] = {
                "category_id": str(cat_id) if cat_id is not None else None,
                "created": ad.get("createdTime") or None,
                "refreshed": ad.get("lastRefreshTime") or None,
                "numeric_id": ad.get("id"),
                "photos": ([p for p in photos if isinstance(p, str)]
                           if isinstance(photos, list) else []),
            }
        return rezultat
    except Exception:
        return {}
