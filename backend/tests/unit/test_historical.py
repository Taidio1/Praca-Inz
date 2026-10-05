import json
from datetime import UTC, date, datetime

import httpx
import pytest

from src.marketdata.historical import (
    BybitKlineProvider,
    FallbackProvider,
    HistoricalPrice,
    HistoricalPriceError,
    HistoricalPriceService,
    StooqProvider,
    YahooChartProvider,
    parse_bybit_kline,
    parse_bybit_kline_series,
    parse_stooq_csv,
    parse_stooq_csv_series,
    parse_yahoo_chart_series,
)


def _kline_row(day: date, close: str) -> list[str]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return [str(int(start.timestamp() * 1000)), "1", "2", "0.5", close, "10", "10"]


def test_parse_bybit_kline_takes_newest_candle() -> None:
    data = {
        "retCode": 0,
        "result": {
            "list": [  # Bybit zwraca od najnowszej
                _kline_row(date(2026, 7, 3), "108500.5"),
                _kline_row(date(2026, 7, 2), "107100.0"),
            ]
        },
    }
    hp = parse_bybit_kline(data, "BTCUSDT")
    assert hp == HistoricalPrice(
        price=108500.5, price_date=date(2026, 7, 3), source="bybit", currency="USD"
    )


def test_parse_bybit_kline_error_code_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_bybit_kline({"retCode": 10001, "retMsg": "params error"}, "BTCUSDT")


def test_parse_bybit_kline_empty_list_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_bybit_kline({"retCode": 0, "result": {"list": []}}, "XXXUSDT")


STOOQ_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-07-02,213.0,215.2,212.1,214.5,1000\n"
    "2026-07-03,214.6,216.0,213.9,215.75,900\n"
)


def test_parse_stooq_csv_takes_last_trading_day() -> None:
    hp = parse_stooq_csv(STOOQ_CSV, "aapl.us")
    assert hp == HistoricalPrice(price=215.75, price_date=date(2026, 7, 3), source="stooq")


def test_parse_stooq_csv_no_data_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_stooq_csv("No data\n", "xxxx.us")


def test_parse_stooq_csv_header_only_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_stooq_csv("Date,Open,High,Low,Close,Volume\n", "xxxx.us")


def test_parse_bybit_kline_series_sorts_ascending_by_date() -> None:
    data = {
        "retCode": 0,
        "result": {
            "list": [  # Bybit zwraca od najnowszej
                _kline_row(date(2026, 7, 3), "108500.5"),
                _kline_row(date(2026, 7, 2), "107100.0"),
                _kline_row(date(2026, 7, 1), "106000.0"),
            ]
        },
    }
    series = parse_bybit_kline_series(data, "BTCUSDT")
    assert series == [
        HistoricalPrice(
            price=106000.0, price_date=date(2026, 7, 1), source="bybit", currency="USD"
        ),
        HistoricalPrice(
            price=107100.0, price_date=date(2026, 7, 2), source="bybit", currency="USD"
        ),
        HistoricalPrice(
            price=108500.5, price_date=date(2026, 7, 3), source="bybit", currency="USD"
        ),
    ]


def test_parse_bybit_kline_series_error_code_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_bybit_kline_series({"retCode": 10001, "retMsg": "params error"}, "BTCUSDT")


def test_parse_bybit_kline_series_empty_list_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_bybit_kline_series({"retCode": 0, "result": {"list": []}}, "XXXUSDT")


def test_parse_stooq_csv_series_returns_all_rows_ascending() -> None:
    series = parse_stooq_csv_series(STOOQ_CSV, "aapl.us")
    assert series == [
        HistoricalPrice(price=214.5, price_date=date(2026, 7, 2), source="stooq"),
        HistoricalPrice(price=215.75, price_date=date(2026, 7, 3), source="stooq"),
    ]


def test_parse_stooq_csv_series_no_data_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_stooq_csv_series("No data\n", "xxxx.us")


def test_parse_stooq_csv_series_header_only_raises() -> None:
    with pytest.raises(HistoricalPriceError):
        parse_stooq_csv_series("Date,Open,High,Low,Close,Volume\n", "xxxx.us")


class FakeProvider:
    def __init__(self, price: float) -> None:
        self._price = price
        self.calls: list[str] = []

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        self.calls.append(ticker)
        return HistoricalPrice(price=self._price, price_date=on, source="fake")


def _mock_client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


async def test_bybit_kline_provider_price_series_parses_all_candles() -> None:
    payload = {
        "retCode": 0,
        "result": {
            "list": [
                _kline_row(date(2026, 7, 3), "108500.5"),
                _kline_row(date(2026, 7, 2), "107100.0"),
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(payload))

    provider = BybitKlineProvider(_mock_client(handler))
    series = await provider.price_series("BTC", 2)
    assert [p.price for p in series] == [107100.0, 108500.5]


async def test_bybit_kline_provider_price_series_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content="boom")

    provider = BybitKlineProvider(_mock_client(handler))
    with pytest.raises(HistoricalPriceError):
        await provider.price_series("BTC", 30)


async def test_stooq_provider_price_series_parses_all_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=STOOQ_CSV)

    provider = StooqProvider(_mock_client(handler))
    series = await provider.price_series("AAPL", 90)
    assert [p.price for p in series] == [214.5, 215.75]


class FakeSeriesProvider(FakeProvider):
    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        self.calls.append(f"{ticker}:{days}")
        return [HistoricalPrice(price=self._price, price_date=date(2026, 7, 3), source="fake")]


async def test_service_price_series_routes_crypto_and_stocks() -> None:
    crypto, stocks = FakeSeriesProvider(1.0), FakeSeriesProvider(2.0)
    svc = HistoricalPriceService(crypto=crypto, stocks=stocks)
    crypto_series = await svc.price_series("BTC", "crypto", 30)
    stock_series = await svc.price_series("AAPL", "stock", 90)
    assert crypto_series[0].price == 1.0
    assert stock_series[0].price == 2.0
    assert crypto.calls == ["BTC:30"]
    assert stocks.calls == ["AAPL:90"]


async def test_service_price_series_serves_repeated_calls_from_cache() -> None:
    crypto = FakeSeriesProvider(1.0)
    svc = HistoricalPriceService(crypto=crypto, stocks=FakeSeriesProvider(2.0))
    first = await svc.price_series("BTC", "crypto", 30)
    second = await svc.price_series("btc", "crypto", 30)
    assert first == second
    assert crypto.calls == ["BTC:30"]


async def test_service_price_series_cache_keyed_by_ticker_type_and_range() -> None:
    crypto, stocks = FakeSeriesProvider(1.0), FakeSeriesProvider(2.0)
    svc = HistoricalPriceService(crypto=crypto, stocks=stocks)
    await svc.price_series("BTC", "crypto", 30)
    await svc.price_series("BTC", "crypto", 90)
    await svc.price_series("ETH", "crypto", 30)
    await svc.price_series("BTC", "stock", 30)
    assert crypto.calls == ["BTC:30", "BTC:90", "ETH:30"]
    assert stocks.calls == ["BTC:30"]


async def test_service_routes_crypto_and_stocks() -> None:
    crypto, stocks = FakeProvider(1.0), FakeProvider(2.0)
    svc = HistoricalPriceService(crypto=crypto, stocks=stocks)
    d = date(2026, 7, 3)
    assert (await svc.price_on("BTC", "crypto", d)).price == 1.0
    assert (await svc.price_on("AAPL", "stock", d)).price == 2.0
    assert (await svc.price_on("SPY", "etf", d)).price == 2.0
    assert crypto.calls == ["BTC"]
    assert stocks.calls == ["AAPL", "SPY"]


# ─── Yahoo chart + fallback ──────────────────────────────────────────────────

STOOQ_CHALLENGE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><noscript>'
    "This site requires JavaScript to verify your browser.</noscript></body></html>"
)


def _ts(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 13, 30, tzinfo=UTC).timestamp())


def _yahoo_payload(rows: list[tuple[date, float | None]]) -> dict[str, object]:
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [_ts(d) for d, _ in rows],
                    "indicators": {"quote": [{"close": [c for _, c in rows]}]},
                }
            ],
            "error": None,
        }
    }


def test_stooq_html_challenge_raises_clear_error() -> None:
    with pytest.raises(HistoricalPriceError, match="ochrona antybotowa"):
        parse_stooq_csv(STOOQ_CHALLENGE, "aapl.us")
    with pytest.raises(HistoricalPriceError, match="ochrona antybotowa"):
        parse_stooq_csv_series(STOOQ_CHALLENGE, "aapl.us")


def test_parse_yahoo_chart_series_skips_nulls_and_sorts() -> None:
    data = _yahoo_payload(
        [
            (date(2026, 7, 3), 215.75),
            (date(2026, 7, 2), 213.0),
            (date(2026, 7, 1), None),
        ]
    )
    series = parse_yahoo_chart_series(data, "AAPL")
    assert series == [
        HistoricalPrice(price=213.0, price_date=date(2026, 7, 2), source="yahoo"),
        HistoricalPrice(price=215.75, price_date=date(2026, 7, 3), source="yahoo"),
    ]


def test_parse_yahoo_chart_series_unknown_symbol_raises() -> None:
    data = {"chart": {"result": None, "error": {"description": "No data found"}}}
    with pytest.raises(HistoricalPriceError, match="No data found"):
        parse_yahoo_chart_series(data, "ZZZZ")


async def test_yahoo_provider_price_on_weekend_takes_last_session() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=_yahoo_payload(
                [
                    (date(2026, 7, 2), 213.0),
                    (date(2026, 7, 3), 215.75),
                ]
            ),
        )

    hp = await YahooChartProvider(_mock_client(handler)).price_on("brk.b", date(2026, 7, 5))
    assert hp == HistoricalPrice(price=215.75, price_date=date(2026, 7, 3), source="yahoo")
    assert seen[0].url.path.endswith("/BRK-B")


async def test_yahoo_provider_404_with_chart_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"chart": {"result": None, "error": {"description": "delisted"}}}
        )

    with pytest.raises(HistoricalPriceError, match="delisted"):
        await YahooChartProvider(_mock_client(handler)).price_series("ZZZZ", 30)


class _FailingProvider:
    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        raise HistoricalPriceError("pierwsze źródło padło")

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        raise HistoricalPriceError("pierwsze źródło padło")


async def test_fallback_provider_uses_next_source() -> None:
    backup = FakeSeriesProvider(7.0)
    chain = FallbackProvider(_FailingProvider(), backup)
    assert (await chain.price_on("AAPL", date(2026, 7, 3))).price == 7.0
    assert (await chain.price_series("AAPL", 30))[0].price == 7.0


async def test_fallback_provider_reports_all_errors() -> None:
    chain = FallbackProvider(_FailingProvider(), _FailingProvider())
    with pytest.raises(HistoricalPriceError, match="padło; pierwsze"):
        await chain.price_on("AAPL", date(2026, 7, 3))


# ─── Waluta notowania i symbole spoza USA ────────────────────────────────────


def _with_currency(payload: dict[str, object], currency: str) -> dict[str, object]:
    chart = payload["chart"]
    assert isinstance(chart, dict)
    chart["result"][0]["meta"] = {"currency": currency}
    return payload


def test_parse_yahoo_chart_series_reads_quote_currency() -> None:
    data = _with_currency(_yahoo_payload([(date(2026, 10, 2), 255.6)]), "PLN")
    series = parse_yahoo_chart_series(data, "CDR.WA")
    assert series == [
        HistoricalPrice(
            price=255.6, price_date=date(2026, 10, 2), source="yahoo", currency="PLN"
        )
    ]


def test_parse_yahoo_chart_series_converts_pence_to_pounds() -> None:
    data = _with_currency(_yahoo_payload([(date(2026, 10, 2), 127.2)]), "GBp")
    hp = parse_yahoo_chart_series(data, "VOD.L")[0]
    assert hp.currency == "GBP"
    assert hp.price == pytest.approx(1.272)


async def test_yahoo_provider_keeps_exchange_suffix() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=_with_currency(_yahoo_payload([(date(2026, 10, 2), 255.6)]), "PLN")
        )

    hp = await YahooChartProvider(_mock_client(handler)).price_on("cdr.wa", date(2026, 10, 4))
    assert seen[0].url.path.endswith("/CDR.WA")
    assert hp.currency == "PLN"


def test_stooq_symbol_maps_markets() -> None:
    from src.marketdata.historical import stooq_symbol

    assert stooq_symbol("AAPL") == ("aapl.us", "USD")
    assert stooq_symbol("CDR.WA") == ("cdr", "PLN")
    with pytest.raises(HistoricalPriceError):
        stooq_symbol("VOD.L")
