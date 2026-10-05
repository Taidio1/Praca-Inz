from datetime import datetime
from typing import Any, Protocol

from src.core.errors import NotFoundError
from src.schemas.assets import AssetDetailOut, SnapshotOut
from src.schemas.sources import SourceItemOut
from src.services.mappers import asset_from_row, insight_from_row, snapshot_from_row

Row = dict[str, Any]


class AssetsRepo(Protocol):
    async def get(self, asset_id: str) -> Row | None: ...


class SnapshotsRepo(Protocol):
    async def latest_for_assets(self, asset_ids: list[str]) -> dict[str, Row]: ...


class InsightsRepo(Protocol):
    async def list_for_assets(
        self,
        asset_ids: list[str],
        *,
        before: datetime | None,
        sentiment: str | None,
        limit: int,
    ) -> list[Row]: ...


class SourcesRepo(Protocol):
    async def list_for_asset(
        self, asset_id: str, *, min_score: float | None, limit: int
    ) -> list[Row]: ...


class AssetService:
    LATEST_INSIGHTS_LIMIT = 5

    def __init__(
        self,
        assets: AssetsRepo,
        snapshots: SnapshotsRepo,
        insights: InsightsRepo,
        sources: SourcesRepo,
    ) -> None:
        self._assets = assets
        self._snapshots = snapshots
        self._insights = insights
        self._sources = sources

    async def get_detail(self, asset_id: str) -> AssetDetailOut:
        asset = await self._assets.get(asset_id)
        if asset is None:
            raise NotFoundError("Aktywo nie istnieje")
        snaps = await self._snapshots.latest_for_assets([asset_id])
        insight_rows = await self._insights.list_for_assets(
            [asset_id], before=None, sentiment=None, limit=self.LATEST_INSIGHTS_LIMIT
        )
        return AssetDetailOut(
            asset=asset_from_row(asset),
            snapshot=snapshot_from_row(snaps.get(asset_id)),
            latest_insights=[insight_from_row(row) for row in insight_rows],
        )

    async def list_sources(
        self, asset_id: str, *, min_score: float | None, limit: int
    ) -> list[SourceItemOut]:
        rows = await self._sources.list_for_asset(
            asset_id, min_score=min_score, limit=limit
        )
        return [
            SourceItemOut(
                item_id=row["source_items"]["id"],
                title=row["source_items"]["title"],
                source=row["source_items"]["source"],
                url=row["source_items"]["url"],
                published_at=row["source_items"].get("published_at"),
                score=row["score"],
                method=row["method"],
                reason=row.get("reason"),
            )
            for row in rows
        ]

    async def list_snapshots(self, asset_id: str, limit: int = 100) -> list[SnapshotOut]:
        asset = await self._assets.get(asset_id)
        if asset is None:
            raise NotFoundError("Aktywo nie istnieje")
        if hasattr(self._snapshots, "history_for_asset"):
            rows = await self._snapshots.history_for_asset(asset_id, limit=limit)
            return [snap for row in rows if (snap := snapshot_from_row(row)) is not None]
        return []
