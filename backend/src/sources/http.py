"""HTTP dla źródeł: odstęp między zapytaniami i ponawianie przy 429/5xx."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping

import httpx

from src.sources.base import RateLimitedError, SourceFetchError

Sleep = Callable[[float], Awaitable[None]]
_MAX_DELAY = 30.0


class MinIntervalLimiter:
    """Gwarantuje minimalny odstęp między kolejnymi wywołaniami `wait()`."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._min = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            target = now if self._next is None else max(now, self._next)
            if target > now:
                await self._sleep(target - now)
            self._next = target + self._min


def _retry_after(res: httpx.Response) -> float | None:
    value = res.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


async def get_with_retry(
    http: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    attempts: int = 3,
    base_delay: float = 2.0,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response:
    """GET z ponawianiem przy błędach sieci i 5xx. 429 kończy od razu (RateLimitedError).

    Inne statusy zwraca wywołującemu.
    """
    last_error = "brak odpowiedzi"
    for attempt in range(attempts):
        delay = base_delay * 2**attempt
        try:
            res = await http.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            last_error = f"sieć: {exc}"
        except httpx.HTTPError as exc:  # np. TooManyRedirects, InvalidURL: ponowienie nie pomoże
            raise SourceFetchError(f"HTTP: {exc}") from exc
        else:
            if res.status_code == 429:
                raise RateLimitedError("HTTP 429")
            if res.status_code < 500:
                return res
            last_error = f"HTTP {res.status_code}"
            delay = _retry_after(res) or delay
        if attempt < attempts - 1:
            await sleep(min(delay, _MAX_DELAY))
    raise SourceFetchError(last_error)
