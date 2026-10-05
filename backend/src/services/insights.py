from typing import Any, Protocol

from src.core.errors import NotFoundError
from src.schemas.insights import TraceOut

Row = dict[str, Any]


class InsightsRepo(Protocol):
    async def get(self, insight_id: str) -> Row | None: ...
    async def get_run(self, llm_run_id: str) -> Row | None: ...


class InsightService:
    def __init__(self, insights: InsightsRepo) -> None:
        self._insights = insights

    async def get_trace(self, insight_id: str) -> TraceOut:
        insight = await self._insights.get(insight_id)
        if insight is None:
            raise NotFoundError("Insight nie istnieje")
        run = await self._insights.get_run(insight["llm_run_id"])
        if run is None:
            raise NotFoundError("Brak zapisu audytu LLM dla tego insightu")
        return TraceOut(
            provider=run["provider"],
            model=run["model"],
            prompt=run["prompt"],
            response=run["response"],
            tokens_in=run["tokens_in"],
            tokens_out=run["tokens_out"],
            latency_ms=run["latency_ms"],
            cost_usd=run["cost_usd"],
            created_at=run["created_at"],
        )
