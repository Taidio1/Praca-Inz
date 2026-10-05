from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from src.api.deps import get_insight_service
from src.schemas.insights import TraceOut
from src.services.insights import InsightService

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/{insight_id}/trace")
async def get_trace(
    insight_id: UUID,
    service: Annotated[InsightService, Depends(get_insight_service)],
) -> TraceOut:
    return await service.get_trace(str(insight_id))
