from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.api.deps import CurrentUser, get_current_user, get_sources_service
from src.schemas.sources import EvaluationMetricsOut, FunnelOut, RelevanceLabelIn, SourcePage
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


@router.get("/evaluation")
async def sources_evaluation(
    service: Annotated[SourcesService, Depends(get_sources_service)],
) -> EvaluationMetricsOut:
    return await service.evaluation()


@router.put("/{item_id}/labels/{asset_id}", status_code=204)
async def label_source_item(
    item_id: UUID,
    asset_id: UUID,
    payload: RelevanceLabelIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SourcesService, Depends(get_sources_service)],
) -> None:
    await service.label(user.id, str(item_id), str(asset_id), relevant=payload.relevant)
