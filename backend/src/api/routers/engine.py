from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_sources_service
from src.schemas.sources import EngineStatusOut
from src.services.sources import SourcesService

router = APIRouter(prefix="/engine", tags=["engine"])


@router.get("/status")
async def engine_status(
    service: Annotated[SourcesService, Depends(get_sources_service)],
) -> EngineStatusOut:
    return await service.engine_status()
