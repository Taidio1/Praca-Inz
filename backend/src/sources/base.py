"""Wspólne typy źródeł newsów (spec 2026-10-05 §3)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from src.marketdata.symbols import exchange_suffix

Market = Literal["crypto", "us", "gpw", "eu_etf"]
SourceName = Literal["finnhub", "gdelt", "rss"]

# Nakładka okna pobierania: news opublikowany tuż przed poprzednim pobraniem nie przepada.
OVERLAP = timedelta(minutes=10)


class SourceFetchError(Exception):
    """Nieudane pobranie lub nieczytelna odpowiedź źródła."""


class RateLimitedError(SourceFetchError):
    """Źródło odpowiedziało 429: dalsze zapytania w tym cyklu tylko przedłużą blokadę."""


@dataclass(frozen=True)
class TrackedAsset:
    id: str
    ticker: str
    name: str
    asset_type: str
    aliases: tuple[str, ...] = ()

    @property
    def market(self) -> Market:
        if self.asset_type == "crypto":
            return "crypto"
        suffix = exchange_suffix(self.ticker)
        if suffix is None:
            return "us"
        if suffix == "WA":
            return "gpw"
        # Pozostałe giełdy zagraniczne: newsy głównie makro/indeksowe
        return "eu_etf"


@dataclass(frozen=True)
class RawItem:
    source: SourceName
    url: str
    title: str
    snippet: str | None
    published_at: datetime | None
    raw: dict[str, Any]
    # Źródło ukierunkowane wie, o które aktywo pytało; to sygnał, nie wyrok trafności.
    hint_asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceState:
    key: str
    last_fetched_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    consecutive_failures: int = 0
    last_error: str | None = None


@dataclass
class FetchResult:
    items: list[RawItem] = field(default_factory=list)
    # klucz źródła -> (etag, last_modified) dla udanych pobrań
    ok: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    # klucz źródła -> komunikat błędu
    errors: dict[str, str] = field(default_factory=dict)


class NewsSource(Protocol):
    name: SourceName

    async def fetch(
        self, assets: list[TrackedAsset], states: Mapping[str, SourceState], now: datetime
    ) -> FetchResult: ...


def since_for(
    key: str,
    states: Mapping[str, SourceState],
    now: datetime,
    lookback_hours: int,
    overlap: timedelta = OVERLAP,
) -> datetime:
    state = states.get(key)
    if state is None or state.last_fetched_at is None:
        return now - timedelta(hours=lookback_hours)
    return state.last_fetched_at - overlap
