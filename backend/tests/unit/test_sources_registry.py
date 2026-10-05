import httpx
import pytest

from src.core.config import Settings
from src.sources.registry import build_sources, feeds_from_settings
from src.sources.rss import DEFAULT_FEEDS


def test_empty_setting_uses_default_feeds() -> None:
    assert feeds_from_settings("") == DEFAULT_FEEDS


def test_json_setting_overrides_markets() -> None:
    feeds = feeds_from_settings('{"gpw": ["https://a.test/rss"]}')
    assert feeds["gpw"] == ("https://a.test/rss",)
    assert feeds["crypto"] == ()


def test_invalid_market_rejected() -> None:
    with pytest.raises(ValueError, match="nieznany rynek"):
        feeds_from_settings('{"mars": ["https://a.test"]}')


async def test_build_sources_order() -> None:
    settings = Settings(supabase_url="http://x", supabase_anon_key="k")  # type: ignore[call-arg]
    async with httpx.AsyncClient() as http:
        names = [s.name for s in build_sources(http, settings)]
    assert names == ["rss", "finnhub", "gdelt"]


async def test_build_sources_without_gdelt() -> None:
    settings = Settings(  # type: ignore[call-arg]
        supabase_url="http://x", supabase_anon_key="k", gdelt_enabled=False
    )
    async with httpx.AsyncClient() as http:
        names = [s.name for s in build_sources(http, settings)]
    assert names == ["rss", "finnhub"]
