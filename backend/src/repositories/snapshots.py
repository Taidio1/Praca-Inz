from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]

_SCAN_LIMIT = 200  # najnowsze wiersze; deduplikacja per aktywo po stronie Pythona


class SnapshotsRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def latest_for_assets(self, asset_ids: list[str]) -> dict[str, Row]:
        if not asset_ids:
            return {}
        res = await (
            self._client.table("market_snapshots")
            .select("*")
            .in_("asset_id", asset_ids)
            .order("captured_at", desc=True)
            .limit(_SCAN_LIMIT)
            .execute()
        )
        latest: dict[str, Row] = {}
        for row in res.data:
            latest.setdefault(row["asset_id"], row)
        return latest

    async def history_for_asset(self, asset_id: str, limit: int = 100) -> list[Row]:
        res = await (
            self._client.table("market_snapshots")
            .select("*")
            .eq("asset_id", asset_id)
            .order("captured_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
