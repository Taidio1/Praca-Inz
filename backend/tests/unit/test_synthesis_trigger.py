from datetime import UTC, datetime, timedelta

from src.synthesis.trigger import AssetActivity, Candidate, Decision, TriggerRules, decide, priority

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
RULES = TriggerRules(important_score=0.85, batch_min=3, daily_hours=24, max_per_day=6,
                     min_gap_minutes=30)
FRESH = AssetActivity(last_insight_at=None, insights_today=0)


def cand(score: float, i: int = 0) -> Candidate:
    return Candidate(item_id=f"i{i}", score=score, fetched_at=NOW - timedelta(minutes=5))


def test_no_candidates() -> None:
    assert decide([], FRESH, RULES, NOW).trigger is None


def test_important_single_item() -> None:
    d = decide([cand(0.9)], FRESH, RULES, NOW)
    assert d.trigger == "important"


def test_batch_needs_three() -> None:
    assert decide([cand(0.6, 1), cand(0.6, 2)], FRESH, RULES, NOW).trigger is None
    assert decide([cand(0.6, i) for i in range(3)], FRESH, RULES, NOW).trigger == "batch"


def test_daily_after_24h_with_one_item() -> None:
    old = AssetActivity(last_insight_at=NOW - timedelta(hours=25), insights_today=0)
    assert decide([cand(0.6)], old, RULES, NOW).trigger == "daily"
    recent = AssetActivity(last_insight_at=NOW - timedelta(hours=2), insights_today=1)
    assert decide([cand(0.6)], recent, RULES, NOW).trigger is None


def test_daily_cap_and_min_gap_block_even_important() -> None:
    capped = AssetActivity(last_insight_at=NOW - timedelta(hours=3), insights_today=6)
    assert decide([cand(0.95)], capped, RULES, NOW).trigger is None
    too_soon = AssetActivity(last_insight_at=NOW - timedelta(minutes=10), insights_today=1)
    d = decide([cand(0.95)], too_soon, RULES, NOW)
    assert d.trigger is None and "odstęp" in d.reason


def test_priority_orders_important_first_then_volume() -> None:
    imp = (Decision("important", ""), [cand(0.9)])
    big = (Decision("batch", ""), [cand(0.6, i) for i in range(5)])
    small = (Decision("batch", ""), [cand(0.6, i) for i in range(3)])
    ranked = sorted([small, big, imp], key=lambda x: priority(*x), reverse=True)
    assert ranked == [imp, big, small]
