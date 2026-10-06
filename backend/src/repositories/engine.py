from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from src.repositories.llm_costs import llm_cost_since

Row = dict[str, Any]


class EngineRepository:
    """Cykle silnika i stan źródeł. Zapis wymaga service_role; odczyt działa z RLS."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def start_cycle(self) -> str:
        res = await self._client.table("engine_cycles").insert({}).execute()
        return str(res.data[0]["id"])

    async def finish_cycle(
        self, cycle_id: str, stats: dict[str, Any], errors: dict[str, str]
    ) -> None:
        await (
            self._client.table("engine_cycles")
            .update({"finished_at": datetime.now(UTC).isoformat(), "stats": stats,
                     "errors": errors})
            .eq("id", cycle_id)
            .execute()
        )

    async def latest_cycle(self) -> Row | None:
        res = await (
            self._client.table("engine_cycles")
            .select("*")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    async def failing_states(self, limit: int = 20) -> list[Row]:
        res = await (
            self._client.table("source_state")
            .select("source_key, last_fetched_at, consecutive_failures, last_error")
            .gt("consecutive_failures", 0)
            .order("consecutive_failures", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data)

    async def cost_since(self, since: datetime) -> float:
        return await llm_cost_since(self._client, since)
