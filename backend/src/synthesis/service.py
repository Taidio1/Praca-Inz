"""Etap 3 cyklu silnika: synteza LLM per aktywo (spec §5)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

import structlog

from src.relevance.service import TrackedAssetsRepo
from src.sources.base import TrackedAsset
from src.synthesis.budget import Budget, day_start_utc
from src.synthesis.prompt import (
    SYNTHESIS_SYSTEM,
    PriceSnapshot,
    PromptItem,
    build_items,
    build_user_message,
)
from src.synthesis.provider import LLMError, LLMProvider, LLMResult
from src.synthesis.trigger import (
    AssetActivity,
    Candidate,
    Decision,
    TriggerRules,
    decide,
    priority,
)
from src.synthesis.validator import SYNTHESIS_SCHEMA, DraftInvalid, SynthesisDraft, validate_draft

log = structlog.get_logger(__name__)
Row = dict[str, Any]
_MAX_TOKENS = 1024
# Dzierżawa blokady: wygasa sama, gdyby proces padł w trakcie syntezy
LOCK_TTL = timedelta(minutes=10)


class SynthesisRepo(Protocol):
    async def candidates(
        self,
        asset_id: str,
        *,
        threshold: float,
        since: datetime,
        fetched_after: datetime,
        limit: int,
    ) -> list[Row]: ...
    async def activity(self, asset_ids: list[str], day_start: datetime) -> dict[str, Row]: ...
    async def cost_since(self, since: datetime) -> float: ...
    async def profiles(self, asset_ids: list[str]) -> dict[str, Row]: ...
    async def snapshots(self, asset_ids: list[str]) -> dict[str, Row]: ...
    async def insert_run(self, row: Row) -> str: ...
    async def insert_insight(self, row: Row) -> str: ...
    async def insert_insight_items(self, rows: list[Row]) -> None: ...
    async def delete_insight(self, insight_id: str) -> None: ...
    async def acquire_lock(self, owner: str, ttl: timedelta) -> bool: ...
    async def release_lock(self, owner: str) -> None: ...


@dataclass
class SynthesisStats:
    checked: int = 0
    triggered: int = 0
    created: int = 0
    invalid: int = 0
    failed: int = 0
    skipped_budget: int = 0
    cost_usd: float = 0.0
    budget_exhausted: bool = False
    waiting: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "checked": self.checked, "triggered": self.triggered, "created": self.created,
            "invalid": self.invalid, "failed": self.failed,
            "skipped_budget": self.skipped_budget, "cost_usd": round(self.cost_usd, 6),
            "budget_exhausted": self.budget_exhausted, "waiting": self.waiting,
        }


def _ts(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class SynthesisService:
    def __init__(
        self,
        repo: SynthesisRepo,
        assets: TrackedAssetsRepo,
        provider: LLMProvider | None,
        *,
        rules: TriggerRules,
        threshold: float,
        lookback_hours: int,
        max_items: int,
        max_per_cycle: int,
        budget_usd: float,
        reserve_usd: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._assets = assets
        self._provider = provider
        self._rules = rules
        self._threshold = threshold
        self._lookback = timedelta(hours=lookback_hours)
        self._max_items = max_items
        self._max_per_cycle = max_per_cycle
        self._budget_usd = budget_usd
        self._reserve = reserve_usd
        self._clock = clock

    async def run(self) -> SynthesisStats:
        stats = SynthesisStats()
        if self._provider is None:
            stats.errors["llm"] = "brak ANTHROPIC_API_KEY"
            return stats
        # Jeden syntetyzujący proces na bazę (serwer + lokalny worker = podwójne insighty)
        owner = str(uuid4())
        if not await self._repo.acquire_lock(owner, LOCK_TTL):
            stats.errors["lock"] = "synteza wykonywana przez inny proces, pomijam w tym cyklu"
            return stats
        try:
            return await self._run_locked(stats)
        finally:
            await self._repo.release_lock(owner)

    async def _run_locked(self, stats: SynthesisStats) -> SynthesisStats:
        now = self._clock()
        assets = await self._assets.tracked_assets()
        if not assets:
            return stats
        ids = [a.id for a in assets]
        activity = await self._repo.activity(ids, day_start_utc(now))
        budget = Budget(self._budget_usd, self._reserve,
                        await self._repo.cost_since(day_start_utc(now)))

        ready: list[tuple[Decision, list[Row], TrackedAsset]] = []
        for asset in assets:
            stats.checked += 1
            act = activity.get(asset.id, {})
            last = _ts(act.get("last_insight_at"))
            since = last or now - self._lookback
            # since: czas OCENY po ostatnim insighcie (news oceniony później nie przepada);
            # fetched_after: zaległość ograniczona oknem wstecz
            rows = await self._repo.candidates(asset.id, threshold=self._threshold,
                                               since=since, fetched_after=now - self._lookback,
                                               limit=50)
            cands = [Candidate(str(r["item_id"]), float(r["score"]), _ts(r["fetched_at"]) or now)
                     for r in rows]
            activity_now = AssetActivity(
                last,
                int(act.get("insights_today", 0)),
                last_failure_at=_ts(act.get("last_failure_at")),
                failures_today=int(act.get("failures_today", 0)),
            )
            decision = decide(cands, activity_now, self._rules, now)
            if decision.trigger is None:
                stats.waiting[asset.ticker] = decision.reason
                continue
            ready.append((decision, rows, asset))

        ready.sort(key=lambda x: priority(x[0], [Candidate(str(r["item_id"]), float(r["score"]),
                                                           now) for r in x[1]]), reverse=True)
        ready = ready[: self._max_per_cycle]
        profiles: dict[str, Row] = {}
        snapshots: dict[str, Row] = {}
        if ready:
            profiles = await self._repo.profiles([a.id for _, _, a in ready])
            snapshots = await self._repo.snapshots([a.id for _, _, a in ready])
        for decision, rows, asset in ready:
            stats.triggered += 1
            if not budget.can_spend():
                stats.skipped_budget += 1
                stats.waiting[asset.ticker] = "limit dzienny budżetu"
                continue
            try:
                await self._synthesize(asset, decision, rows, activity.get(asset.id, {}),
                                       profiles.get(asset.id), snapshots.get(asset.id), budget,
                                       stats, now)
            except Exception as exc:  # noqa: BLE001 (błąd jednego aktywa nie zatrzymuje etapu)
                log.exception("synthesis_asset_failed", asset=asset.ticker)
                stats.failed += 1
                stats.errors[f"synthesis:{asset.ticker}"] = f"{type(exc).__name__}: {exc}"
        stats.budget_exhausted = budget.exhausted
        log.info("synthesis_done", **{k: v for k, v in stats.as_json().items() if k != "waiting"})
        return stats

    async def _call(self, user: str, budget: Budget, stats: SynthesisStats) -> LLMResult:
        assert self._provider is not None
        result = await self._provider.complete(system=SYNTHESIS_SYSTEM, user=user,
                                               max_tokens=_MAX_TOKENS, schema=SYNTHESIS_SCHEMA)
        budget.add(result.cost_usd)
        stats.cost_usd += result.cost_usd
        return result

    def _run_row(self, asset: TrackedAsset, user: str, result: LLMResult | None,
                 status: str, error: str | None) -> Row:
        assert self._provider is not None
        row: Row = {"asset_id": asset.id, "provider": self._provider.name,
                    "model": self._provider.model, "prompt": f"{SYNTHESIS_SYSTEM}\n\n{user}",
                    "response": result.text if result else "", "purpose": "synthesis",
                    "status": status, "error": error}
        if result:
            row.update(tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                       cache_read_tokens=result.cache_read_tokens,
                       latency_ms=result.latency_ms, cost_usd=result.cost_usd)
        return row

    async def _synthesize(
        self,
        asset: TrackedAsset,
        decision: Decision,
        rows: list[Row],
        act: Row,
        profile: Row | None,
        snap: Row | None,
        budget: Budget,
        stats: SynthesisStats,
        now: datetime,
    ) -> None:
        items: list[PromptItem] = build_items(rows, self._max_items)
        snapshot = (
            PriceSnapshot(snap.get("price"), snap.get("change_24h"),
                          _ts(snap["captured_at"]) or now)
            if snap else None
        )
        user = build_user_message(
            asset_name=asset.name, ticker=asset.ticker,
            market=(profile or {}).get("market") or asset.market,
            profile_text=(profile or {}).get("profile_text") or asset.name,
            items=items, snapshot=snapshot, previous_summary=act.get("last_summary"), now=now,
        )
        allowed = {i.short_id for i in items}
        attempt_user = user
        draft: SynthesisDraft | None = None
        result: LLMResult | None = None
        for attempt in range(2):
            try:
                result = await self._call(attempt_user, budget, stats)
            except LLMError as exc:
                # Odmowa i ucięcie są płatne (Etap 2, LLMError.result): koszt do budżetu i audytu
                if exc.result is not None:
                    budget.add(exc.result.cost_usd)
                    stats.cost_usd += exc.result.cost_usd
                await self._repo.insert_run(self._run_row(asset, attempt_user, exc.result,
                                                          "error", str(exc)))
                stats.failed += 1
                stats.errors[f"synthesis:{asset.ticker}"] = str(exc)
                return
            try:
                draft = validate_draft(result.text, allowed)
                break
            except DraftInvalid as exc:
                await self._repo.insert_run(self._run_row(asset, attempt_user, result,
                                                          "invalid", str(exc)))
                if attempt == 1 or not budget.can_spend():
                    stats.invalid += 1
                    return
                attempt_user = (f"{user}\n\nPoprzednia odpowiedź była niepoprawna: {exc}. "
                                "Zwróć poprawiony JSON.")
        assert draft is not None and result is not None
        run_id = await self._repo.insert_run(self._run_row(asset, attempt_user, result, "ok",
                                                           None))
        insight_id = await self._repo.insert_insight({
            "asset_id": asset.id, "llm_run_id": run_id, "title": draft.title,
            "summary": draft.summary, "sentiment_score": draft.sentiment_score,
            "sentiment_label": draft.sentiment_label, "price_context": draft.price_context,
            "trigger": decision.trigger,
        })
        by_short = {i.short_id: i for i in items}
        try:
            await self._repo.insert_insight_items([
                {"insight_id": insight_id, "item_id": by_short[s].item_id,
                 "relevance": by_short[s].score}
                for s in draft.key_item_ids
            ])
        except Exception:
            # Bez transakcji: kompensacja, żeby w strumieniu nie został insight bez źródeł
            await self._repo.delete_insight(insight_id)
            raise
        stats.created += 1
