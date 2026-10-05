"""Jeden cykl silnika z zapisem przebiegu do engine_cycles (audyt + status w UI)."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


class StageStats(Protocol):
    errors: dict[str, str]

    def as_json(self) -> dict[str, Any]: ...


class Stage(Protocol):
    async def run(self) -> StageStats: ...


class CyclesRepo(Protocol):
    async def start_cycle(self) -> str: ...
    async def finish_cycle(
        self, cycle_id: str, stats: dict[str, Any], errors: dict[str, str]
    ) -> None: ...


async def run_cycle(stages: Sequence[tuple[str, Stage]], cycles: CyclesRepo) -> None:
    cycle_id = await cycles.start_cycle()
    structlog.contextvars.bind_contextvars(cycle_id=cycle_id)
    stats: dict[str, Any] = {}
    errors: dict[str, str] = {}
    try:
        for name, stage in stages:
            try:
                result = await stage.run()
            except Exception as exc:  # noqa: BLE001 (awaria etapu nie zatrzymuje kolejnych)
                log.exception("stage_failed", stage=name)
                errors[name] = f"{type(exc).__name__}: {exc}"
                continue
            stats[name] = result.as_json()
            errors.update(result.errors)
    finally:
        structlog.contextvars.unbind_contextvars("cycle_id")
    await cycles.finish_cycle(cycle_id, stats, errors)


async def run_loop(
    stages: Sequence[tuple[str, Stage]],
    cycles: CyclesRepo,
    interval: float,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    iterations: int | None = None,
) -> None:
    """Cykle co `interval` s, bez nakładania. Błąd zapisu cyklu nie zabija workera."""
    done = 0
    while iterations is None or done < iterations:
        started = clock()
        try:
            await run_cycle(stages, cycles)
        except Exception:  # noqa: BLE001 (np. chwilowa niedostępność Supabase)
            log.exception("cycle_loop_failed")
        done += 1
        await sleep(max(0.0, interval - (clock() - started)))
