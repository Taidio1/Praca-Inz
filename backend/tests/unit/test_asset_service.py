from datetime import UTC, datetime

import pytest

from src.core.errors import NotFoundError
from src.services.assets import AssetService

ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
ASSET_ROW = {
    "id": ASSET_ID,
    "ticker": "BTC",
    "name": "Bitcoin",
    "asset_type": "crypto",
    "currency": "USD",
}


class FakeAssetsRepo:
    def __init__(self, row: dict | None) -> None:  # type: ignore[type-arg]
        self._row = row

    async def find_by_ticker(self, ticker: str, asset_type: str) -> dict | None:  # type: ignore[type-arg]
        return None

    async def get(self, asset_id: str) -> dict | None:  # type: ignore[type-arg]
        return self._row if self._row and self._row["id"] == asset_id else None


class FakeSnapshotsRepo:
    async def latest_for_assets(self, asset_ids: list[str]) -> dict[str, dict]:  # type: ignore[type-arg]
        return {
            ASSET_ID: {
                "price": 67000.0,
                "change_24h": -2.8,
                "indicators": {"rsi": 42.6},
                "funding": {"rate": 0.0082},
                "captured_at": "2026-07-03T10:00:00Z",
            }
        }

    async def history_for_asset(self, asset_id: str, limit: int = 100) -> list[dict]:  # type: ignore[type-arg]
        return [{"price": 67000.0, "change_24h": -2.8, "captured_at": "2026-07-03T10:00:00Z"}]


class FakeInsightsRepo:
    async def list_for_assets(self, asset_ids, *, before, sentiment, limit):  # type: ignore[no-untyped-def]
        return [
            {
                "id": "bbbbbbbb-0000-0000-0000-000000000001",
                "asset_id": ASSET_ID,
                "assets": {"ticker": "BTC"},
                "title": "T",
                "summary": "S",
                "sentiment_score": -0.3,
                "sentiment_label": "negative",
                "price_context": None,
                "created_at": datetime(2026, 7, 3, tzinfo=UTC),
                "insight_items": [],
            }
        ]


class FakeSourcesRepo:
    async def list_for_asset(
        self, asset_id: str, *, min_score: float | None, limit: int
    ) -> list[dict]:  # type: ignore[type-arg]
        rows = [
            {
                "score": 0.91,
                "method": "embedding",
                "reason": "R1",
                "source_items": {
                    "id": "cccccccc-0000-0000-0000-000000000001",
                    "title": "A",
                    "source": "rss",
                    "url": "http://a",
                    "published_at": None,
                },
            },
            {
                "score": 0.03,
                "method": "ticker_match",
                "reason": "R2",
                "source_items": {
                    "id": "cccccccc-0000-0000-0000-000000000002",
                    "title": "B",
                    "source": "gdelt",
                    "url": "http://b",
                    "published_at": None,
                },
            },
        ]
        if min_score is not None:
            rows = [r for r in rows if r["score"] >= min_score]
        return rows[:limit]


def make_service(asset_row: dict | None = ASSET_ROW) -> AssetService:  # type: ignore[type-arg]
    return AssetService(
        assets=FakeAssetsRepo(asset_row),
        snapshots=FakeSnapshotsRepo(),
        insights=FakeInsightsRepo(),
        sources=FakeSourcesRepo(),
    )


async def test_detail_returns_asset_snapshot_and_insights() -> None:
    detail = await make_service().get_detail(ASSET_ID)
    assert detail.asset.ticker == "BTC"
    assert detail.snapshot is not None and detail.snapshot.indicators == {"rsi": 42.6}
    assert len(detail.latest_insights) == 1


async def test_detail_unknown_asset_raises_not_found() -> None:
    with pytest.raises(NotFoundError):
        await make_service(asset_row=None).get_detail(ASSET_ID)


async def test_sources_include_rejected_and_respect_min_score() -> None:
    svc = make_service()
    all_rows = await svc.list_sources(ASSET_ID, min_score=None, limit=50)
    assert [s.score for s in all_rows] == [0.91, 0.03]  # odrzucone też widoczne
    filtered = await svc.list_sources(ASSET_ID, min_score=0.5, limit=50)
    assert [s.score for s in filtered] == [0.91]


async def test_list_snapshots_returns_history() -> None:
    svc = make_service()
    snaps = await svc.list_snapshots(ASSET_ID)
    assert len(snaps) == 1
    assert snaps[0].price == 67000.0
