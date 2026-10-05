from typing import Any

from src.engine.cycle import run_cycle, run_loop
from src.engine.ingest import IngestStats
from src.relevance.service import RelevanceStats


class FakeCycles:
    def __init__(self) -> None:
        self.finished: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def start_cycle(self) -> str:
        return "c1"

    async def finish_cycle(self, cycle_id: str, stats: dict[str, Any],
                           errors: dict[str, str]) -> None:
        self.finished.append((cycle_id, stats, errors))


class FakeStage:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def run(self) -> Any:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def test_cycle_runs_stages_and_merges_errors() -> None:
    cycles = FakeCycles()
    ingest = IngestStats(tracked_assets=2, fetched=5, inserted=4, errors={"rss:x": "HTTP 404"})
    relevance = RelevanceStats(scored=4, errors={"embedder": "brak modelu"})
    await run_cycle([("ingest", FakeStage(ingest)), ("relevance", FakeStage(relevance))], cycles)
    cid, recorded, errors = cycles.finished[0]
    assert cid == "c1"
    assert recorded == {"ingest": ingest.as_json(), "relevance": relevance.as_json()}
    assert errors == {"rss:x": "HTTP 404", "embedder": "brak modelu"}


async def test_crashed_stage_does_not_stop_next_stage() -> None:
    cycles = FakeCycles()
    relevance = RelevanceStats(scored=1)
    await run_cycle([("ingest", FakeStage(RuntimeError("db down"))),
                     ("relevance", FakeStage(relevance))], cycles)
    _, recorded, errors = cycles.finished[0]
    assert recorded == {"relevance": relevance.as_json()}
    assert errors == {"ingest": "RuntimeError: db down"}


class FlakyCycles(FakeCycles):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def start_cycle(self) -> str:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("supabase niedostępny")
        return f"c{self.calls}"


async def test_loop_survives_storage_error_and_keeps_interval() -> None:
    cycles = FlakyCycles()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    await run_loop([("ingest", FakeStage(IngestStats()))], cycles, interval=900,
                   sleep=fake_sleep, clock=lambda: 0.0, iterations=2)
    assert cycles.calls == 2
    assert [c[0] for c in cycles.finished] == ["c2"]
    assert sleeps == [900, 900]
