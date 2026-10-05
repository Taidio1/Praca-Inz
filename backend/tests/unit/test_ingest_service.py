from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from src.engine.ingest import IngestService
from src.sources.base import FetchResult, RawItem, SourceState, TrackedAsset
from src.sources.dedup import title_hash

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
CDR = TrackedAsset(id="a-cdr", ticker="CDR.WA", name="CD Projekt", asset_type="stock")


def item(url: str, title: str, source: str = "rss") -> RawItem:
    return RawItem(source=source, url=url, title=title, snippet=None,  # type: ignore[arg-type]
                   published_at=NOW, raw={}, hint_asset_ids=("a-cdr",))


class FakeSource:
    def __init__(self, name: str, result: FetchResult | Exception) -> None:
        self.name = name
        self._result = result

    async def fetch(self, assets: list[TrackedAsset], states: Mapping[str, SourceState],
                    now: datetime) -> FetchResult:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeRepo:
    def __init__(self, assets: list[TrackedAsset], existing: dict[str, str] | None = None,
                 states: dict[str, SourceState] | None = None) -> None:
        self.assets = assets
        self.existing = existing or {}
        self.states = states or {}
        self.saved: list[SourceState] = []
        self.rows: list[dict[str, Any]] = []
        self.hash_query_since: datetime | None = None

    async def tracked_assets(self) -> list[TrackedAsset]:
        return self.assets

    async def load_states(self) -> dict[str, SourceState]:
        return self.states

    async def save_states(self, states: list[SourceState]) -> None:
        self.saved.extend(states)

    async def existing_title_hashes(self, hashes: list[str], since: datetime) -> dict[str, str]:
        self.hash_query_since = since
        return {h: i for h, i in self.existing.items() if h in hashes}

    async def insert_items(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        known = {(r["source"], r["url"]) for r in self.rows}
        inserted = []
        for row in rows:
            if (row["source"], row["url"]) in known:
                continue
            stored = {**row, "id": f"id-{len(self.rows)}"}
            self.rows.append(stored)
            known.add((row["source"], row["url"]))
            inserted.append(stored)
        return inserted


def service(sources: list[FakeSource], repo: FakeRepo) -> IngestService:
    return IngestService(sources, repo, clock=lambda: NOW)


async def test_no_tracked_assets_is_noop() -> None:
    repo = FakeRepo([])
    stats = await service([FakeSource("rss", FetchResult())], repo).run()
    assert stats.tracked_assets == 0 and stats.inserted == 0
    assert repo.rows == [] and repo.saved == []


async def test_inserts_normalized_rows_with_hash_and_hints() -> None:
    res = FetchResult(items=[item("https://a.test/x?utm_source=RSS", "CD Projekt rośnie")],
                      ok={"rss:feed": ('"e"', None)})
    repo = FakeRepo([CDR])
    stats = await service([FakeSource("rss", res)], repo).run()
    row = repo.rows[0]
    assert row["url"] == "https://a.test/x"
    assert row["title_hash"] == title_hash("CD Projekt rośnie")
    assert row["raw"]["hint_asset_ids"] == ["a-cdr"]
    assert row["published_at"] == NOW.isoformat()
    assert "duplicate_of" not in row
    assert stats.fetched == 1 and stats.inserted == 1 and stats.per_source == {"rss": 1}
    assert repo.saved == [SourceState(key="rss:feed", last_fetched_at=NOW, etag='"e"')]


async def test_same_url_with_different_utm_is_one_row() -> None:
    res = FetchResult(items=[item("https://a.test/x?utm_medium=A", "T1"),
                             item("https://a.test/x?utm_medium=B", "T1")])
    repo = FakeRepo([CDR])
    stats = await service([FakeSource("rss", res)], repo).run()
    assert len(repo.rows) == 1 and stats.inserted == 1 and stats.duplicates == 0


async def test_title_duplicates_point_to_original() -> None:
    old_hash = title_hash("Orlen podnosi prognozy")
    res = FetchResult(items=[
        item("https://a.test/1", "Nowy temat"),
        item("https://b.test/2", "Nowy temat!", source="gdelt"),
        item("https://c.test/3", "Orlen podnosi prognozy"),
    ])
    repo = FakeRepo([CDR], existing={old_hash: "old-id"})
    stats = await service([FakeSource("rss", res)], repo).run()
    by_url = {r["url"]: r for r in repo.rows}
    assert "duplicate_of" not in by_url["https://a.test/1"]
    assert by_url["https://b.test/2"]["duplicate_of"] == by_url["https://a.test/1"]["id"]
    assert by_url["https://c.test/3"]["duplicate_of"] == "old-id"
    assert stats.inserted == 1 and stats.duplicates == 2
    assert repo.hash_query_since == NOW - timedelta(hours=48)


async def test_source_exception_is_isolated() -> None:
    ok = FetchResult(items=[item("https://a.test/1", "A")], ok={"rss:f": (None, None)})
    repo = FakeRepo([CDR])
    stats = await service([FakeSource("gdelt", RuntimeError("boom")),
                           FakeSource("rss", ok)], repo).run()
    assert stats.inserted == 1
    assert stats.errors["gdelt"] == "RuntimeError: boom"


async def test_failed_key_increments_failures_and_keeps_last_fetch() -> None:
    prev = SourceState(key="finnhub:a1", last_fetched_at=NOW - timedelta(hours=1),
                       consecutive_failures=2)
    res = FetchResult(errors={"finnhub:a1": "HTTP 401"})
    repo = FakeRepo([CDR], states={"finnhub:a1": prev})
    stats = await service([FakeSource("finnhub", res)], repo).run()
    assert repo.saved == [SourceState(key="finnhub:a1", last_fetched_at=NOW - timedelta(hours=1),
                                      consecutive_failures=3, last_error="HTTP 401")]
    assert stats.errors == {"finnhub:a1": "HTTP 401"}


async def test_source_crash_is_recorded_in_source_state() -> None:
    prev = SourceState(key="gdelt:*", consecutive_failures=1)
    repo = FakeRepo([CDR], states={"gdelt:*": prev})
    await service([FakeSource("gdelt", RuntimeError("boom"))], repo).run()
    assert repo.saved == [SourceState(key="gdelt:*", consecutive_failures=2,
                                      last_error="RuntimeError: boom")]


async def test_same_url_for_two_assets_keeps_both_hints() -> None:
    # Finnhub zwraca ten sam artykuł dla kilku tickerów: wskazówki trzeba scalić.
    a = RawItem(source="finnhub", url="https://n.test/1", title="Apple i Microsoft",
                snippet=None, published_at=NOW, raw={}, hint_asset_ids=("a-aapl",))
    b = RawItem(source="finnhub", url="https://n.test/1", title="Apple i Microsoft",
                snippet=None, published_at=NOW, raw={}, hint_asset_ids=("a-msft",))
    repo = FakeRepo([CDR])
    await service([FakeSource("finnhub", FetchResult(items=[a, b]))], repo).run()
    assert len(repo.rows) == 1
    assert repo.rows[0]["raw"]["hint_asset_ids"] == ["a-aapl", "a-msft"]
