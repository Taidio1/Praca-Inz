import time

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.api.deps import CurrentUser, get_current_user
from src.core.config import Settings
from src.core.errors import AuthError

SECRET = "test-secret"


def make_settings() -> Settings:
    return Settings(
        supabase_url="http://localhost:54321",
        supabase_anon_key="anon",
        supabase_jwt_secret=SECRET,
        _env_file=None,
    )


def make_token(
    *,
    sub: str = "11111111-1111-1111-1111-111111111111",
    secret: str = SECRET,
    exp_delta: int = 3600,
    aud: str = "authenticated",
) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "aud": aud, "iat": now, "exp": now + exp_delta},
        secret,
        algorithm="HS256",
    )


def creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_valid_token_returns_user() -> None:
    token = make_token()
    user = await get_current_user(credentials=creds(token), settings=make_settings())
    assert isinstance(user, CurrentUser)
    assert user.id == "11111111-1111-1111-1111-111111111111"
    assert user.token == token


async def test_missing_token_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        await get_current_user(credentials=None, settings=make_settings())


async def test_expired_token_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        await get_current_user(
            credentials=creds(make_token(exp_delta=-60)), settings=make_settings()
        )


async def test_wrong_signature_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        await get_current_user(
            credentials=creds(make_token(secret="inny-sekret")), settings=make_settings()
        )


async def test_wrong_audience_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        await get_current_user(credentials=creds(make_token(aud="anon")), settings=make_settings())


async def test_hs256_token_without_secret_raises_auth_error() -> None:
    settings = Settings(
        supabase_url="http://localhost:54321",
        supabase_anon_key="anon",
        supabase_jwt_secret="",
        _env_file=None,
    )
    with pytest.raises(AuthError):
        await get_current_user(credentials=creds(make_token()), settings=settings)
