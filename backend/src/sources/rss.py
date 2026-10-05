"""Źródło RSS: szerokie feedy per rynek, pobierane raz na cykl (ETag/If-Modified-Since)."""

import calendar
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser  # type: ignore[import-untyped]  # brak stubów i py.typed
import httpx
import structlog

from src.sources.base import (
    FetchResult,
    Market,
    RawItem,
    SourceFetchError,
    SourceName,
    SourceState,
    TrackedAsset,
)
from src.sources.dedup import strip_html
from src.sources.http import get_with_retry

log = structlog.get_logger(__name__)

# Zweryfikowane 2026-10-05 (HTTP 200, poprawne RSS). PAP Biznes nie ma publicznego RSS.
DEFAULT_FEEDS: dict[Market, tuple[str, ...]] = {
    "crypto": (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ),
    "gpw": (
        "https://www.bankier.pl/rss/wiadomosci.xml",
        "https://www.bankier.pl/rss/gielda.xml",
        "https://static.stooq.pl/rss/pl/b.rss",
    ),
    "us": (),
    "eu_etf": (
        "https://www.ecb.europa.eu/rss/press.html",
        "https://www.federalreserve.gov/feeds/press_all.xml",
    ),
}
_UA = "Mozilla/5.0 (Opes research tool)"
_SNIPPET_MAX = 1000


def _entry_time(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), UTC)


def parse_feed(content: bytes, feed_url: str, cutoff: datetime) -> list[RawItem]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise SourceFetchError(f"RSS nieczytelny: {parsed.get('bozo_exception')}")
    items: list[RawItem] = []
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        title = strip_html(entry.get("title") or "")
        if not link or not title:
            continue
        published = _entry_time(entry)
        if published is not None and published < cutoff:
            continue
        snippet = strip_html(entry.get("summary") or "")[:_SNIPPET_MAX] or None
        items.append(
            RawItem(
                source="rss",
                url=link,
                title=title,
                snippet=snippet,
                published_at=published,
                raw={"feed": feed_url, "guid": entry.get("id")},
            )
        )
    return items


class RssSource:
    name: SourceName = "rss"

    def __init__(
        self,
        http: httpx.AsyncClient,
        feeds: Mapping[Market, Sequence[str]],
        lookback_hours: int = 72,
    ) -> None:
        self._http = http
        self._feeds = feeds
        self._lookback = lookback_hours

    async def fetch(
        self, assets: list[TrackedAsset], states: Mapping[str, SourceState], now: datetime
    ) -> FetchResult:
        markets = {a.market for a in assets}
        urls = list(dict.fromkeys(u for m in markets for u in self._feeds.get(m, ())))
        result = FetchResult()
        for url in urls:
            key = f"rss:{url}"
            state = states.get(key)
            headers = {"User-Agent": _UA}
            if state and state.etag:
                headers["If-None-Match"] = state.etag
            if state and state.last_modified:
                headers["If-Modified-Since"] = state.last_modified
            try:
                res = await get_with_retry(self._http, url, headers=headers)
                if res.status_code == 304:
                    result.ok[key] = (
                        state.etag if state else None,
                        state.last_modified if state else None,
                    )
                    continue
                if res.status_code >= 400:
                    raise SourceFetchError(f"HTTP {res.status_code}")
                # Tylko stałe okno wstecz: feedy publikują z opóźnieniem, a ponowne
                # przeczytanie starego wpisu jest darmowe (unikalność source+url w bazie).
                cutoff = now - timedelta(hours=self._lookback)
                result.items.extend(parse_feed(res.content, url, cutoff))
            except SourceFetchError as exc:
                log.warning("rss_failed", source=url, reason=str(exc))
                result.errors[key] = str(exc)
                continue
            result.ok[key] = (res.headers.get("ETag"), res.headers.get("Last-Modified"))
        return result
