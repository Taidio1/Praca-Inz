from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.analysis.service import CompanyAnalysisService
from src.api.deps import get_company_analysis_service
from src.schemas.analysis import (
    CompanyOverviewOut,
    CompanySearchHitOut,
    PeerComparisonOut,
    PopularCompanyOut,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])

Ticker = Annotated[str, Path(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.\-]+$")]


@router.get("/popular")
async def popular_companies(
    service: Annotated[CompanyAnalysisService, Depends(get_company_analysis_service)],
) -> list[PopularCompanyOut]:
    return service.popular()


@router.get("/search")
async def search_companies(
    q: Annotated[str, Query(min_length=1, max_length=50)],
    service: Annotated[CompanyAnalysisService, Depends(get_company_analysis_service)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[CompanySearchHitOut]:
    """Spółki raportujące do SEC — po tickerze lub nazwie."""
    return await service.search(q, limit=limit)


@router.get("/{ticker}")
async def company_overview(
    ticker: Ticker,
    service: Annotated[CompanyAnalysisService, Depends(get_company_analysis_service)],
) -> CompanyOverviewOut:
    """Profil, notowania 5Y, wskaźniki TTM vs średnia 5Y i historia finansowa."""
    return await service.overview(ticker)


@router.get("/{ticker}/peers")
async def company_peers(
    ticker: Ticker,
    service: Annotated[CompanyAnalysisService, Depends(get_company_analysis_service)],
) -> PeerComparisonOut:
    """Wskaźniki spółek porównawczych i ich mediany (osobno — wolniejsze pobranie)."""
    return await service.peer_comparison(ticker)
