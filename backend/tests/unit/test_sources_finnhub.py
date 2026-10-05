import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from src.sources.base import SourceFetchError, SourceState, TrackedAsset
from src.sources.finnhub_news import FinnhubNewsSource, parse_company_news
from src.sources.http import MinIntervalLimiter

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
OLD = datetime(2000, 1, 1, tzinfo=UTC)
AAPL = TrackedAsset(id="a-aapl", ticker="AAPL", name="Apple", asset_type="stock")
CDR = TrackedAsset(id="a-cdr", ticker="CDR.WA", name="CD Projekt", asset_type="stock")


def real_news() -> list[dict]:  # type: ignore[type-arg]
    return json.loads((FIX / "finnhub_company_news_AAPL.json").read_text(encoding="utf-8"))


def test_parse_real_company_news() -> None:
    items = parse_company_news(real_news(), "a-aapl", OLD)
    assert len(items) > 0
    for it in items:
        assert it.source == "finnhub"
        assert it.url.startswith("http")
        assert it.title
        assert it.hint_asset_ids == ("a-aapl",)
        assert it.published_at is not None and it.published_at.tzinfo == UTC


def test_parse_drops_items_before_since() -> None:
    data = real_news()
    times = sorted({row["datetime"] for row in data})
    assert len(times) > 1, "fixture Finnhub powinien mieć artykuły z różnymi datami"
    cutoff = datetime.fromtimestamp(times[len(times) // 2], UTC)
    items = parse_company_news(data, "a-aapl", cutoff)
    assert 0 < len(items) < len(data)
    assert all(it.published_at is not None and it.published_at >= cutoff for it in items)


def test_parse_rejects_error_object() -> None:
    with pytest.raises(SourceFetchError):
        parse_company_news({"error": "Invalid API key"}, "a-aapl", OLD)


async def instant_sleep(_: float) -> None:
    return None


async def test_fetch_only_us_assets_with_date_window() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=real_news())

    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = FinnhubNewsSource(
            http, "key", MinIntervalLimiter(0, sleep=instant_sleep), lookback_hours=24 * 365 * 30
        )
        result = await source.fetch([AAPL, CDR], {}, now)
    assert len(seen) == 1
    assert seen[0].url.params["symbol"] == "AAPL"
    assert seen[0].url.params["to"] == "2026-10-06"
    assert result.ok == {"finnhub:a-aapl": (None, None)}
    assert len(result.items) > 0


async def test_no_api_key_returns_empty_without_error() -> None:
    async with httpx.AsyncClient() as http:
        source = FinnhubNewsSource(http, "", MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch([AAPL], {}, datetime.now(UTC))
    assert result.items == [] and result.errors == {} and result.ok == {}


async def test_http_error_recorded_per_asset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = FinnhubNewsSource(http, "bad", MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch([AAPL], {}, datetime.now(UTC))
    assert "finnhub:a-aapl" in result.errors
    assert result.items == []


async def test_429_stops_finnhub_for_rest_of_cycle() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(429, json={"error": "API limit reached"})

    msft = TrackedAsset(id="a-msft", ticker="MSFT", name="Microsoft", asset_type="stock")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = FinnhubNewsSource(http, "key", MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch([AAPL, msft], {}, datetime.now(UTC))
    assert len(seen) == 1  # limit współdzielony z workerem notowań: nie dobijamy go
    assert result.errors == {
        "finnhub:a-aapl": "HTTP 429",
        "finnhub:a-msft": "HTTP 429 (pominięte w tym cyklu)",
    }


async def test_late_indexed_articles_not_cut_by_last_fetch() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=real_news())

    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    states = {"finnhub:a-aapl": SourceState(key="finnhub:a-aapl", last_fetched_at=now)}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = FinnhubNewsSource(
            http, "key", MinIntervalLimiter(0, sleep=instant_sleep), lookback_hours=24 * 365 * 30
        )
        result = await source.fetch([AAPL], states, now)
    assert len(result.items) == len([r for r in real_news() if r["url"] and r["headline"]])
    assert seen[0].url.params["from"] < "2026-10-01"


def test_parse_decodes_html_entities() -> None:
    # Finnhub zwraca np. "S&amp;P 500" i "Friday&#39;s" w nagłówkach i streszczeniach.
    items = parse_company_news(real_news(), "a-aapl", OLD)
    for it in items:
        for text in (it.title, it.snippet or ""):
            assert "&amp;" not in text and "&#39;" not in text and "&quot;" not in text
