import importlib
import sys
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings


async def test_dashboard_api_entrypoint_exposes_health_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    get_settings.cache_clear()
    sys.modules.pop("src.dashboard.api", None)

    module: Any = importlib.import_module("src.dashboard.api")

    async with AsyncClient(
        transport=ASGITransport(app=module.app), base_url="http://test"
    ) as client:
        res = await client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    get_settings.cache_clear()
