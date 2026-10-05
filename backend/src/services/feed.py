from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from src.schemas.feed import FeedPage
from src.services.mappers import insight_from_row

Row = dict[str, Any]
Sentiment = Literal["pos", "neg"]


class PortfolioRepo(Protocol):
    async def list_positions(self) -> list[Row]: ...


class InsightsRepo(Protocol):
    async def list_for_assets(
        self,
        asset_ids: list[str],
        *,
        before: datetime | None,
        sentiment: str | None,
        limit: int,
    ) -> list[Row]: ...


class FeedService:
    def __init__(self, portfolio: PortfolioRepo, insights: InsightsRepo) -> None:
        self._portfolio = portfolio
        self._insights = insights

    async def get_feed(
        self,
        *,
        asset_id: UUID | None,
        sentiment: Sentiment | None,
        cursor: datetime | None,
        limit: int,
    ) -> FeedPage:
        positions = await self._portfolio.list_positions()
        asset_ids = [row["assets"]["id"] for row in positions]
        if asset_id is not None:
            asset_ids = [aid for aid in asset_ids if aid == str(asset_id)]
        if not asset_ids:
            return FeedPage(items=[], next_cursor=None)

        rows = await self._insights.list_for_assets(
            asset_ids, before=cursor, sentiment=sentiment, limit=limit
        )
        items = [insight_from_row(row) for row in rows]
        next_cursor = items[-1].created_at if len(items) == limit else None
        return FeedPage(items=items, next_cursor=next_cursor)
