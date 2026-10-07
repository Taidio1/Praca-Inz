from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from src.core.errors import ValidationError
from src.relevance.evaluation import EvaluationLabel, calculate_metrics
from src.schemas.sources import (
    AssessmentOut,
    EngineCycleOut,
    EngineStatusOut,
    EvaluationMetricsOut,
    FunnelOut,
    RawSourceItemOut,
    SourceHealthOut,
    SourcePage,
)
from src.synthesis.budget import Budget, day_start_utc

Row = dict[str, Any]
Status = Literal["all", "passed", "rejected", "unmatched"]
_DEFAULT_THRESHOLD = 0.5


def _parse_cursor(cursor: str) -> tuple[datetime, str]:
    # Kursor keyset "fetched_at|id": cały cykl ingestu ma ten sam fetched_at.
    try:
        ts, item_id = cursor.split("|", 1)
        return datetime.fromisoformat(ts), str(UUID(item_id))
    except ValueError as exc:
        raise ValidationError("Nieprawidłowy kursor stronicowania") from exc


class AuditRepo(Protocol):
    async def page(
        self,
        *,
        asset_ids: list[str],
        threshold: float,
        status: str,
        before: tuple[datetime, str] | None,
        limit: int,
        asset_filter: str | None,
    ) -> list[Row]: ...
    async def outlets(self, item_ids: list[str]) -> dict[str, str]: ...
    async def funnel(self, *, since: datetime, asset_ids: list[str], threshold: float) -> Row: ...
    async def evaluation_labels(self, asset_ids: list[str]) -> list[Row]: ...
    async def save_label(
        self, user_id: str, item_id: str, asset_id: str, relevant: bool
    ) -> None: ...


class PortfolioRepo(Protocol):
    async def list_positions(self) -> list[Row]: ...


class SettingsRepo(Protocol):
    async def get(self) -> Row | None: ...


class EngineStatusRepo(Protocol):
    async def latest_cycle(self) -> Row | None: ...
    async def failing_states(self, limit: int = 20) -> list[Row]: ...
    async def cost_since(self, since: datetime) -> float: ...


class SourcesService:
    def __init__(
        self,
        audit: AuditRepo,
        engine: EngineStatusRepo,
        portfolio: PortfolioRepo,
        settings: SettingsRepo,
        daily_budget_usd: float = 0.60,
        cost_reserve_usd: float = 0.01,
    ) -> None:
        self._audit = audit
        self._engine = engine
        self._portfolio = portfolio
        self._settings = settings
        self._budget = daily_budget_usd
        self._reserve = cost_reserve_usd

    async def _scope(self) -> tuple[list[str], float]:
        positions = await self._portfolio.list_positions()
        asset_ids = [str(p["assets"]["id"]) for p in positions if p.get("assets")]
        row = await self._settings.get()
        threshold = float(row["relevance_threshold"]) if row else _DEFAULT_THRESHOLD
        return asset_ids, threshold

    async def list_items(
        self, *, status: Status, asset_id: str | None, cursor: str | None, limit: int
    ) -> SourcePage:
        before = _parse_cursor(cursor) if cursor else None
        asset_ids, threshold = await self._scope()
        if asset_id is not None and asset_id not in asset_ids:
            return SourcePage(items=[], next_cursor=None)
        rows = await self._audit.page(
            asset_ids=asset_ids,
            threshold=threshold,
            status=status,
            before=before,
            limit=limit,
            asset_filter=asset_id,
        )
        outlets = await self._audit.outlets([str(r["id"]) for r in rows])
        items = [
            RawSourceItemOut(
                item_id=r["id"],
                source=r["source"],
                url=r["url"],
                title=r["title"],
                snippet=r.get("snippet"),
                published_at=r.get("published_at"),
                fetched_at=r["fetched_at"],
                duplicate_of=r.get("duplicate_of"),
                relevance_done=bool(r.get("relevance_done")),
                assessments=[AssessmentOut(**a) for a in r.get("assessments") or []],
                outlet=outlets.get(str(r["id"])),
            )
            for r in rows
        ]
        next_cursor = (
            f"{items[-1].fetched_at.isoformat()}|{items[-1].item_id}"
            if len(items) == limit
            else None
        )
        return SourcePage(items=items, next_cursor=next_cursor)

    async def funnel(self, *, hours: int, now: datetime | None = None) -> FunnelOut:
        asset_ids, threshold = await self._scope()
        since = (now or datetime.now(UTC)) - timedelta(hours=hours)
        data = await self._audit.funnel(since=since, asset_ids=asset_ids, threshold=threshold)
        return FunnelOut(hours=hours, threshold=threshold, **data)

    async def evaluation(self) -> EvaluationMetricsOut:
        asset_ids, threshold = await self._scope()
        rows = await self._audit.evaluation_labels(asset_ids)
        metrics = calculate_metrics(
            (
                EvaluationLabel(relevant=bool(row["relevant"]), score=row.get("score"))
                for row in rows
            ),
            threshold=threshold,
        )
        return EvaluationMetricsOut(threshold=threshold, **metrics.__dict__)

    async def label(self, user_id: str, item_id: str, asset_id: str, *, relevant: bool) -> None:
        asset_ids, _ = await self._scope()
        if asset_id not in asset_ids:
            raise ValidationError("Możesz oznaczać tylko aktywa z własnego portfela")
        await self._audit.save_label(user_id, item_id, asset_id, relevant)

    async def engine_status(self, now: datetime | None = None) -> EngineStatusOut:
        cycle = await self._engine.latest_cycle()
        failing = await self._engine.failing_states()
        day = day_start_utc(now or datetime.now(UTC))
        today = await self._engine.cost_since(day)
        month = await self._engine.cost_since(day.replace(day=1))
        # ta sama reguła co w silniku, żeby UI i synteza zgadzały się co do limitu
        budget = Budget(self._budget, self._reserve, today)
        return EngineStatusOut(
            last_cycle=EngineCycleOut(
                started_at=cycle["started_at"],
                finished_at=cycle.get("finished_at"),
                stats=cycle.get("stats") or {},
                errors=cycle.get("errors") or {},
            )
            if cycle
            else None,
            failing_sources=[
                SourceHealthOut(
                    key=r["source_key"],
                    last_fetched_at=r.get("last_fetched_at"),
                    consecutive_failures=r["consecutive_failures"],
                    last_error=r.get("last_error"),
                )
                for r in failing
            ],
            cost_today_usd=round(today, 6),
            cost_month_usd=round(month, 6),
            daily_budget_usd=self._budget,
            budget_exhausted=budget.exhausted,
        )
