import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query
from app.models.user import User
from app.utils.auth import require_feature
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
