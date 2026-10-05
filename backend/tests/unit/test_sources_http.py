import httpx
import pytest

from src.sources.base import RateLimitedError, SourceFetchError
from src.sources.http import MinIntervalLimiter, get_with_retry


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_limiter_spaces_calls() -> None:
    fc = FakeClock()
    limiter = MinIntervalLimiter(6.0, clock=fc.clock, sleep=fc.sleep)
    await limiter.wait()
    await limiter.wait()
    fc.now += 10  # minęło więcej niż interwał
    await limiter.wait()
    assert fc.sleeps == [6.0]


def transport(statuses: list[int]) -> httpx.MockTransport:
    calls = iter(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(calls)
        headers = {"Retry-After": "1"} if status == 429 else {}
        return httpx.Response(status, text="ok", headers=headers)

    return httpx.MockTransport(handler)


async def test_429_raises_rate_limited_without_retry() -> None:
    # Ponawianie po 429 łamie limity GDELT/Finnhub (wspólny limit z workerem notowań).
    fc = FakeClock()
    async with httpx.AsyncClient(transport=transport([429, 200])) as http:
        with pytest.raises(RateLimitedError, match="429"):
            await get_with_retry(http, "https://x.test/a", sleep=fc.sleep)
    assert fc.sleeps == []


async def test_non_transport_httpx_error_becomes_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("pętla", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(SourceFetchError, match="pętla"):
            await get_with_retry(http, "https://x.test/a", sleep=FakeClock().sleep)


async def test_retry_exhausted_raises() -> None:
    fc = FakeClock()
    async with httpx.AsyncClient(transport=transport([503, 503, 503])) as http:
        with pytest.raises(SourceFetchError, match="503"):
            await get_with_retry(http, "https://x.test/a", sleep=fc.sleep)
    assert fc.sleeps == [2.0, 4.0]


async def test_client_error_is_returned_not_retried() -> None:
    fc = FakeClock()
    async with httpx.AsyncClient(transport=transport([404])) as http:
        res = await get_with_retry(http, "https://x.test/a", sleep=fc.sleep)
    assert res.status_code == 404
    assert fc.sleeps == []
