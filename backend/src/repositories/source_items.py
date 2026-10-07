from datetime import datetime
from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]


class SourceItemsRepository:
    """Odczyt audytu przez funkcje SQL (security invoker: działa RLS użytkownika)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def page(
        self,
        *,
        asset_ids: list[str],
        threshold: float,
        status: str,
        before: tuple[datetime, str] | None,
        limit: int,
        asset_filter: str | None,
    ) -> list[Row]:
        res = await self._client.rpc(
            "sources_page",
            {
                "p_asset_ids": asset_ids,
                "p_threshold": threshold,
                "p_status": status,
                "p_before_ts": before[0].isoformat() if before else None,
                "p_before_id": before[1] if before else None,
                "p_limit": limit,
                "p_asset_filter": asset_filter,
            },
        ).execute()
        return list(res.data)

    async def outlets(self, item_ids: list[str]) -> dict[str, str]:
        if not item_ids:
            return {}
        res = await (
            self._client.table("source_items")
            .select("id, publisher:raw->>publisher, domain:raw->>domain")
            .in_("id", item_ids)
            .execute()
        )
        out: dict[str, str] = {}
        for r in res.data:
            name = r.get("publisher") or r.get("domain")
            if name:
                out[str(r["id"])] = str(name)
        return out

    async def funnel(self, *, since: datetime, asset_ids: list[str], threshold: float) -> Row:
        res = await self._client.rpc(
            "sources_funnel",
            {"p_since": since.isoformat(), "p_asset_ids": asset_ids, "p_threshold": threshold},
        ).execute()
        return dict(res.data)

    async def evaluation_labels(self, asset_ids: list[str]) -> list[Row]:
        if not asset_ids:
            return []
        labels = await (
            self._client.table("relevance_labels")
            .select("item_id, asset_id, relevant")
            .in_("asset_id", asset_ids)
            .execute()
        )
        if not labels.data:
            return []
        scores = await (
            self._client.table("item_relevance")
            .select("item_id, asset_id, score")
            .in_("asset_id", asset_ids)
            .execute()
        )
        by_pair = {(str(row["item_id"]), str(row["asset_id"])): row["score"] for row in scores.data}
        return [
            {
                **row,
                "score": by_pair.get((str(row["item_id"]), str(row["asset_id"]))),
            }
            for row in labels.data
        ]

    async def save_label(self, user_id: str, item_id: str, asset_id: str, relevant: bool) -> None:
        await (
            self._client.table("relevance_labels")
            .upsert(
                {
                    "user_id": user_id,
                    "item_id": item_id,
                    "asset_id": asset_id,
                    "relevant": relevant,
                },
                on_conflict="user_id,item_id,asset_id",
            )
            .execute()
        )
