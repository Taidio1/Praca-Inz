from typing import Any, Protocol

import structlog

from src.marketdata.providers import QuoteError, QuoteProvider

Row = dict[str, Any]

log = structlog.get_logger(__name__)


class MarketRepo(Protocol):
    async def assets_in_portfolios(self) -> list[Row]: ...
    async def insert_snapshot(
        self, asset_id: str, price: float, change_24h: float | None
    ) -> None: ...


class MarketDataService:
    """Pobiera notowania dla aktywów z portfeli i zapisuje snapshoty do bazy."""

    def __init__(
        self,
        crypto: QuoteProvider,
        stocks: QuoteProvider,
        commodities: QuoteProvider,
        repo: MarketRepo,
    ) -> None:
        self._providers: dict[str, QuoteProvider] = {
            "crypto": crypto, "commodity": commodities,
        }
        self._stocks = stocks
        self._repo = repo

    async def refresh_all(self) -> int:
        assets = await self._repo.assets_in_portfolios()
        written = 0
        for asset in assets:
            provider = self._providers.get(asset["asset_type"], self._stocks)
            try:
                quote = await provider.quote(asset["ticker"])
            except QuoteError as exc:
                log.warning(
                    "quote_failed", asset=asset["ticker"],
                    asset_type=asset["asset_type"], reason=str(exc),
                )
                continue
            await self._repo.insert_snapshot(asset["id"], quote.price, quote.change_24h)
            written += 1
        return written
