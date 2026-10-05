from collections.abc import Iterator

import pytest
from fastapi import FastAPI

from src.api.app import create_app
from src.core.config import get_settings
from src.marketdata.historical import _SERIES_CACHE


@pytest.fixture(autouse=True)
def _clear_price_series_cache() -> Iterator[None]:
    """Cache serii cenowych żyje na poziomie modułu — bez tego testy przeciekają."""
    _SERIES_CACHE.clear()
    yield
    _SERIES_CACHE.clear()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    get_settings.cache_clear()
    application = create_app()
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()
