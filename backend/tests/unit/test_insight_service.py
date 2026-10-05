from datetime import UTC, datetime

import pytest

from src.core.errors import NotFoundError
from src.services.insights import InsightService

INSIGHT_ID = "bbbbbbbb-0000-0000-0000-000000000001"
RUN_ID = "dddddddd-0000-0000-0000-000000000001"


class FakeInsightsRepo:
    def __init__(self, insight: dict | None, run: dict | None) -> None:  # type: ignore[type-arg]
        self._insight = insight
        self._run = run

    async def get(self, insight_id: str) -> dict | None:  # type: ignore[type-arg]
        return self._insight

    async def get_run(self, llm_run_id: str) -> dict | None:  # type: ignore[type-arg]
        return self._run


RUN_ROW = {
    "id": RUN_ID,
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "prompt": "P",
    "response": "R",
    "tokens_in": 1200,
    "tokens_out": 300,
    "latency_ms": 2100,
    "cost_usd": 0.012,
    "created_at": datetime(2026, 7, 3, tzinfo=UTC),
}


async def test_trace_returns_llm_run_fields() -> None:
    svc = InsightService(FakeInsightsRepo({"llm_run_id": RUN_ID}, RUN_ROW))
    trace = await svc.get_trace(INSIGHT_ID)
    assert trace.model == "claude-sonnet-5"
    assert trace.tokens_in == 1200


async def test_trace_missing_insight_raises_not_found() -> None:
    svc = InsightService(FakeInsightsRepo(None, RUN_ROW))
    with pytest.raises(NotFoundError):
        await svc.get_trace(INSIGHT_ID)


async def test_trace_missing_run_raises_not_found() -> None:
    svc = InsightService(FakeInsightsRepo({"llm_run_id": RUN_ID}, None))
    with pytest.raises(NotFoundError):
        await svc.get_trace(INSIGHT_ID)
