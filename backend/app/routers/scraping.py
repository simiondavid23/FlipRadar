import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.user import User
from app.utils.auth import require_feature
from app.services import search_service
from app.services.scraper_service import (
    scrape_altex, scrape_sole, scrape_farmaciatei, scrape_emag, scrape_pcgarage,
    filter_by_relevance, filter_by_code,
)

router = APIRouter(prefix="/api/scraping", tags=["Web Scraping"])


def _apply_filter(items: list, query: str, search_type: Optional[str]) -> list:
    if search_type == "ean":
        return filter_by_code(items, query, "ean")
    if search_type == "sku":
        return filter_by_code(items, query, "sku")
    return filter_by_relevance(items, query)

# Toată suprafața de scraping stă în spatele flag-ului `can_use_scraping` — este
# cel mai intens workload de ieșire și cel mai predispus la abuz, deci adminii au un
# singur comutator pentru a-l dezactiva per utilizator.
_scraping_user = require_feature("can_use_scraping")

# --- Ajustare limite rezultate -----------------------------------------------
# Inițial, router-ul limita fiecare sursă la 30 de produse și căutarea agregată
# la 20/site. Utilizatorii au raportat că ratează rezultate relevante — de ex.,
# o căutare pentru "rtx 5070" returna doar 15 produse fiindcă search-all limita
# fiecare sursă la un număr mic. Stratul de scraper paginează acum pe mai multe
# pagini HTML, deci ridicăm limitele să reflecte dimensiunile reale ale cataloagelor
# (eMAG ~78/pagină, PCGarage ~20/pagină, Farmacia Tei ~60/pagină, Altex până la 100
# într-un singur apel API). Valorile implicite sunt generoase pentru ca UI-ul să
# afișeze „toate produsele potrivite" fără ca utilizatorul să modifice parametrii.
_PER_SITE_DEFAULT = 100
_PER_SITE_MAX = 300
_ALL_DEFAULT = 50
_ALL_MAX = 100


@router.get("/altex")
async def search_altex(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse pe Altex.ro"""
    results = _apply_filter(await scrape_altex(q, max_results), q, search_type)
    return {"source": "altex.ro", "query": q, "results": results, "count": len(results)}


@router.get("/sole")
async def search_sole(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse pe Sole.ro"""
    results = _apply_filter(await scrape_sole(q, max_results), q, search_type)
    return {"source": "sole.ro", "query": q, "results": results, "count": len(results)}


@router.get("/farmaciatei")
async def search_farmaciatei(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse pe comenzi.farmaciatei.ro"""
    results = _apply_filter(await scrape_farmaciatei(q, max_results), q, search_type)
    return {"source": "farmaciatei.ro", "query": q, "results": results, "count": len(results)}


@router.get("/emag")
async def search_emag(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse pe eMAG.ro"""
    results = _apply_filter(await scrape_emag(q, max_results), q, search_type)
    return {"source": "emag.ro", "query": q, "results": results, "count": len(results)}


@router.get("/pcgarage")
async def search_pcgarage(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse pe PCGarage.ro"""
    results = _apply_filter(await scrape_pcgarage(q, max_results), q, search_type)
    return {"source": "pcgarage.ro", "query": q, "results": results, "count": len(results)}


@router.get("/search-all")
async def search_all_sources(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_ALL_DEFAULT, ge=1, le=_ALL_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Caută produse în paralel pe toate sursele."""
    altex_results, sole_results, farmaciatei_results, emag_results, pcgarage_results = await asyncio.gather(
        scrape_altex(q, max_results),
        scrape_sole(q, max_results),
        scrape_farmaciatei(q, max_results),
        scrape_emag(q, max_results),
        scrape_pcgarage(q, max_results),
    )

    altex_results = _apply_filter(altex_results, q, search_type)
    sole_results = _apply_filter(sole_results, q, search_type)
    farmaciatei_results = _apply_filter(farmaciatei_results, q, search_type)
    emag_results = _apply_filter(emag_results, q, search_type)
    pcgarage_results = _apply_filter(pcgarage_results, q, search_type)

    return {
        "query": q,
        "sources": {
            "altex": {"results": altex_results, "count": len(altex_results)},
            "sole": {"results": sole_results, "count": len(sole_results)},
            "farmaciatei": {"results": farmaciatei_results, "count": len(farmaciatei_results)},
            "emag": {"results": emag_results, "count": len(emag_results)},
            "pcgarage": {"results": pcgarage_results, "count": len(pcgarage_results)},
        },
        "total_results": (
            len(altex_results) + len(sole_results)
            + len(farmaciatei_results) + len(emag_results)
            + len(pcgarage_results)
        ),
    }


# ── SEARCH-1b — rutele generice, peste registru ───────────────────────────────
# Rutele de mai sus (/altex … /search-all) raman NEATINSE ca alias: frontend-ul
# curent le foloseste si continua sa mearga pana la SEARCH-2, care il rescrie peste
# cele doua de aici.
#
# FARA `@limiter.limit`, deliberat si simetric cu rutele istorice (care n-au nici
# ele): pagina de cautare lanseaza cate o cerere per magazin selectat, in paralel.
# Un `5/minute` ar taia jumatate din rezultatele unei singure cautari cu 6 magazine
# bifate — adica ar rupe exact fluxul normal, nu abuzul. Suprafata ramane in spatele
# flagului `can_use_scraping`, care e comutatorul real per utilizator.


@router.get("/sources")
async def list_search_sources(
    current_user: User = Depends(_scraping_user),
):
    """Magazinele din registru, pentru selectorul din „Scanare Magazine".

    Le intoarce pe TOATE, inclusiv cele necautabile — acelea vin cu `searchable:
    false` si cu motivul in `reason`, ca UI-ul sa le poata arata dezactivate cu
    tooltip in loc sa le ascunda.
    """
    return {"sources": search_service.sources()}


@router.get("/search")
async def search_one_source(
    domain: str = Query(..., description="Domeniul din registru"),
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Cauta un termen pe UN magazin, prin mecanismul lui din registru."""
    try:
        rezultat = await asyncio.to_thread(
            search_service.search, domain, q, max_results)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Magazin necunoscut: {domain}")

    # Filtrul de relevanta se aplica DOAR pe calea `custom`, si asta e o decizie
    # masurata, nu o scapare.
    #
    # El exista ca sa taie fallback-ul FUZZY al scraperelor scrise de mana — eMAG
    # intoarce ~50 de produse fara legatura cand termenul exact n-are potriviri. Pe
    # mecanismele generice problema nu exista: motorul magazinului a potrivit deja
    # termenul, iar titlurile pot sa nu contina brandul cautat. Masurat la SEARCH-0:
    # bergfreunde raspunde la „salomon" cu titluri de forma „Xa Pro V8 Winter CSWP
    # Junior Winter boots" — filtrul ar fi taiat 72 din 72 de rezultate corecte.
    #
    # Pe generic, `search_type` ean/sku trimite codul ca termen de cautare si NU
    # filtreaza: campurile `ean`/`sku` sunt None acolo, deci `filter_by_code` ar
    # elimina tot.
    if rezultat.get("kind") == "custom" and rezultat.get("status") == "ok":
        filtrate = _apply_filter(rezultat["results"], q, search_type)
        # `filter_by_relevance` reintroduce o sentinela `message` cand nu ramane
        # niciun produs relevant. Nu are voie sa iasa din API sub forma de produs,
        # deci se traduce inapoi in status — la fel ca sentinelele din serviciu.
        reale = [p for p in filtrate
                 if isinstance(p, dict) and not p.get("message") and not p.get("error")]
        rezultat = {**rezultat, "results": reale, "count": len(reale)}
        if not reale:
            rezultat["status"] = "empty"
            rezultat["truncated"] = False

    return rezultat
