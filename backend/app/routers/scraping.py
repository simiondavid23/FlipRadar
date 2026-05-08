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

# Whole scraping surface sits behind the `can_use_scraping` flag — it's the
# heaviest outbound workload and the most abuse-prone, so admins get a single
# toggle to shut it off per user.
_scraping_user = require_feature("can_use_scraping")

# --- Result-cap tuning -------------------------------------------------------
# Earlier this router limited each source to 30 products and the aggregate
# search to 20/site. Users reported missing relevant matches — e.g. a search
# for "rtx 5070" returned only 15 products because search-all capped each
# source at a tiny number. The scraper layer now paginates across multiple
# HTML pages, so we raise the caps to reflect real catalog sizes (eMAG
# ~78/page, PCGarage ~20/page, Farmacia Tei ~60/page, Altex up to 100 in one
# API call). Defaults are generous so the UI shows "all matching products"
# without the user having to tweak query params.
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
    """Search products on Altex.ro"""
    results = _apply_filter(await scrape_altex(q, max_results), q, search_type)
    return {"source": "altex.ro", "query": q, "results": results, "count": len(results)}


@router.get("/sole")
async def search_sole(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Search products on Sole.ro"""
    results = _apply_filter(await scrape_sole(q, max_results), q, search_type)
    return {"source": "sole.ro", "query": q, "results": results, "count": len(results)}


@router.get("/farmaciatei")
async def search_farmaciatei(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Search products on comenzi.farmaciatei.ro"""
    results = _apply_filter(await scrape_farmaciatei(q, max_results), q, search_type)
    return {"source": "farmaciatei.ro", "query": q, "results": results, "count": len(results)}


@router.get("/emag")
async def search_emag(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Search products on eMAG.ro"""
    results = _apply_filter(await scrape_emag(q, max_results), q, search_type)
    return {"source": "emag.ro", "query": q, "results": results, "count": len(results)}


@router.get("/pcgarage")
async def search_pcgarage(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_PER_SITE_DEFAULT, ge=1, le=_PER_SITE_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Search products on PCGarage.ro"""
    results = _apply_filter(await scrape_pcgarage(q, max_results), q, search_type)
    return {"source": "pcgarage.ro", "query": q, "results": results, "count": len(results)}


@router.get("/search-all")
async def search_all_sources(
    q: str = Query(..., description="Search query"),
    max_results: int = Query(_ALL_DEFAULT, ge=1, le=_ALL_MAX),
    search_type: Optional[str] = Query(None, description="name | ean | sku"),
    current_user: User = Depends(_scraping_user),
):
    """Search products across all sources in parallel."""
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
