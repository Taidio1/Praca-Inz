from src.marketdata.providers import Quote, QuoteError
from src.marketdata.service import MarketDataService

BTC = {"id": "aaaaaaaa-0000-0000-0000-000000000001", "ticker": "BTC", "asset_type": "crypto"}
AAPL = {"id": "aaaaaaaa-0000-0000-0000-000000000002", "ticker": "AAPL", "asset_type": "stock"}


class FakeProvider:
    def __init__(self, quotes: dict[str, Quote]) -> None:
        self._quotes = quotes
        self.calls: list[str] = []

    async def quote(self, ticker: str) -> Quote:
        self.calls.append(ticker)
        if ticker not in self._quotes:
            raise QuoteError(f"brak {ticker}")
        return self._quotes[ticker]


class FakeMarketRepo:
    def __init__(self, assets: list[dict]) -> None:  # type: ignore[type-arg]
        self._assets = assets
        self.snapshots: list[dict] = []  # type: ignore[type-arg]

    async def assets_in_portfolios(self) -> list[dict]:  # type: ignore[type-arg]
        return self._assets

    async def insert_snapshot(self, asset_id: str, price: float, change_24h: float | None) -> None:
        self.snapshots.append({"asset_id": asset_id, "price": price, "change_24h": change_24h})


def make_service(
    assets: list[dict],  # type: ignore[type-arg]
    crypto_quotes: dict[str, Quote] | None = None,
    stock_quotes: dict[str, Quote] | None = None,
) -> tuple[MarketDataService, FakeMarketRepo]:
    repo = FakeMarketRepo(assets)
    svc = MarketDataService(
        crypto=FakeProvider(crypto_quotes or {}),
        stocks=FakeProvider(stock_quotes or {}),
        repo=repo,
    )
    return svc, repo


async def test_refresh_routes_by_asset_type_and_writes_snapshots() -> None:
    svc, repo = make_service(
        [BTC, AAPL],
        crypto_quotes={"BTC": Quote(price=67000.5, change_24h=-2.85)},
        stock_quotes={"AAPL": Quote(price=213.55, change_24h=1.23)},
    )
    written = await svc.refresh_all()
    assert written == 2
    assert repo.snapshots[0] == {"asset_id": BTC["id"], "price": 67000.5, "change_24h": -2.85}
    assert repo.snapshots[1]["asset_id"] == AAPL["id"]


async def test_failed_quote_is_skipped_not_fatal() -> None:
    svc, repo = make_service(
        [BTC, AAPL],
        crypto_quotes={},  # BTC rzuci QuoteError
        stock_quotes={"AAPL": Quote(price=213.55, change_24h=None)},
    )
    written = await svc.refresh_all()
    assert written == 1
    assert [s["asset_id"] for s in repo.snapshots] == [AAPL["id"]]


async def test_etf_uses_stock_provider() -> None:
    etf = {"id": "aaaaaaaa-0000-0000-0000-000000000003", "ticker": "SPY", "asset_type": "etf"}
    svc, repo = make_service([etf], stock_quotes={"SPY": Quote(price=550.0, change_24h=0.4)})
    assert await svc.refresh_all() == 1
    assert repo.snapshots[0]["price"] == 550.0
