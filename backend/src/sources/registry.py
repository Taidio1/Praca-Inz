"""Składanie listy źródeł newsów z konfiguracji."""

import json
from typing import get_args

import httpx

from src.core.config import Settings
from src.sources.base import Market, NewsSource
from src.sources.finnhub_news import FinnhubNewsSource
from src.sources.gdelt import GdeltSource
from src.sources.http import MinIntervalLimiter
from src.sources.rss import DEFAULT_FEEDS, RssSource

_MARKETS: tuple[Market, ...] = get_args(Market)


def feeds_from_settings(raw: str) -> dict[Market, tuple[str, ...]]:
    if not raw.strip():
        return dict(DEFAULT_FEEDS)
    data = json.loads(raw)
    unknown = set(data) - set(_MARKETS)
    if unknown:
        raise ValueError(f"RSS_FEEDS: nieznany rynek {sorted(unknown)}")
    return {m: tuple(data.get(m, ())) for m in _MARKETS}


def build_sources(http: httpx.AsyncClient, settings: Settings) -> list[NewsSource]:
    lookback = settings.ingest_lookback_hours
    return [
        RssSource(http, feeds_from_settings(settings.rss_feeds), lookback_hours=lookback),
        FinnhubNewsSource(
            http,
            settings.finnhub_api_key,
            MinIntervalLimiter(60.0 / settings.finnhub_news_rpm),
            lookback_hours=lookback,
        ),
        GdeltSource(
            http,
            MinIntervalLimiter(settings.gdelt_min_interval_seconds),
            lookback_hours=lookback,
        ),
    ]
