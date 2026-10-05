"""Ceny historyczne (dzienny close): Bybit kline (krypto) oraz Yahoo chart → Stooq (akcje/ETF).

Wszystkie źródła są publiczne i nie wymagają klucza API. Weekend/święto obsługiwane
przez okno wsteczne: bierzemy ostatnią świecę/wiersz nie późniejsze niż żądana data.

Stooq od 2026 zwraca zamiast CSV stronę z wyzwaniem JavaScript (ochrona antybotowa),
dlatego dla akcji/ETF głównym źródłem jest Yahoo, a Stooq zostaje jako zapasowe —
zadziała ponownie samoczynnie, jeśli blokada zostanie zdjęta. Wyzwania nie obchodzimy.
"""

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx

from src.marketdata.symbols import exchange_suffix, normalize_currency, yahoo_symbol
from src.schemas.assets import AssetType

_LOOKBACK_DAYS = 7

# Serie dzienne zmieniają się raz na dobę, a jedna seria potrafi być potrzebna
# kilkanaście razy w jednym żądaniu (historia portfela). Deps tworzą providera
# per request, więc cache musi żyć na poziomie modułu.
_SERIES_CACHE_TTL_SECONDS = 900.0
_SERIES_CACHE: dict[tuple[str, str, int], tuple[float, list["HistoricalPrice"]]] = {}


@dataclass(frozen=True)
class HistoricalPrice:
    price: float
    price_date: date
    source: str
    currency: str | None = None  # waluta notowania (ISO 4217), jeśli źródło ją podaje


class HistoricalPriceError(Exception):
    """Nieudane pobranie ceny historycznej (HTTP, format odpowiedzi lub brak notowań)."""


class HistoricalPriceProvider(Protocol):
    async def price_on(self, ticker: str, on: date) -> HistoricalPrice: ...
    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]: ...


def parse_bybit_kline(data: Any, symbol: str) -> HistoricalPrice:
    if data.get("retCode") != 0:
        raise HistoricalPriceError(
            f"Bybit retCode={data.get('retCode')}: {data.get('retMsg')}"
        )
    rows = (data.get("result") or {}).get("list") or []
    if not rows:
        raise HistoricalPriceError(f"Bybit: brak świec dla {symbol}")
    newest = rows[0]  # lista posortowana od najnowszej świecy
    try:
        start_ms = int(newest[0])
        close = float(newest[4])
    except (IndexError, TypeError, ValueError) as exc:
        raise HistoricalPriceError(f"Bybit: niepoprawny format świecy dla {symbol}") from exc
    price_date = datetime.fromtimestamp(start_ms / 1000, tz=UTC).date()
    return HistoricalPrice(
        price=close, price_date=price_date, source="bybit", currency="USD"
    )


def _ensure_stooq_csv(text: str, symbol: str) -> None:
    if text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        raise HistoricalPriceError(
            f"Stooq: odpowiedź HTML zamiast CSV dla {symbol} (ochrona antybotowa)"
        )


def parse_stooq_csv(text: str, symbol: str, currency: str | None = None) -> HistoricalPrice:
    _ensure_stooq_csv(text, symbol)
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:  # sam nagłówek albo "No data"
        raise HistoricalPriceError(f"Stooq: brak notowań dla {symbol}")
    last = lines[-1].split(",")
    try:
        return HistoricalPrice(
            price=float(last[4]),
            price_date=date.fromisoformat(last[0]),
            source="stooq",
            currency=currency,
        )
    except (IndexError, ValueError) as exc:
        raise HistoricalPriceError(f"Stooq: niepoprawny format CSV dla {symbol}") from exc


def parse_bybit_kline_series(data: Any, symbol: str) -> list[HistoricalPrice]:
    if data.get("retCode") != 0:
        raise HistoricalPriceError(
            f"Bybit retCode={data.get('retCode')}: {data.get('retMsg')}"
        )
    rows = (data.get("result") or {}).get("list") or []
    if not rows:
        raise HistoricalPriceError(f"Bybit: brak świec dla {symbol}")
    series = []
    for row in rows:
        try:
            start_ms = int(row[0])
            close = float(row[4])
        except (IndexError, TypeError, ValueError) as exc:
            raise HistoricalPriceError(
                f"Bybit: niepoprawny format świecy dla {symbol}"
            ) from exc
        price_date = datetime.fromtimestamp(start_ms / 1000, tz=UTC).date()
        series.append(
            HistoricalPrice(price=close, price_date=price_date, source="bybit", currency="USD")
        )
    series.sort(key=lambda hp: hp.price_date)  # Bybit zwraca od najnowszej — odwracamy
    return series


def parse_stooq_csv_series(
    text: str, symbol: str, currency: str | None = None
) -> list[HistoricalPrice]:
    _ensure_stooq_csv(text, symbol)
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:  # sam nagłówek albo "No data"
        raise HistoricalPriceError(f"Stooq: brak notowań dla {symbol}")
    series = []
    for line in lines[1:]:
        row = line.split(",")
        try:
            series.append(
                HistoricalPrice(
                    price=float(row[4]),
                    price_date=date.fromisoformat(row[0]),
                    source="stooq",
                    currency=currency,
                )
            )
        except (IndexError, ValueError) as exc:
            raise HistoricalPriceError(f"Stooq: niepoprawny format CSV dla {symbol}") from exc
    series.sort(key=lambda hp: hp.price_date)
    return series


class BybitKlineProvider:
    """Dzienne świece spot z publicznego API Bybit v5."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://api.bybit.com") -> None:
        self._client = client
        self._base_url = base_url

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        symbol = f"{ticker.upper()}USDT"
        day_start = datetime(on.year, on.month, on.day, tzinfo=UTC)
        window_start = day_start - timedelta(days=_LOOKBACK_DAYS - 1)
        window_end = day_start + timedelta(days=1)
        try:
            res = await self._client.get(
                f"{self._base_url}/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": symbol,
                    "interval": "D",
                    "start": str(int(window_start.timestamp() * 1000)),
                    "end": str(int(window_end.timestamp() * 1000) - 1),
                    "limit": str(_LOOKBACK_DAYS),
                },
            )
            res.raise_for_status()
            data = res.json()
        except httpx.HTTPError as exc:
            raise HistoricalPriceError(f"HTTP: {exc}") from exc
        except ValueError as exc:
            raise HistoricalPriceError("Odpowiedź nie jest JSON-em") from exc
        return parse_bybit_kline(data, symbol)

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        symbol = f"{ticker.upper()}USDT"
        now = datetime.now(UTC)
        window_start = now - timedelta(days=days)
        try:
            res = await self._client.get(
                f"{self._base_url}/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": symbol,
                    "interval": "D",
                    "start": str(int(window_start.timestamp() * 1000)),
                    "end": str(int(now.timestamp() * 1000)),
                    "limit": str(days),
                },
            )
            res.raise_for_status()
            data = res.json()
        except httpx.HTTPError as exc:
            raise HistoricalPriceError(f"HTTP: {exc}") from exc
        except ValueError as exc:
            raise HistoricalPriceError("Odpowiedź nie jest JSON-em") from exc
        return parse_bybit_kline_series(data, symbol)


def stooq_symbol(ticker: str) -> tuple[str, str]:
    """Symbol Stooq + waluta: USA → aapl.us (USD), GPW → cdr (PLN)."""
    suffix = exchange_suffix(ticker)
    if suffix is None:
        return f"{ticker.lower()}.us", "USD"
    if suffix == "WA":
        return ticker.rsplit(".", 1)[0].lower(), "PLN"
    raise HistoricalPriceError(f"Stooq: nieobsługiwany rynek dla {ticker.upper()}")


class StooqProvider:
    """Dzienne notowania EOD ze Stooq (CSV, bez klucza). USA: aapl.us, GPW: cdr."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://stooq.com") -> None:
        self._client = client
        self._base_url = base_url

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        symbol, currency = stooq_symbol(ticker)
        try:
            res = await self._client.get(
                f"{self._base_url}/q/d/l/",
                params={
                    "s": symbol,
                    "d1": (on - timedelta(days=_LOOKBACK_DAYS - 1)).strftime("%Y%m%d"),
                    "d2": on.strftime("%Y%m%d"),
                    "i": "d",
                },
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            raise HistoricalPriceError(f"HTTP: {exc}") from exc
        return parse_stooq_csv(res.text, symbol, currency)

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        symbol, currency = stooq_symbol(ticker)
        today = datetime.now(UTC).date()
        try:
            res = await self._client.get(
                f"{self._base_url}/q/d/l/",
                params={
                    "s": symbol,
                    "d1": (today - timedelta(days=days)).strftime("%Y%m%d"),
                    "d2": today.strftime("%Y%m%d"),
                    "i": "d",
                },
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            raise HistoricalPriceError(f"HTTP: {exc}") from exc
        return parse_stooq_csv_series(res.text, symbol, currency)


def parse_yahoo_chart_series(data: Any, symbol: str) -> list[HistoricalPrice]:
    """Dzienne zamknięcia z Yahoo chart v8 (ceny skorygowane o splity), rosnąco po dacie.
    Ceny w jednostkach drobnych (GBp) przeliczamy na jednostkę główną (GBP)."""
    chart = (data or {}).get("chart") or {}
    results = chart.get("result") or []
    if not results:
        err = (chart.get("error") or {}).get("description") or "brak wyników"
        raise HistoricalPriceError(f"Yahoo: brak notowań dla {symbol} ({err})")
    r = results[0]
    currency, factor = normalize_currency((r.get("meta") or {}).get("currency"))
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    by_day: dict[date, HistoricalPrice] = {}
    for ts, close in zip(stamps, closes, strict=False):
        if close is None:  # dni bez notowań / niepełne świece
            continue
        try:
            day = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=int(ts))).date()
            by_day[day] = HistoricalPrice(
                price=float(close) * factor, price_date=day, source="yahoo", currency=currency
            )
        except (TypeError, ValueError, OSError) as exc:
            raise HistoricalPriceError(f"Yahoo: niepoprawny format notowań dla {symbol}") from exc
    if not by_day:
        raise HistoricalPriceError(f"Yahoo: brak notowań dla {symbol}")
    return [by_day[d] for d in sorted(by_day)]


class YahooChartProvider:
    """Dzienne notowania akcji/ETF z publicznego Yahoo chart v8 — bez klucza API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://query1.finance.yahoo.com",
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def _series(self, ticker: str, start: date, end: date) -> list[HistoricalPrice]:
        symbol = yahoo_symbol(ticker)  # BRK.B → BRK-B, CDR.WA bez zmian
        period1 = datetime(start.year, start.month, start.day, tzinfo=UTC)
        period2 = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
        try:
            res = await self._client.get(
                f"{self._base_url}/v8/finance/chart/{symbol}",
                params={
                    "period1": str(int(period1.timestamp())),
                    "period2": str(int(period2.timestamp())),
                    "interval": "1d",
                },
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = res.json()
        except httpx.HTTPError as exc:
            raise HistoricalPriceError(f"HTTP: {exc}") from exc
        except ValueError as exc:
            raise HistoricalPriceError("Odpowiedź nie jest JSON-em") from exc
        # Nieznany symbol to 404 z JSON-em w polu chart.error — parser da czytelny komunikat.
        if res.status_code >= 400 and not (data or {}).get("chart"):
            raise HistoricalPriceError(f"HTTP {res.status_code} dla {symbol}")
        return [hp for hp in parse_yahoo_chart_series(data, symbol) if hp.price_date <= end]

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        series = await self._series(ticker, on - timedelta(days=_LOOKBACK_DAYS - 1), on)
        return series[-1]

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        today = datetime.now(UTC).date()
        return await self._series(ticker, today - timedelta(days=days), today)


class FallbackProvider:
    """Próbuje źródeł po kolei; błąd zgłasza dopiero, gdy zawiodą wszystkie."""

    def __init__(self, *providers: HistoricalPriceProvider) -> None:
        if not providers:
            raise ValueError("FallbackProvider wymaga co najmniej jednego źródła")
        self._providers = providers

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.price_on(ticker, on)
            except HistoricalPriceError as exc:
                errors.append(str(exc))
        raise HistoricalPriceError("; ".join(errors))

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.price_series(ticker, days)
            except HistoricalPriceError as exc:
                errors.append(str(exc))
        raise HistoricalPriceError("; ".join(errors))


def stock_price_provider(client: httpx.AsyncClient) -> FallbackProvider:
    """Akcje/ETF: Yahoo jako główne źródło, Stooq zapasowo."""
    return FallbackProvider(YahooChartProvider(client), StooqProvider(client))


class HistoricalPriceService:
    """Wybiera prowajdera po typie aktywa (crypto → Bybit, stock/etf → Yahoo/Stooq)."""

    def __init__(
        self, crypto: HistoricalPriceProvider, stocks: HistoricalPriceProvider
    ) -> None:
        self._crypto = crypto
        self._stocks = stocks

    async def price_on(
        self, ticker: str, asset_type: AssetType, on: date
    ) -> HistoricalPrice:
        provider = self._crypto if asset_type == "crypto" else self._stocks
        return await provider.price_on(ticker, on)

    async def price_series(
        self, ticker: str, asset_type: AssetType, days: int
    ) -> list[HistoricalPrice]:
        key = (ticker.upper(), asset_type, days)
        now = time.monotonic()
        cached = _SERIES_CACHE.get(key)
        if cached and now - cached[0] < _SERIES_CACHE_TTL_SECONDS:
            return cached[1]

        provider = self._crypto if asset_type == "crypto" else self._stocks
        series = await provider.price_series(ticker, days)
        _SERIES_CACHE[key] = (now, series)
        return series
