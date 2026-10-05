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
