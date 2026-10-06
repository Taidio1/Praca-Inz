"""Wyszukiwanie i walidacja symboli aktywow z dostepnych zrodel notowan."""

import asyncio
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import structlog

from src.marketdata.metals import METALS
from src.marketdata.providers import QuoteError, _get_json
from src.marketdata.symbols import exchange_suffix
from src.schemas.assets import AssetType

Row = dict[str, Any]

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SymbolMatch:
    ticker: str
    name: str
    asset_type: AssetType


class SymbolSearchError(Exception):
    """Nieudane wyszukiwanie symbolu w zewnetrznym zrodle."""


class LocalAssetsRepo(Protocol):
    async def search_local(self, q: str, limit: int) -> list[Row]: ...


CRYPTO_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "USDT": "Tether",
    "BNB": "BNB",
    "SOL": "Solana",
    "XRP": "XRP",
    "USDC": "USD Coin",
    "ADA": "Cardano",
    "DOGE": "Dogecoin",
    "TRX": "TRON",
    "AVAX": "Avalanche",
    "SHIB": "Shiba Inu",
    "DOT": "Polkadot",
    "LINK": "Chainlink",
    "BCH": "Bitcoin Cash",
    "NEAR": "NEAR Protocol",
    "MATIC": "Polygon",
    "POL": "Polygon",
    "LTC": "Litecoin",
    "UNI": "Uniswap",
    "ICP": "Internet Computer",
    "APT": "Aptos",
    "ETC": "Ethereum Classic",
    "XLM": "Stellar",
    "ATOM": "Cosmos",
    "FIL": "Filecoin",
    "ARB": "Arbitrum",
    "OP": "Optimism",
    "VET": "VeChain",
    "HBAR": "Hedera",
    "INJ": "Injective",
    "IMX": "Immutable",
    "SUI": "Sui",
    "MKR": "Maker",
    "GRT": "The Graph",
    "AAVE": "Aave",
    "RUNE": "THORChain",
    "ALGO": "Algorand",
    "STX": "Stacks",
    "EGLD": "MultiversX",
    "FTM": "Fantom",
    "SAND": "The Sandbox",
    "MANA": "Decentraland",
    "AXS": "Axie Infinity",
    "FLOW": "Flow",
    "CHZ": "Chiliz",
    "LDO": "Lido DAO",
    "QNT": "Quant",
    "TIA": "Celestia",
    "SEI": "Sei",
    "PYTH": "Pyth Network",
    "JUP": "Jupiter",
    "WIF": "dogwifhat",
    "PEPE": "Pepe",
}

_BYBIT_CACHE_TTL_SECONDS = 3600.0
_BYBIT_CACHE: dict[str, tuple[float, list[SymbolMatch]]] = {}


class BybitSymbolSearch:
    """Publiczna lista instrumentow spot Bybit, ograniczona do par USDT."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://api.bybit.com") -> None:
        self._client = client
        self._base_url = base_url

    async def search(self, q: str) -> list[SymbolMatch]:
        query = q.strip().lower()
        if not query:
            return []
        instruments = await self._instruments()
        matches = [
            item
            for item in instruments
            if item.ticker.lower().startswith(query) or query in item.name.lower()
        ]
        return sorted(matches, key=lambda item: _crypto_sort_key(item, query))

    async def lookup(self, ticker: str) -> SymbolMatch | None:
        wanted = ticker.strip().upper()
        if not wanted:
            return None
        for item in await self._instruments():
            if item.ticker == wanted:
                return item
        return None

    async def _instruments(self) -> list[SymbolMatch]:
        now = time.monotonic()
        cached = _BYBIT_CACHE.get(self._base_url)
        if cached and now - cached[0] < _BYBIT_CACHE_TTL_SECONDS:
            return cached[1]

        try:
            data = await _get_json(
                self._client,
                f"{self._base_url}/v5/market/instruments-info",
                params={"category": "spot"},
            )
        except QuoteError as exc:
            raise SymbolSearchError(str(exc)) from exc

        if data.get("retCode") != 0:
            raise SymbolSearchError(f"Bybit retCode={data.get('retCode')}: {data.get('retMsg')}")

        rows = (data.get("result") or {}).get("list") or []
        if not isinstance(rows, list):
            raise SymbolSearchError("Bybit: niepoprawny format listy instrumentow")

        seen: set[str] = set()
        instruments: list[SymbolMatch] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            base = str(row.get("baseCoin") or "").strip().upper()
            quote = str(row.get("quoteCoin") or "").strip().upper()
            status = str(row.get("status") or "")
            if not base or base in seen or quote != "USDT" or status != "Trading":
                continue
            seen.add(base)
            instruments.append(
                SymbolMatch(
                    ticker=base,
                    name=CRYPTO_NAMES.get(base, base),
                    asset_type="crypto",
                )
            )

        instruments.sort(key=lambda item: item.ticker)
        _BYBIT_CACHE[self._base_url] = (now, instruments)
        return instruments


class FinnhubSymbolSearch:
    """Wyszukiwanie akcji i ETF w Finnhub /search."""

    def __init__(
        self, client: httpx.AsyncClient, api_key: str, base_url: str = "https://finnhub.io"
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url

    async def search(self, q: str) -> list[SymbolMatch]:
        query = q.strip()
        if not query:
            return []
        if not self._api_key:
            log.warning("symbol_search_no_finnhub_key", source="finnhub")
            return []

        try:
            data = await _get_json(
                self._client,
                f"{self._base_url}/api/v1/search",
                params={"q": query, "token": self._api_key},
            )
        except QuoteError as exc:
            raise SymbolSearchError(str(exc)) from exc

        rows = data.get("result") or []
        if not isinstance(rows, list):
            raise SymbolSearchError("Finnhub: niepoprawny format wynikow wyszukiwania")

        matches: list[SymbolMatch] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or row.get("displaySymbol") or "").strip().upper()
            # Kropka: klasa akcji (BRK.B) albo rynek spoza USA (CDR.WA) — oba obsługujemy.
            # Dwukropek to notacja giełda:symbol, której źródła cen nie rozumieją.
            if not symbol or ":" in symbol:
                continue
            name = str(row.get("description") or symbol).strip()
            matches.append(
                SymbolMatch(
                    ticker=symbol,
                    name=name or symbol,
                    asset_type=_map_finnhub_type(str(row.get("type") or "")),
                )
            )
        # Notowania z USA przed zagranicznymi listingami tego samego emitenta (AAPL przed AAPL.MX)
        matches.sort(key=lambda item: exchange_suffix(item.ticker) is not None)
        return matches

    async def lookup(self, ticker: str, asset_type: AssetType) -> SymbolMatch | None:
        wanted = ticker.strip().upper()
        if not wanted:
            return None
        for item in await self.search(wanted):
            if item.ticker == wanted and item.asset_type == asset_type:
                return item
        return None


class AssetSearchService:
    """Laczy lokalny katalog aktywow z wyszukiwaniem w zrodlach notowan."""

    def __init__(
        self,
        local: LocalAssetsRepo,
        crypto: BybitSymbolSearch,
        stocks: FinnhubSymbolSearch,
    ) -> None:
        self._local = local
        self._crypto = crypto
        self._stocks = stocks

    async def search(self, q: str, limit: int = 10) -> list[SymbolMatch]:
        query = q.strip()
        if len(query) < 2:
            return []

        tasks: list[tuple[str, Awaitable[list[SymbolMatch]]]] = [
            ("metals", _search_metals(query)),
            ("local", self._search_local(query, limit)),
            ("bybit", self._crypto.search(query)),
            ("finnhub", self._stocks.search(query)),
        ]
        results = await asyncio.gather(
            *(task for _, task in tasks),
            return_exceptions=True,
        )

        deduped: dict[tuple[str, str], SymbolMatch] = {}
        for (source, _), result in zip(tasks, results, strict=True):
            if isinstance(result, BaseException):
                log.warning(
                    "asset_search_failed",
                    source=source,
                    query=query,
                    reason=str(result),
                )
                continue
            for item in result:
                key = (item.ticker.upper(), item.asset_type)
                if key not in deduped:
                    deduped[key] = item
        return list(deduped.values())[:limit]

    async def lookup(self, ticker: str, asset_type: AssetType) -> SymbolMatch | None:
        if asset_type == "crypto":
            return await self._crypto.lookup(ticker)
        if asset_type == "commodity":
            found = METALS.get(ticker.strip().upper())
            return _metal_match(found.ticker) if found else None
        return await self._stocks.lookup(ticker, asset_type)

    async def _search_local(self, q: str, limit: int) -> list[SymbolMatch]:
        rows = await self._local.search_local(q, limit)
        return [
            SymbolMatch(
                ticker=str(row["ticker"]).upper(),
                name=str(row["name"]),
                asset_type=_asset_type_from_row(row["asset_type"]),
            )
            for row in rows
        ]


def _metal_match(ticker: str) -> SymbolMatch:
    m = METALS[ticker]
    return SymbolMatch(ticker=m.ticker, name=m.name, asset_type="commodity")


async def _search_metals(query: str) -> list[SymbolMatch]:
    """Metale fizyczne nie mają zewnętrznego katalogu; dopasowanie po tickerze i aliasach."""
    q = query.casefold()
    return [
        _metal_match(m.ticker)
        for m in METALS.values()
        if any(alias.startswith(q) for alias in (m.ticker.casefold(), *m.aliases))
    ]


def _crypto_sort_key(item: SymbolMatch, query: str) -> tuple[int, str, str]:
    ticker = item.ticker.lower()
    if ticker == query:
        rank = 0
    elif ticker.startswith(query):
        rank = 1
    else:
        rank = 2
    return (rank, item.name.lower(), ticker)


def _map_finnhub_type(raw_type: str) -> AssetType:
    normalized = raw_type.strip().lower()
    if normalized in {"etp", "etf"} or "exchange traded fund" in normalized:
        return "etf"
    return "stock"


def _asset_type_from_row(raw_type: object) -> AssetType:
    if raw_type == "crypto":
        return "crypto"
    if raw_type == "stock":
        return "stock"
    if raw_type == "etf":
        return "etf"
    if raw_type == "commodity":
        return "commodity"
    raise SymbolSearchError(f"Niepoprawny typ aktywa w lokalnym katalogu: {raw_type}")
