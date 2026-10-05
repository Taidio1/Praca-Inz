"""Finnhub company-news: newsy per ticker dla rynku USA (darmowy plan)."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from src.sources.base import (
    FetchResult,
    RateLimitedError,
    RawItem,
    SourceFetchError,
    SourceName,
    SourceState,
    TrackedAsset,
)
from src.sources.dedup import strip_html
from src.sources.http import MinIntervalLimiter, get_with_retry

log = structlog.get_logger(__name__)


def parse_company_news(data: Any, asset_id: str, since: datetime) -> list[RawItem]:
    if not isinstance(data, list):
        raise SourceFetchError(f"Finnhub: nieoczekiwana odpowiedź {str(data)[:120]}")
    items: list[RawItem] = []
    for row in data:
        url = (row.get("url") or "").strip()
        title = strip_html(row.get("headline") or "")
        if not url or not title:
            continue
        ts = row.get("datetime")
        published = datetime.fromtimestamp(ts, UTC) if ts else None
        if published is not None and published < since:
            continue
        items.append(
            RawItem(
                source="finnhub",
                url=url,
                title=title,
                snippet=strip_html(row.get("summary") or "")[:1000] or None,
                published_at=published,
                raw={"id": row.get("id"), "publisher": row.get("source"),
                     "related": row.get("related"), "category": row.get("category")},
                hint_asset_ids=(asset_id,),
            )
        )
    return items


class FinnhubNewsSource:
    name: SourceName = "finnhub"

    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        limiter: MinIntervalLimiter,
        lookback_hours: int = 72,
        base_url: str = "https://finnhub.io",
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._limiter = limiter
        self._lookback = lookback_hours
        self._base_url = base_url

    async def fetch(
        self, assets: list[TrackedAsset], states: Mapping[str, SourceState], now: datetime
    ) -> FetchResult:
        result = FetchResult()
        if not self._api_key:
            return result  # bez klucza akcje USA pokrywa GDELT; to nie jest błąd cyklu
        rate_limited = False
        for asset in (a for a in assets if a.market == "us"):
            key = f"finnhub:{asset.id}"
            if rate_limited:
                # Limit współdzielony z workerem notowań: nie dobijamy go w tym cyklu.
                result.errors[key] = "HTTP 429 (pominięte w tym cyklu)"
                continue
            # Finnhub indeksuje z opóźnieniem: stałe okno wstecz, duplikaty odsiewa baza.
            since = now - timedelta(hours=self._lookback)
            await self._limiter.wait()
            try:
                res = await get_with_retry(
                    self._http,
                    f"{self._base_url}/api/v1/company-news",
                    params={
                        "symbol": asset.ticker.upper(),
                        "from": since.date().isoformat(),
                        "to": now.date().isoformat(),
                        "token": self._api_key,
                    },
                )
                if res.status_code >= 400:
                    raise SourceFetchError(f"HTTP {res.status_code}")
                try:
                    data = res.json()
                except ValueError as exc:
                    raise SourceFetchError("Finnhub: odpowiedź nie jest JSON-em") from exc
                result.items.extend(parse_company_news(data, asset.id, since))
            except SourceFetchError as exc:
                log.warning("finnhub_news_failed", asset=asset.ticker, reason=str(exc))
                rate_limited = isinstance(exc, RateLimitedError)
                result.errors[key] = str(exc)
                continue
            result.ok[key] = (None, None)
        return result
