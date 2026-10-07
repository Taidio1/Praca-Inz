from datetime import UTC, datetime
from typing import Any

import pytest

from src.core.errors import ValidationError
from src.services.sources import SourcesService

ITEM = {
    "id": "bbbbbbbb-0000-0000-0000-000000000001",
    "source": "rss",
    "url": "https://www.bankier.pl/wiadomosc/x.html",
    "title": "Orlen podnosi prognozy",
    "snippet": "Spółka podała…",
    "published_at": "2026-10-06T10:00:00+00:00",
    "fetched_at": "2026-10-06T10:05:00+00:00",
    "duplicate_of": None,
}
ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
ROW = {
    **ITEM,
    "relevance_done": True,
    "assessments": [
        {
            "asset_id": ASSET_ID,
            "ticker": "PKN.WA",
            "score": 0.78,
            "method": "combined",
            "reason": 'nazwa "Orlen" w tytule (1.00); podobieństwo 0.85 → 0.67; wynik 0.83',
            "match_score": 1.0,
            "embedding_score": 0.85,
        }
    ],
}


class FakeAudit:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.page_args: dict[str, Any] = {}
        self.funnel_args: dict[str, Any] = {}

    async def page(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.page_args = kwargs
        return self.rows

    async def outlets(self, item_ids: list[str]) -> dict[str, str]:
        self.outlet_ids = item_ids
        return {ITEM["id"]: "Motley Fool"}

    async def funnel(self, **kwargs: Any) -> dict[str, Any]:
        self.funnel_args = kwargs
        return {
            "fetched": 354,
            "duplicates": 0,
            "scored": 354,
            "candidates": 40,
            "passed": 12,
            "rejected": 28,
            "unmatched": 314,
            "sent_to_llm": 0,
            "insights": 0,
            "cost_usd": 0,
        }

    async def evaluation_labels(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        self.evaluation_asset_ids = asset_ids
        return [
            {"item_id": "item-tp", "asset_id": ASSET_ID, "relevant": True, "score": 0.9},
            {"item_id": "item-fp", "asset_id": ASSET_ID, "relevant": False, "score": 0.8},
            {"item_id": "item-fn", "asset_id": ASSET_ID, "relevant": True, "score": 0.1},
        ]

    async def save_label(self, user_id: str, item_id: str, asset_id: str, relevant: bool) -> None:
        self.saved_label = (user_id, item_id, asset_id, relevant)


class FakeEngine:
    def __init__(self, cycle: dict[str, Any] | None, failing: list[dict[str, Any]]) -> None:
        self.cycle = cycle
        self.failing = failing

    async def latest_cycle(self) -> dict[str, Any] | None:
        return self.cycle

    async def failing_states(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.failing

    async def cost_since(self, since: datetime) -> float:
        # od północy UTC 6.10 (dzień) vs od 1.10 (miesiąc)
        return 0.59 if since.day == 6 else 2.4


class FakePortfolio:
    async def list_positions(self) -> list[dict[str, Any]]:
        return [{"assets": {"id": ASSET_ID}}]


class FakeSettings:
    def __init__(self, threshold: float | None) -> None:
        self.threshold = threshold

    async def get(self) -> dict[str, Any] | None:
        return None if self.threshold is None else {"relevance_threshold": self.threshold}


def make(
    rows: list[dict[str, Any]],
    threshold: float | None = 0.6,
    engine: FakeEngine | None = None,
) -> tuple[SourcesService, FakeAudit]:
    audit = FakeAudit(rows)
    svc = SourcesService(
        audit=audit,
        engine=engine or FakeEngine(None, []),
        portfolio=FakePortfolio(),
        settings=FakeSettings(threshold),
        daily_budget_usd=0.60,
    )
    return svc, audit


async def test_list_passes_portfolio_threshold_and_status() -> None:
    svc, audit = make([ROW])
    page = await svc.list_items(status="passed", asset_id=None, cursor=None, limit=1)
    assert audit.page_args == {
        "asset_ids": [ASSET_ID],
        "threshold": 0.6,
        "status": "passed",
        "before": None,
        "limit": 1,
        "asset_filter": None,
    }
    assert page.items[0].assessments[0].ticker == "PKN.WA"
    assert page.items[0].relevance_done is True
    assert page.next_cursor == f"2026-10-06T10:05:00+00:00|{ITEM['id']}"


async def test_no_cursor_on_partial_page() -> None:
    svc, _ = make([ROW])
    page = await svc.list_items(status="all", asset_id=None, cursor=None, limit=30)
    assert page.next_cursor is None


async def test_default_threshold_when_no_settings_row() -> None:
    svc, audit = make([], threshold=None)
    await svc.list_items(status="all", asset_id=None, cursor=None, limit=5)
    assert audit.page_args["threshold"] == 0.5


async def test_asset_outside_portfolio_returns_empty_without_query() -> None:
    svc, audit = make([ROW])
    page = await svc.list_items(
        status="all", asset_id="bbbbbbbb-0000-0000-0000-000000000009", cursor=None, limit=5
    )
    assert page.items == [] and audit.page_args == {}


async def test_keyset_cursor_parsed() -> None:
    # Cały cykl ingestu ma ten sam fetched_at (now() transakcji): sam timestamp gubi itemy.
    svc, audit = make([ROW])
    await svc.list_items(
        status="all", asset_id=None, cursor=f"2026-10-06T10:05:00+00:00|{ITEM['id']}", limit=1
    )
    assert audit.page_args["before"] == (datetime(2026, 10, 6, 10, 5, tzinfo=UTC), ITEM["id"])


async def test_malformed_cursor_is_validation_error() -> None:
    svc, _ = make([])
    with pytest.raises(ValidationError):
        await svc.list_items(status="all", asset_id=None, cursor="nie-kursor", limit=5)


async def test_funnel_uses_window_and_user_threshold() -> None:
    svc, audit = make([])
    out = await svc.funnel(hours=24, now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC))
    assert audit.funnel_args == {
        "since": datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        "asset_ids": [ASSET_ID],
        "threshold": 0.6,
    }
    assert (out.passed, out.rejected, out.threshold, out.hours) == (12, 28, 0.6, 24)


async def test_evaluation_uses_user_threshold_and_labeled_pairs() -> None:
    svc, audit = make([])

    out = await svc.evaluation()

    assert audit.evaluation_asset_ids == [ASSET_ID]
    assert (out.labeled_pairs, out.true_positive, out.false_positive, out.false_negative) == (
        3,
        1,
        1,
        1,
    )
    assert (out.precision, out.recall, out.f1, out.threshold) == (0.5, 0.5, 0.5, 0.6)


async def test_label_accepts_asset_from_users_portfolio() -> None:
    svc, audit = make([])

    await svc.label(
        "11111111-0000-0000-0000-000000000001",
        "bbbbbbbb-0000-0000-0000-000000000001",
        ASSET_ID,
        relevant=True,
    )

    assert audit.saved_label == (
        "11111111-0000-0000-0000-000000000001",
        "bbbbbbbb-0000-0000-0000-000000000001",
        ASSET_ID,
        True,
    )


async def test_label_rejects_asset_outside_users_portfolio() -> None:
    svc, _ = make([])

    with pytest.raises(ValidationError, match="portfela"):
        await svc.label(
            "11111111-0000-0000-0000-000000000001",
            "bbbbbbbb-0000-0000-0000-000000000001",
            "aaaaaaaa-0000-0000-0000-000000000099",
            relevant=False,
        )


async def test_engine_status_without_cycles() -> None:
    svc, _ = make([])
    status = await svc.engine_status()
    assert status.last_cycle is None and status.failing_sources == []


async def test_engine_status_maps_cycle_and_failures() -> None:
    cycle = {
        "started_at": "2026-10-06T10:00:00+00:00",
        "finished_at": None,
        "stats": {"ingest": {"inserted": 3}},
        "errors": {"rss:x": "HTTP 404"},
    }
    failing = [
        {
            "source_key": "rss:x",
            "last_fetched_at": None,
            "consecutive_failures": 2,
            "last_error": "HTTP 404",
        }
    ]
    svc, _ = make([], engine=FakeEngine(cycle, failing))
    status = await svc.engine_status()
    assert status.last_cycle is not None
    assert status.last_cycle.stats == {"ingest": {"inserted": 3}}
    assert status.failing_sources[0].key == "rss:x"


async def test_items_carry_publisher_name_as_outlet() -> None:
    # Finnhub podaje linki przekierowujące finnhub.io; w UI pokazujemy wydawcę z raw.
    svc, audit = make([ROW])
    page = await svc.list_items(status="all", asset_id=None, cursor=None, limit=5)
    assert page.items[0].outlet == "Motley Fool"
    assert audit.outlet_ids == [ITEM["id"]]


async def test_engine_status_reports_costs_and_budget() -> None:
    svc, _ = make([])
    status = await svc.engine_status(now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC))
    assert (status.cost_today_usd, status.cost_month_usd) == (0.59, 2.4)
    assert status.daily_budget_usd == 0.60
    # ta sama reguła co w silniku (Budget): 0.59 + rezerwa 0.01 mieści się w limicie
    assert status.budget_exhausted is False


async def test_engine_status_budget_exhausted_like_engine() -> None:
    class SpentEngine(FakeEngine):
        async def cost_since(self, since: datetime) -> float:
            return 0.595

    svc, _ = make([], engine=SpentEngine(None, []))
    status = await svc.engine_status(now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC))
    assert status.budget_exhausted is True
