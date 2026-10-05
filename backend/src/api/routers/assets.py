from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_asset_search_service, get_asset_service
from src.marketdata.symbol_search import AssetSearchService
from src.schemas.assets import AssetDetailOut, AssetSearchResultOut, SnapshotOut
from src.schemas.sources import SourceItemOut
from src.services.assets import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/search")
async def search_assets(
    q: Annotated[str, Query(min_length=1, max_length=50)],
    service: Annotated[AssetSearchService, Depends(get_asset_search_service)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[AssetSearchResultOut]:
    matches = await service.search(q, limit=limit)
    return [
        AssetSearchResultOut(
            ticker=match.ticker,
            name=match.name,
            asset_type=match.asset_type,
        )
        for match in matches
    ]


@router.get("/{asset_id}")
async def get_asset(
    asset_id: UUID,
    service: Annotated[AssetService, Depends(get_asset_service)],
) -> AssetDetailOut:
    return await service.get_detail(str(asset_id))


@router.get("/{asset_id}/snapshots")
async def get_asset_snapshots(
    asset_id: UUID,
    service: Annotated[AssetService, Depends(get_asset_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[SnapshotOut]:
    return await service.list_snapshots(str(asset_id), limit=limit)


@router.get("/{asset_id}/sources")
async def get_asset_sources(
    asset_id: UUID,
    service: Annotated[AssetService, Depends(get_asset_service)],
    min_score: Annotated[float | None, Query(ge=0, le=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SourceItemOut]:
    return await service.list_sources(str(asset_id), min_score=min_score, limit=limit)
