import json

import httpx
import pytest

from src.marketdata.providers import BybitProvider, FinnhubProvider, QuoteError


def client_returning(payload: dict, status: int = 200) -> httpx.AsyncClient:  # type: ignore[type-arg]
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=json.dumps(payload))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_bybit_parses_spot_ticker() -> None:
    payload = {
        "retCode": 0,
        "result": {
            "list": [{"symbol": "BTCUSDT", "lastPrice": "67000.5", "price24hPcnt": "-0.0285"}]
        },
    }
    provider = BybitProvider(client_returning(payload))
    q = await provider.quote("btc")
    assert q.price == pytest.approx(67000.5)
    assert q.change_24h == pytest.approx(-2.85)


async def test_bybit_error_code_raises() -> None:
    provider = BybitProvider(
        client_returning({"retCode": 10001, "retMsg": "params error", "result": {}})
    )
    with pytest.raises(QuoteError):
        await provider.quote("XXX")


async def test_bybit_empty_list_raises() -> None:
    provider = BybitProvider(client_returning({"retCode": 0, "result": {"list": []}}))
    with pytest.raises(QuoteError):
        await provider.quote("XXX")


async def test_finnhub_parses_quote() -> None:
    provider = FinnhubProvider(client_returning({"c": 213.55, "dp": 1.23}), api_key="k")
    q = await provider.quote("aapl")
    assert q.price == pytest.approx(213.55)
    assert q.change_24h == pytest.approx(1.23)


async def test_finnhub_unknown_symbol_raises() -> None:
    # Finnhub zwraca c=0 dla nieznanych symboli
    provider = FinnhubProvider(client_returning({"c": 0, "dp": None}), api_key="k")
    with pytest.raises(QuoteError):
        await provider.quote("XXXX")


async def test_finnhub_without_key_raises() -> None:
    provider = FinnhubProvider(client_returning({}), api_key="")
    with pytest.raises(QuoteError):
        await provider.quote("AAPL")


async def test_http_error_raises_quote_error() -> None:
    provider = BybitProvider(client_returning({}, status=500))
    with pytest.raises(QuoteError):
        await provider.quote("BTC")


# ─── Yahoo (rynki spoza USA) i waluta notowania ──────────────────────────────


def _yahoo_meta(meta: dict) -> dict:  # type: ignore[type-arg]
    return {"chart": {"result": [{"meta": meta}], "error": None}}


async def test_yahoo_quote_reads_price_change_and_currency() -> None:
    from src.marketdata.providers import YahooQuoteProvider

    provider = YahooQuoteProvider(
        client_returning(
            _yahoo_meta(
                {"currency": "PLN", "regularMarketPrice": 255.6, "chartPreviousClose": 253.5}
            )
        )
    )
    q = await provider.quote("CDR.WA")
    assert q.price == pytest.approx(255.6)
    assert q.currency == "PLN"
    assert q.change_24h == pytest.approx((255.6 - 253.5) / 253.5 * 100)


async def test_stock_quotes_fall_back_to_yahoo_when_finnhub_has_no_access() -> None:
    from src.marketdata.providers import stock_quote_provider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "finnhub.io":
            return httpx.Response(403, json={"error": "You don't have access to this resource."})
        return httpx.Response(
            200, json=_yahoo_meta({"currency": "PLN", "regularMarketPrice": 255.6})
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    q = await stock_quote_provider(client, "k").quote("CDR.WA")
    assert q.price == pytest.approx(255.6)
    assert q.currency == "PLN"


async def test_quote_currency_resolver() -> None:
    from src.marketdata.providers import QuoteCurrencyResolver, YahooQuoteProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/CDR.WA"):
            return httpx.Response(
                200, json=_yahoo_meta({"currency": "PLN", "regularMarketPrice": 255.6})
            )
        return httpx.Response(500)

    resolver = QuoteCurrencyResolver(
        YahooQuoteProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    )
    assert await resolver.quote_currency("BTC", "crypto") == "USD"
    assert await resolver.quote_currency("CDR.WA", "stock") == "PLN"
    # Yahoo niedostępne: rynek USA (bez sufiksu) → USD, inny rynek → błąd, bez zgadywania
    assert await resolver.quote_currency("AAPL", "stock") == "USD"
    with pytest.raises(QuoteError):
        await resolver.quote_currency("VOD.L", "stock")


async def test_finnhub_search_keeps_foreign_listings_after_us_ones() -> None:
    from src.marketdata.symbol_search import FinnhubSymbolSearch

    payload = {
        "result": [
            {"symbol": "CDR.WA", "description": "CD PROJEKT", "type": "Common Stock"},
            {"symbol": "BRK.B", "description": "BERKSHIRE HATHAWAY", "type": "Common Stock"},
            {"symbol": "XETR:SAP", "description": "SAP", "type": "Common Stock"},
        ]
    }
    search = FinnhubSymbolSearch(client_returning(payload), api_key="k")
    tickers = [m.ticker for m in await search.search("x")]
    assert tickers == ["BRK.B", "CDR.WA"]
