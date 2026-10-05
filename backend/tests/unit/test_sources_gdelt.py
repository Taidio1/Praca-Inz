from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from src.sources.base import RateLimitedError, SourceFetchError, SourceState, TrackedAsset
from src.sources.gdelt import GdeltSource, gdelt_term, parse_artlist
from src.sources.http import MinIntervalLimiter

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def ta(i: int, name: str, ticker: str, asset_type: str = "stock") -> TrackedAsset:
    return TrackedAsset(id=f"a{i}", ticker=ticker, name=name, asset_type=asset_type)


def test_gdelt_term_strips_legal_forms() -> None:
    assert gdelt_term("Apple Inc.") == "Apple"
    assert gdelt_term("CD PROJEKT S.A.") == "CD PROJEKT"
    assert gdelt_term("Vanguard FTSE All-World UCITS ETF") == "Vanguard FTSE All-World"
    assert gdelt_term("Bitcoin") == "Bitcoin"
    assert gdelt_term("X") is None


def test_parse_real_artlist() -> None:
    items = parse_artlist((FIX / "gdelt_artlist_polish.json").read_text(encoding="utf-8"))
    assert len(items) > 0
    for it in items:
        assert it.source == "gdelt"
        assert it.url.startswith("http")
        assert it.title
        assert it.snippet is None
        assert it.published_at is not None and it.published_at.tzinfo == UTC
        assert "domain" in it.raw


def test_parse_empty_object_is_no_items() -> None:
    assert parse_artlist("{}") == []


def test_parse_artlist_rate_limit_text_is_error() -> None:
    text = (FIX / "gdelt_rate_limit.txt").read_text(encoding="utf-8")
    with pytest.raises(RateLimitedError, match="limit"):
        parse_artlist(text)


async def instant_sleep(_: float) -> None:
    return None


async def test_fetch_groups_by_language_and_chunks() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="{}")

    assets = [ta(i, f"Spolka{i}", f"S{i}.WA") for i in range(9)]
    assets.append(ta(99, "Bitcoin", "BTC", "crypto"))
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = GdeltSource(http, MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch(assets, {}, now)
    queries = [r.url.params["query"] for r in seen]
    assert len(queries) == 3  # 8 + 1 polskich, 1 angielskie
    assert queries[0].startswith('("Spolka0" OR "Spolka1"') and queries[0].endswith(
        ") sourcelang:polish"
    )
    assert queries[1] == '"Spolka8" sourcelang:polish'  # pojedyncza fraza bez nawiasów
    assert queries[2] == '"Bitcoin" sourcelang:english'
    assert seen[0].url.params["startdatetime"] == "20261003120000"
    assert set(result.ok) == {f"gdelt:{a.id}" for a in assets}


async def test_fetch_rate_limit_marks_chunk_failed() -> None:
    text = (FIX / "gdelt_rate_limit.txt").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=text)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = GdeltSource(http, MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch([ta(1, "Orlen", "PKN.WA")], {}, datetime.now(UTC))
    assert "gdelt:a1" in result.errors
    assert result.ok == {}


async def test_429_stops_gdelt_for_rest_of_cycle() -> None:
    # Prawdziwy GDELT przy limicie zwraca HTTP 429; każde kolejne zapytanie przedłuża blokadę.
    text = (FIX / "gdelt_rate_limit.txt").read_text(encoding="utf-8")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(429, text=text)

    assets = [ta(i, f"Spolka{i}", f"S{i}.WA") for i in range(9)]
    assets.append(ta(99, "Bitcoin", "BTC", "crypto"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = GdeltSource(http, MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch(assets, {}, datetime.now(UTC))
    assert len(seen) == 1  # bez ponowień i bez kolejnych chunków
    assert result.errors["gdelt:a0"] == "HTTP 429"
    assert result.errors["gdelt:a8"] == "HTTP 429 (pominięte w tym cyklu)"
    assert result.errors["gdelt:a99"] == "HTTP 429 (pominięte w tym cyklu)"
    assert result.ok == {}


async def test_5xx_is_not_retried_inside_cycle() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = GdeltSource(http, MinIntervalLimiter(0, sleep=instant_sleep))
        result = await source.fetch([ta(1, "Orlen", "PKN.WA")], {}, datetime.now(UTC))
    assert len(seen) == 1  # ponowienie omijałoby limiter 6 s; spróbuje następny cykl
    assert result.errors == {"gdelt:a1": "HTTP 503"}


async def test_known_key_window_overlaps_gdelt_index_lag() -> None:
    # Indeks GDELT DOC aktualizuje się co ~15 min: nakładka musi pokryć cykl + opóźnienie.
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="{}")

    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    states = {"gdelt:a1": SourceState(key="gdelt:a1", last_fetched_at=now)}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = GdeltSource(http, MinIntervalLimiter(0, sleep=instant_sleep))
        await source.fetch([ta(1, "Orlen", "PKN.WA")], states, now)
    assert seen[0].url.params["startdatetime"] == "20261006113000"


def test_parse_unexpected_json_shapes_are_source_errors() -> None:
    with pytest.raises(SourceFetchError):
        parse_artlist("[]")
    with pytest.raises(SourceFetchError):
        parse_artlist('{"articles": [{"url": "https://a.test", "title": "T", "seendate": "zle"}]}')
