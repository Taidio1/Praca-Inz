from datetime import UTC, datetime, timedelta, timezone

from src.synthesis.budget import Budget, day_start_utc


def test_day_starts_at_utc_midnight() -> None:
    warsaw = timezone(timedelta(hours=2))
    now = datetime(2026, 10, 6, 1, 30, tzinfo=warsaw)  # 23:30 UTC poprzedniego dnia
    assert day_start_utc(now) == datetime(2026, 10, 5, 0, 0, tzinfo=UTC)


def test_reserve_counts_against_limit() -> None:
    b = Budget(limit_usd=0.60, reserve_usd=0.01, spent_usd=0.585)
    assert b.can_spend()
    b.add(0.006)
    assert not b.can_spend() and b.exhausted


def test_exact_limit_is_allowed() -> None:
    assert Budget(limit_usd=0.60, reserve_usd=0.01, spent_usd=0.59).can_spend()
