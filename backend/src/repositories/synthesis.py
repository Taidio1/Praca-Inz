from datetime import datetime
from typing import Any

from supabase import AsyncClient

from src.repositories.snapshots import SnapshotsRepository

Row = dict[str, Any]
_ITEM = "source_items!inner(id, title, snippet, published_at, fetched_at, raw, duplicate_of)"


class SynthesisRepository:
    """Odczyt kandydatów i zapis syntez: wymaga klienta service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def candidates(
        self, asset_id: str, *, threshold: float, since: datetime, limit: int
    ) -> list[Row]:
        res = await (
            self._client.table("item_relevance")
            .select(f"item_id, score, {_ITEM}")
            .eq("asset_id", asset_id)
            .gte("score", threshold)
            .gt("source_items.fetched_at", since.isoformat())
            .is_("source_items.duplicate_of", "null")
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[Row] = []
        for r in res.data:
            item = r["source_items"]
            raw = item.get("raw") or {}
            out.append({
                "item_id": r["item_id"], "score": float(r["score"]), "title": item["title"],
                "snippet": item.get("snippet"),
                "outlet": raw.get("publisher") or raw.get("domain"),
                "published_at": item.get("published_at"), "fetched_at": item["fetched_at"],
            })
        return out

    async def activity(self, asset_ids: list[str], day_start: datetime) -> dict[str, Row]:
        if not asset_ids:
            return {}
        res = await (
            self._client.table("insights")
            .select("asset_id, summary, created_at")
            .in_("asset_id", asset_ids)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        out: dict[str, Row] = {}
        for r in res.data:
            entry = out.setdefault(r["asset_id"], {
                "last_insight_at": datetime.fromisoformat(r["created_at"]),
                "last_summary": r["summary"], "insights_today": 0,
            })
            if datetime.fromisoformat(r["created_at"]) >= day_start:
                entry["insights_today"] += 1
        return out

    async def cost_since(self, since: datetime) -> float:
        res = await (
            self._client.table("llm_runs")
            .select("cost_usd")
            .gte("created_at", since.isoformat())
            .limit(10000)
            .execute()
        )
        return sum(float(r["cost_usd"] or 0) for r in res.data)

    async def profiles(self, asset_ids: list[str]) -> dict[str, Row]:
        if not asset_ids:
            return {}
        res = await (
            self._client.table("asset_profiles")
            .select("asset_id, profile_text, market")
            .in_("asset_id", asset_ids)
            .execute()
        )
        return {r["asset_id"]: r for r in res.data}

    async def snapshots(self, asset_ids: list[str]) -> dict[str, Row]:
        return await SnapshotsRepository(self._client).latest_for_assets(asset_ids)

    async def insert_run(self, row: Row) -> str:
        res = await self._client.table("llm_runs").insert(row).execute()
        return str(res.data[0]["id"])

    async def insert_insight(self, row: Row) -> str:
        res = await self._client.table("insights").insert(row).execute()
        return str(res.data[0]["id"])

    async def insert_insight_items(self, rows: list[Row]) -> None:
        if rows:
            await self._client.table("insight_items").insert(rows).execute()
