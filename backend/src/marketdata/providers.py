"""Adaptery notowań: Bybit v5 (krypto, publiczny REST), Finnhub i Yahoo (akcje/ETF).

Finnhub w darmowym planie notuje tylko rynek USA, więc dla pozostałych giełd (CDR.WA)
bieżącą cenę bierzemy zapasowo z publicznego Yahoo chart.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from src.marketdata.symbols import exchange_suffix, normalize_currency, yahoo_symbol
from src.schemas.assets import AssetType


@dataclass(frozen=True)
class Quote:
    price: float
    change_24h: float | None
    currency: str | None = None  # waluta notowania, jeśli źródło ją podaje


class QuoteError(Exception):
    """Nieudane pobranie notowania (HTTP, format odpowiedzi lub brak symbolu)."""


class QuoteProvider(Protocol):
    async def quote(self, ticker: str) -> Quote: ...


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> Any:
    try:
        res = await client.get(url, params=params)
        res.raise_for_status()
        return res.json()
    except httpx.HTTPError as exc:
        raise QuoteError(f"HTTP: {exc}") from exc
    except ValueError as exc:
        raise QuoteError("Odpowiedź nie jest JSON-em") from exc


class BybitProvider:
    """Spot tickers z publicznego API Bybit v5 — nie wymaga klucza."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://api.bybit.com") -> None:
        self._client = client
        self._base_url = base_url

    async def quote(self, ticker: str) -> Quote:
        symbol = f"{ticker.upper()}USDT"
        data = await _get_json(
            self._client,
            f"{self._base_url}/v5/market/tickers",
            params={"category": "spot", "symbol": symbol},
        )
        if data.get("retCode") != 0:
            raise QuoteError(f"Bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            raise QuoteError(f"Bybit: brak notowania dla {symbol}")
        row = rows[0]
        try:
            # price24hPcnt to ułamek (np. "-0.0285"), API zwraca procenty w skali 0..1
            return Quote(
                price=float(row["lastPrice"]),
                change_24h=float(row["price24hPcnt"]) * 100,
                currency="USD",  # pary *USDT traktujemy jako USD
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise QuoteError(f"Bybit: niepoprawny format notowania dla {symbol}") from exc


class FinnhubProvider:
    """Kwotowania akcji/ETF z Finnhub /quote — wymaga darmowego klucza API."""

    def __init__(
        self, client: httpx.AsyncClient, api_key: str, base_url: str = "https://finnhub.io"
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url

    async def quote(self, ticker: str) -> Quote:
        if not self._api_key:
            raise QuoteError("Brak FINNHUB_API_KEY — pomijam akcje/ETF")
        data = await _get_json(
            self._client,
            f"{self._base_url}/api/v1/quote",
            params={"symbol": ticker.upper(), "token": self._api_key},
        )
        price = data.get("c")
        if not price:  # Finnhub zwraca c=0 dla nieznanych symboli
            raise QuoteError(f"Finnhub: brak notowania dla {ticker.upper()}")
        dp = data.get("dp")
        return Quote(
            price=float(price),
            change_24h=float(dp) if dp is not None else None,
            currency="USD" if exchange_suffix(ticker) is None else None,
        )


def parse_yahoo_quote(data: Any, symbol: str) -> Quote:
    results = ((data or {}).get("chart") or {}).get("result") or []
    if not results:
        raise QuoteError(f"Yahoo: brak notowania dla {symbol}")
    meta = results[0].get("meta") or {}
    currency, factor = normalize_currency(meta.get("currency"))
    try:
        price = float(meta["regularMarketPrice"]) * factor
    except (KeyError, TypeError, ValueError) as exc:
        raise QuoteError(f"Yahoo: niepoprawny format notowania dla {symbol}") from exc
    prev = meta.get("chartPreviousClose")
    change: float | None = None
    if prev:
        prev_price = float(prev) * factor
        change = (price - prev_price) / prev_price * 100
    return Quote(price=price, change_24h=change, currency=currency)


class YahooQuoteProvider:
    """Bieżąca cena z publicznego Yahoo chart v8 (meta.regularMarketPrice) — bez klucza API."""

    def __init__(
        self, client: httpx.AsyncClient, base_url: str = "https://query1.finance.yahoo.com"
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def _chart(self, ticker: str) -> Any:
        symbol = yahoo_symbol(ticker)
        try:
            res = await self._client.get(
                f"{self._base_url}/v8/finance/chart/{symbol}",
                params={"range": "1d", "interval": "1d"},  # chartPreviousClose = poprzednia sesja
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return res.json()
        except httpx.HTTPError as exc:
            raise QuoteError(f"HTTP: {exc}") from exc
        except ValueError as exc:
            raise QuoteError("Odpowiedź nie jest JSON-em") from exc

    async def quote(self, ticker: str) -> Quote:
        return parse_yahoo_quote(await self._chart(ticker), yahoo_symbol(ticker))


class FallbackQuoteProvider:
    """Próbuje źródeł po kolei; błąd zgłasza dopiero, gdy zawiodą wszystkie."""

    def __init__(self, *providers: QuoteProvider) -> None:
        if not providers:
            raise ValueError("FallbackQuoteProvider wymaga co najmniej jednego źródła")
        self._providers = providers

    async def quote(self, ticker: str) -> Quote:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.quote(ticker)
            except QuoteError as exc:
                errors.append(str(exc))
        raise QuoteError("; ".join(errors))


def stock_quote_provider(client: httpx.AsyncClient, finnhub_api_key: str) -> QuoteProvider:
    """Akcje/ETF: Finnhub (USA) jako główne źródło, Yahoo dla pozostałych rynków."""
    return FallbackQuoteProvider(
        FinnhubProvider(client, finnhub_api_key), YahooQuoteProvider(client)
    )


class QuoteCurrencyResolver:
    """Ustala walutę notowania aktywa: krypto → USD (pary USDT), akcje/ETF → Yahoo meta.currency.

    Gdy Yahoo nie odpowiada, ticker bez sufiksu giełdy to rynek USA (konwencja Finnhub),
    więc USD. Dla innych rynków bez odpowiedzi źródła waluty nie zgadujemy.
    """

    def __init__(self, yahoo: YahooQuoteProvider) -> None:
        self._yahoo = yahoo

    async def quote_currency(self, ticker: str, asset_type: AssetType) -> str:
        if asset_type == "crypto":
            return "USD"
        try:
            currency = (await self._yahoo.quote(ticker)).currency
        except QuoteError:
            currency = None
        if currency:
            return currency
        if exchange_suffix(ticker) is None:
            return "USD"
        raise QuoteError(f"Nie udało się ustalić waluty notowania {ticker.upper()}")
