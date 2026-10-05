from datetime import UTC, datetime
from uuid import UUID

from src.services.feed import FeedService

ASSET_BTC_ID = "aaaaaaaa-0000-0000-0000-000000000001"
ASSET_ETH_ID = "aaaaaaaa-0000-0000-0000-000000000002"


def insight_row(i: int, asset_id: str, score: float) -> dict:  # type: ignore[type-arg]
    return {
        "id": f"bbbbbbbb-0000-0000-0000-{i:012d}",
        "asset_id": asset_id,
        "assets": {"ticker": "BTC" if asset_id == ASSET_BTC_ID else "ETH"},
        "title": f"Insight {i}",
        "summary": "...",
        "sentiment_score": score,
        "sentiment_label": "negative" if score < 0 else "positive",
        "price_context": None,
        "created_at": datetime(2026, 7, 3, 12, 0, i, tzinfo=UTC),
        "insight_items": [
            {
                "relevance": 0.9,
                "source_items": {"title": "T", "source": "gdelt", "url": "http://x"},
            }
        ],
    }


class FakePortfolioRepo:
    def __init__(self, asset_ids: list[str]) -> None:
        self._ids = asset_ids

    async def list_positions(self) -> list[dict]:  # type: ignore[type-arg]
        return [
            {"id": f"p{i}", "quantity": 1, "assets": {"id": aid}} for i, aid in enumerate(self._ids)
        ]


class FakeInsightsRepo:
    def __init__(self, rows: list[dict]) -> None:  # type: ignore[type-arg]
        self.rows = rows
        self.last_call: dict = {}  # type: ignore[type-arg]

    async def list_for_assets(
        self,
        asset_ids: list[str],
        *,
        before: datetime | None,
        sentiment: str | None,
        limit: int,
    ) -> list[dict]:  # type: ignore[type-arg]
        self.last_call = {
            "asset_ids": asset_ids,
            "before": before,
            "sentiment": sentiment,
            "limit": limit,
        }
        rows = [r for r in self.rows if r["asset_id"] in asset_ids]
        return rows[:limit]


async def test_feed_queries_only_portfolio_assets() -> None:
    insights = FakeInsightsRepo([insight_row(1, ASSET_BTC_ID, -0.3)])
    svc = FeedService(portfolio=FakePortfolioRepo([ASSET_BTC_ID]), insights=insights)
    page = await svc.get_feed(asset_id=None, sentiment=None, cursor=None, limit=20)
    assert insights.last_call["asset_ids"] == [ASSET_BTC_ID]
    assert len(page.items) == 1
    assert page.items[0].key_items[0].source == "gdelt"
    assert page.next_cursor is None


async def test_feed_asset_filter_outside_portfolio_returns_empty() -> None:
    insights = FakeInsightsRepo([insight_row(1, ASSET_ETH_ID, 0.5)])
    svc = FeedService(portfolio=FakePortfolioRepo([ASSET_BTC_ID]), insights=insights)
    page = await svc.get_feed(asset_id=UUID(ASSET_ETH_ID), sentiment=None, cursor=None, limit=20)
    assert page.items == []


async def test_feed_empty_portfolio_returns_empty_page() -> None:
    insights = FakeInsightsRepo([insight_row(1, ASSET_BTC_ID, -0.3)])
    svc = FeedService(portfolio=FakePortfolioRepo([]), insights=insights)
    page = await svc.get_feed(asset_id=None, sentiment=None, cursor=None, limit=20)
    assert page.items == [] and page.next_cursor is None
    assert insights.last_call == {}  # repo nie był odpytywany


async def test_feed_sets_next_cursor_when_page_full() -> None:
    rows = [insight_row(i, ASSET_BTC_ID, -0.3) for i in range(3)]
    insights = FakeInsightsRepo(rows)
    svc = FeedService(portfolio=FakePortfolioRepo([ASSET_BTC_ID]), insights=insights)
    page = await svc.get_feed(asset_id=None, sentiment=None, cursor=None, limit=3)
    assert len(page.items) == 3
    assert page.next_cursor == rows[2]["created_at"]
