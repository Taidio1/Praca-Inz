from datetime import date

import pytest

from src.marketdata.historical import HistoricalPrice, HistoricalPriceError
from src.marketdata.metals import MetalPriceProvider, MetalQuoteProvider
from src.marketdata.providers import Quote, QuoteCurrencyResolver, QuoteError
from src.marketdata.symbol_search import AssetSearchService


class RecordingYahoo:
    def __init__(self) -> None:
        self.symbols: list[str] = []

    async def quote(self, ticker: str) -> Quote:
        self.symbols.append(ticker)
        return Quote(price=2400.0, change_24h=0.3, currency="USD")

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        self.symbols.append(ticker)
        return HistoricalPrice(price=2300.0, price_date=on, source="yahoo", currency="USD")

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        self.symbols.append(ticker)
        return []


class EmptySearch:
    async def search(self, q: str) -> list:  # type: ignore[type-arg]
        return []

    async def search_local(self, q: str, limit: int) -> list:  # type: ignore[type-arg]
        return []

    async def lookup(self, *args: object) -> None:
        return None


async def test_metal_quote_maps_ticker_to_comex_symbol() -> None:
    yahoo = RecordingYahoo()
    quote = await MetalQuoteProvider(yahoo).quote("xau")  # type: ignore[arg-type]
    assert quote.price == 2400.0
    assert yahoo.symbols == ["GC=F"]


async def test_metal_history_maps_silver() -> None:
    yahoo = RecordingYahoo()
    provider = MetalPriceProvider(yahoo)  # type: ignore[arg-type]
    await provider.price_on("XAG", date(2026, 10, 1))
    await provider.price_series("XAG", 30)
    assert yahoo.symbols == ["SI=F", "SI=F"]


async def test_unknown_metal_raises() -> None:
    with pytest.raises(QuoteError):
        await MetalQuoteProvider(RecordingYahoo()).quote("XPT")  # type: ignore[arg-type]
    with pytest.raises(HistoricalPriceError):
        await MetalPriceProvider(RecordingYahoo()).price_on("XPT", date(2026, 10, 1))  # type: ignore[arg-type]


async def test_metal_quote_currency_is_usd() -> None:
    resolver = QuoteCurrencyResolver(RecordingYahoo())  # type: ignore[arg-type]
    assert await resolver.quote_currency("XAU", "commodity") == "USD"


async def test_search_finds_metals_by_polish_name_and_lookup_resolves() -> None:
    search = AssetSearchService(local=EmptySearch(), crypto=EmptySearch(), stocks=EmptySearch())  # type: ignore[arg-type]
    found = await search.search("złot")
    assert [(m.ticker, m.asset_type) for m in found] == [("XAU", "commodity")]
    match = await search.lookup("xag", "commodity")
    assert match is not None and match.name == "Srebro (fizyczne)"
    assert await search.lookup("XPT", "commodity") is None
