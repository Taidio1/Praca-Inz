"""Twardy limit dzienny kosztu LLM (spec §5). Dzień liczony od północy UTC."""

from dataclasses import dataclass
from datetime import UTC, datetime

_EPS = 1e-9  # porównania kwot w USD bez błędów zaokrągleń float


def day_start_utc(now: datetime) -> datetime:
    utc = now.astimezone(UTC)
    return utc.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class Budget:
    limit_usd: float
    reserve_usd: float
    spent_usd: float

    def can_spend(self) -> bool:
        return self.spent_usd + self.reserve_usd <= self.limit_usd + _EPS

    def add(self, cost: float) -> None:
        self.spent_usd += cost

    @property
    def exhausted(self) -> bool:
        return not self.can_spend()
