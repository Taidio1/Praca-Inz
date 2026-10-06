"""Kiedy syntetyzować (spec §5): ważne wydarzenie, paczka newsów albo dzienne podsumowanie."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Trigger = Literal["important", "batch", "daily"]
_MAX_BACKOFF = 6 * 60  # minuty


@dataclass(frozen=True)
class Candidate:
    item_id: str
    score: float
    fetched_at: datetime


@dataclass(frozen=True)
class AssetActivity:
    last_insight_at: datetime | None
    insights_today: int
    # Nieudane syntezy (invalid/error) też kosztują: wycofanie wykładnicze od ostatniej
    last_failure_at: datetime | None = None
    failures_today: int = 0


@dataclass(frozen=True)
class TriggerRules:
    important_score: float
    batch_min: int
    daily_hours: int
    max_per_day: int
    min_gap_minutes: int


@dataclass(frozen=True)
class Decision:
    trigger: Trigger | None
    reason: str


def decide(
    candidates: Sequence[Candidate], activity: AssetActivity, rules: TriggerRules, now: datetime
) -> Decision:
    if not candidates:
        return Decision(None, "brak nowych trafnych newsów")
    if activity.insights_today >= rules.max_per_day:
        return Decision(None, f"limit {rules.max_per_day} syntez na dobę")
    last = activity.last_insight_at
    if last is not None and now - last < timedelta(minutes=rules.min_gap_minutes):
        return Decision(None, f"odstęp krótszy niż {rules.min_gap_minutes} min")
    failed = activity.last_failure_at
    if failed is not None and activity.failures_today > 0:
        backoff = timedelta(
            minutes=min(rules.min_gap_minutes * 2 ** (activity.failures_today - 1), _MAX_BACKOFF)
        )
        if now - failed < backoff:
            minutes = int(backoff.total_seconds() // 60)
            return Decision(None, f"błąd ostatniej syntezy, ponowienie po {minutes} min")
    top = max(c.score for c in candidates)
    if top >= rules.important_score:
        return Decision("important", f"news o trafności {top:.2f}")
    if len(candidates) >= rules.batch_min:
        return Decision("batch", f"{len(candidates)} nowych trafnych newsów")
    if last is not None and now - last >= timedelta(hours=rules.daily_hours):
        return Decision("daily", f"{rules.daily_hours} h od ostatniego insightu")
    return Decision(None, f"czeka na paczkę ({len(candidates)}/{rules.batch_min})")


def priority(decision: Decision, candidates: Sequence[Candidate]) -> tuple[int, int]:
    return (1 if decision.trigger == "important" else 0, len(candidates))
