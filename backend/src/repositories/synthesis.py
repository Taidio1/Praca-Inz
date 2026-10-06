from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import AsyncClient

from src.repositories.llm_costs import llm_cost_since
from src.repositories.snapshots import SnapshotsRepository

Row = dict[str, Any]
_LOCK_KEY = "lock:synthesis"
_ITEM = "source_items!inner(id, title, snippet, published_at, fetched_at, raw, duplicate_of)"


class SynthesisRepository:
    """Odczyt kandydatów i zapis syntez: wymaga klienta service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def candidates(
        self,
        asset_id: str,
        *,
        threshold: float,
        since: datetime,
        fetched_after: datetime,
        limit: int,
    ) -> list[Row]:
        res = await (
            self._client.table("item_relevance")
            .select(f"item_id, score, created_at, {_ITEM}")
            .eq("asset_id", asset_id)
            .gte("score", threshold)
            # created_at pary = pierwsza ocena (upsert go nie zmienia)
            .gt("created_at", since.isoformat())
            .gt("source_items.fetched_at", fetched_after.isoformat())
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
        # Nieudane syntezy dziś (po ostatnim insighcie aktywa) do wycofania wykładniczego
        fails = await (
            self._client.table("llm_runs")
            .select("asset_id, created_at")
            .eq("purpose", "synthesis")
            .in_("status", ["invalid", "error"])
            .in_("asset_id", asset_ids)
            .gte("created_at", day_start.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
        for r in fails.data:
            created = datetime.fromisoformat(r["created_at"])
            entry = out.setdefault(r["asset_id"], {
                "last_insight_at": None, "last_summary": None, "insights_today": 0,
            })
            last_ok = entry.get("last_insight_at")
            if last_ok is not None and created <= last_ok:
                continue  # porażka przed udaną syntezą (np. naprawiona odpowiedź)
            entry.setdefault("last_failure_at", created)
            entry["failures_today"] = int(entry.get("failures_today", 0)) + 1
        return out

    async def cost_since(self, since: datetime) -> float:
        return await llm_cost_since(self._client, since)

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

    async def delete_insight(self, insight_id: str) -> None:
        await self._client.table("insights").delete().eq("id", insight_id).execute()

    async def acquire_lock(self, owner: str, ttl: timedelta) -> bool:
        """Dzierżawa w source_state (bez migracji): warunkowy UPDATE jest atomowy w Postgresie."""
        await (
            self._client.table("source_state")
            .upsert({"source_key": _LOCK_KEY}, on_conflict="source_key", ignore_duplicates=True)
            .execute()
        )
        now = datetime.now(UTC)
        expired = (now - ttl).isoformat()
        res = await (
            self._client.table("source_state")
            .update({"last_fetched_at": now.isoformat(), "etag": owner,
                     "updated_at": now.isoformat()})
            .eq("source_key", _LOCK_KEY)
            .or_(f'last_fetched_at.is.null,last_fetched_at.lt."{expired}"')
            .execute()
        )
        return len(res.data) == 1

    async def release_lock(self, owner: str) -> None:
        await (
            self._client.table("source_state")
            .update({"last_fetched_at": None, "etag": None})
            .eq("source_key", _LOCK_KEY)
            .eq("etag", owner)
            .execute()
        )
