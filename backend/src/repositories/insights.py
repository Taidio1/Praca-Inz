from datetime import datetime
from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]

_SELECT = (
    "*, assets(ticker), insight_items(relevance, source_items(title, source, url))"
)
_POS_THRESHOLD = 0.2
_NEG_THRESHOLD = -0.2
_LATEST_SCAN_LIMIT = 100


class InsightsRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_for_assets(
        self,
        asset_ids: list[str],
        *,
        before: datetime | None,
        sentiment: str | None,
        limit: int,
    ) -> list[Row]:
        query = (
            self._client.table("insights")
            .select(_SELECT)
            .in_("asset_id", asset_ids)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if before is not None:
            query = query.lt("created_at", before.isoformat())
        if sentiment == "pos":
            query = query.gt("sentiment_score", _POS_THRESHOLD)
        elif sentiment == "neg":
            query = query.lt("sentiment_score", _NEG_THRESHOLD)
        res = await query.execute()
        return list(res.data)

    async def latest_per_asset(self, asset_ids: list[str]) -> dict[str, Row]:
        if not asset_ids:
            return {}
        res = await (
            self._client.table("insights")
            .select("asset_id, sentiment_score, sentiment_label, created_at")
            .in_("asset_id", asset_ids)
            .order("created_at", desc=True)
            .limit(_LATEST_SCAN_LIMIT)
            .execute()
        )
        latest: dict[str, Row] = {}
        for row in res.data:
            latest.setdefault(row["asset_id"], row)
        return latest

    async def get(self, insight_id: str) -> Row | None:
        res = await (
            self._client.table("insights")
            .select("*")
            .eq("id", insight_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    async def get_run(self, llm_run_id: str) -> Row | None:
        res = await (
            self._client.table("llm_runs")
            .select("*")
            .eq("id", llm_run_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
