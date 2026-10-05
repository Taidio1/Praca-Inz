import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from supabase import AsyncClient as SupabaseClient
from supabase import acreate_client

from src.api.app import create_app
from src.core.config import get_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("INTEGRATION_TESTS") != "1",
    reason="Wymaga lokalnego Supabase (INTEGRATION_TESTS=1)",
)

# Wartości lokalnego stacka: `supabase status` (anon key, service_role key, JWT secret).
# .get z pustym defaultem — moduł musi się importować przy zwykłym `pytest tests/`,
# gdy testy integracyjne są pomijane (skipif powyżej).
SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://localhost:54321")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", ANON_KEY)
    # JWT secret lokalnego stacka — patrz `supabase status`
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    get_settings.cache_clear()
    application = create_app()
    yield application
    get_settings.cache_clear()


@pytest.fixture
async def admin() -> AsyncIterator[SupabaseClient]:
    client = await acreate_client(SUPABASE_URL, SERVICE_KEY)
    yield client


@pytest.fixture
async def two_user_tokens(admin: SupabaseClient) -> AsyncIterator[tuple[str, str]]:
    """Tworzy dwóch użytkowników, zwraca ich access tokeny, sprząta po teście."""
    created_ids: list[str] = []
    tokens: list[str] = []
    for _ in range(2):
        email = f"test-{uuid.uuid4().hex[:12]}@opes.test"
        password = f"Pw-{uuid.uuid4().hex}"
        res = await admin.auth.admin.create_user(  # VERIFY-DOCS: admin API supabase-py
            {"email": email, "password": password, "email_confirm": True}
        )
        created_ids.append(res.user.id)
        user_client = await acreate_client(SUPABASE_URL, ANON_KEY)
        session = await user_client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        tokens.append(session.session.access_token)
    yield (tokens[0], tokens[1])
    for uid in created_ids:
        await admin.auth.admin.delete_user(uid)


def api(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
