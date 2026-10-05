from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_sources_service
from src.schemas.sources import FunnelOut, SourcePage
from src.services.sources import SourcesService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources(
    service: Annotated[SourcesService, Depends(get_sources_service)],
    status: Literal["all", "passed", "rejected", "unmatched"] = "all",
    asset_id: UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> SourcePage:
    return await service.list_items(
        status=status, asset_id=str(asset_id) if asset_id else None, cursor=cursor, limit=limit
    )


@router.get("/funnel")
async def sources_funnel(
    service: Annotated[SourcesService, Depends(get_sources_service)],
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> FunnelOut:
    return await service.funnel(hours=hours)
