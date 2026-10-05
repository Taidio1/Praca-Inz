from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]

_SELECT = "score, method, reason, source_items(id, title, source, url, published_at)"


class SourcesRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_for_asset(
        self, asset_id: str, *, min_score: float | None, limit: int
    ) -> list[Row]:
        query = (
            self._client.table("item_relevance")
            .select(_SELECT)
            .eq("asset_id", asset_id)
            .order("score", desc=True)
            .limit(limit)
        )
        if min_score is not None:
            query = query.gte("score", min_score)
        res = await query.execute()
        return list(res.data)
