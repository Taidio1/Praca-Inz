from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_feed_service
from src.schemas.feed import FeedPage
from src.services.feed import FeedService

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("")
async def get_feed(
    service: Annotated[FeedService, Depends(get_feed_service)],
    asset_id: UUID | None = None,
    sentiment: Literal["pos", "neg"] | None = None,
    cursor: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FeedPage:
    return await service.get_feed(
        asset_id=asset_id, sentiment=sentiment, cursor=cursor, limit=limit
    )
