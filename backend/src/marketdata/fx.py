"""Kursy walut: NBP (tabela A, kursy średnie PLN) jako źródło główne, Frankfurter (EBC) zapasowo.

NBP publikuje wyłącznie kursy względem PLN, więc pary krzyżowe (np. USD→EUR) liczymy
przez PLN: USD/PLN ÷ EUR/PLN z tej samej tabeli. Oba źródła są publiczne i nie wymagają
klucza API.

Dni bez notowań (weekend, święto) obsługujemy oknem wstecznym: kurs na dzień D to ostatnia
publikacja nie późniejsza niż D. Kursy historyczne (dni zakończone) zapisujemy w bazie per
żądany dzień — raz ustalone nie zmieniają się. Kurs bieżący trzymamy w pamięci z TTL, bo NBP
publikuje tabelę dzienną dopiero około południa.
"""

import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger(__name__)

# Waluty, w których można podać cenę transakcji (wszystkie są w tabeli A NBP i w EBC).
SUPPORTED_CURRENCIES: tuple[str, ...] = (
    "PLN", "USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD",
    "SEK", "NOK", "DKK", "CZK", "HUF",
)
BASE_CURRENCIES: tuple[str, ...] = ("PLN", "USD", "EUR")

_LOOKBACK_DAYS = 10  # najdłuższa przerwa w publikacji (święta + weekend) z zapasem
_NBP_MAX_RANGE_DAYS = 93  # limit API NBP dla zapytania o zakres dat
_CURRENT_TTL_SECONDS = 900.0
_CURRENT_CACHE: dict[tuple[str, str, date], tuple[float, "FxRate"]] = {}

SOURCE_LABELS = {"nbp": "NBP", "frankfurter": "EBC (Frankfurter)", "identity": "—"}


@dataclass(frozen=True)
class FxRate:
    """Kurs base→quote: 1 jednostka base = rate jednostek quote."""

    rate: float
    rate_date: date  # dzień publikacji kursu (może być wcześniejszy niż żądany)
    source: str


class FxRateError(Exception):
    """Nieudane pobranie kursu (HTTP, format odpowiedzi lub brak notowań)."""


class FxRateProvider(Protocol):
    async def observations(
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxRate]:
        """Opublikowane kursy base→quote w zakresie [start, end], rosnąco po dacie."""
        ...


class FxRepo(Protocol):
    async def get_rates(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]: ...
    async def save_rates(self, base: str, quote: str, rates: dict[date, FxRate]) -> None: ...


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


async def _with_retry[T](call: Callable[[], Awaitable[T]]) -> T:
    """Retry z exponential backoff dla błędów sieci i 5xx; 4xx zwracamy od razu."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.3, max=3),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    ):
        with attempt:
            return await call()
    raise AssertionError("unreachable")  # pragma: no cover


def parse_nbp_rates(data: Any, code: str) -> list[tuple[date, float]]:
    """Kursy średnie z odpowiedzi /exchangerates/rates/a/{code}/{start}/{end}/."""
    rates = (data or {}).get("rates")
    if not isinstance(rates, list):
        raise FxRateError(f"NBP: niepoprawny format odpowiedzi dla {code}")
    out: list[tuple[date, float]] = []
    for row in rates:
        try:
            out.append((date.fromisoformat(row["effectiveDate"]), float(row["mid"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise FxRateError(f"NBP: niepoprawny format kursu dla {code}") from exc
    out.sort(key=lambda item: item[0])
    return out


def cross_rates(
    base_pln: list[tuple[date, float]] | None,
    quote_pln: list[tuple[date, float]] | None,
    source: str,
) -> list[FxRate]:
    """base→quote z kursów względem PLN (None = waluta to PLN, kurs 1)."""
    base_map = dict(base_pln) if base_pln is not None else None
    quote_map = dict(quote_pln) if quote_pln is not None else None
    days: set[date] = set()
    if base_map is not None:
        days |= base_map.keys()
    if quote_map is not None:
        days = days & quote_map.keys() if base_map is not None else set(quote_map)
    out = []
    for day in sorted(days):
        b = base_map[day] if base_map is not None else 1.0
        q = quote_map[day] if quote_map is not None else 1.0
        out.append(FxRate(rate=b / q, rate_date=day, source=source))
    return out


class NbpProvider:
    """Tabela A NBP — kursy średnie walut obcych w PLN, także historyczne."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://api.nbp.pl") -> None:
        self._client = client
        self._base_url = base_url

    async def _pln_series(self, code: str, start: date, end: date) -> list[tuple[date, float]]:
        out: list[tuple[date, float]] = []
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(end, chunk_start + timedelta(days=_NBP_MAX_RANGE_DAYS - 1))
            out.extend(await self._fetch(code, chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(days=1)
        return out

    async def _fetch(self, code: str, start: date, end: date) -> list[tuple[date, float]]:
        url = (
            f"{self._base_url}/api/exchangerates/rates/a/{code.lower()}"
            f"/{start.isoformat()}/{end.isoformat()}/"
        )

        async def call() -> httpx.Response:
            res = await self._client.get(url, params={"format": "json"})
            if res.status_code >= 500:
                res.raise_for_status()
            return res

        try:
            res = await _with_retry(call)
        except httpx.HTTPError as exc:
            raise FxRateError(f"NBP HTTP: {exc}") from exc
        if res.status_code == 404:  # „Brak danych” — w zakresie nie było publikacji
            return []
        if res.status_code >= 400:
            raise FxRateError(f"NBP HTTP {res.status_code} dla {code}")
        try:
            data = res.json()
        except ValueError as exc:
            raise FxRateError("NBP: odpowiedź nie jest JSON-em") from exc
        return parse_nbp_rates(data, code)

    async def observations(
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxRate]:
        base_pln = None if base == "PLN" else await self._pln_series(base, start, end)
        quote_pln = None if quote == "PLN" else await self._pln_series(quote, start, end)
        return cross_rates(base_pln, quote_pln, "nbp")


def parse_frankfurter(data: Any, quote: str) -> list[FxRate]:
    rates = (data or {}).get("rates")
    if not isinstance(rates, dict):
        raise FxRateError("Frankfurter: niepoprawny format odpowiedzi")
    # Zapytanie o jeden dzień zwraca {"date": ..., "rates": {"PLN": 3.9}}
    if "date" in data and quote in rates and not isinstance(rates[quote], dict):
        rates = {data["date"]: rates}
    out = []
    for day, values in rates.items():
        try:
            out.append(
                FxRate(
                    rate=float(values[quote]),
                    rate_date=date.fromisoformat(day),
                    source="frankfurter",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FxRateError(f"Frankfurter: niepoprawny kurs {quote} dla {day}") from exc
    out.sort(key=lambda fx: fx.rate_date)
    return out


class FrankfurterProvider:
    """Kursy referencyjne EBC przez publiczne API Frankfurter."""

    def __init__(
        self, client: httpx.AsyncClient, base_url: str = "https://api.frankfurter.dev/v1"
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def observations(
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxRate]:
        url = f"{self._base_url}/{start.isoformat()}..{end.isoformat()}"

        async def call() -> httpx.Response:
            res = await self._client.get(url, params={"base": base, "symbols": quote})
            res.raise_for_status()
            return res

        try:
            res = await _with_retry(call)
            data = res.json()
        except httpx.HTTPError as exc:
            raise FxRateError(f"Frankfurter HTTP: {exc}") from exc
        except ValueError as exc:
            raise FxRateError("Frankfurter: odpowiedź nie jest JSON-em") from exc
        return [fx for fx in parse_frankfurter(data, quote) if fx.rate_date <= end]


class FallbackFxProvider:
    """Próbuje źródeł po kolei; pusty wynik też oznacza przejście do następnego."""

    def __init__(self, *providers: FxRateProvider) -> None:
        if not providers:
            raise ValueError("FallbackFxProvider wymaga co najmniej jednego źródła")
        self._providers = providers

    async def observations(
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxRate]:
        errors: list[str] = []
        for provider in self._providers:
            try:
                found = await provider.observations(base, quote, start, end)
            except FxRateError as exc:
                errors.append(str(exc))
                continue
            if found:
                return found
            errors.append(f"{type(provider).__name__}: brak kursów {base}/{quote}")
        raise FxRateError("; ".join(errors))


def fill_days(observations: list[FxRate], days: Iterable[date]) -> dict[date, FxRate]:
    """Kurs na każdy żądany dzień = ostatnia publikacja nie późniejsza niż ten dzień.
    Dni sprzed pierwszej publikacji w danych pomijamy (nie zgadujemy kursu)."""
    ordered = sorted(observations, key=lambda fx: fx.rate_date)
    resolved: dict[date, FxRate] = {}
    idx = 0
    last: FxRate | None = None
    for day in sorted(set(days)):
        while idx < len(ordered) and ordered[idx].rate_date <= day:
            last = ordered[idx]
            idx += 1
        if last is not None and (day - last.rate_date).days < _LOOKBACK_DAYS:
            resolved[day] = last
    return resolved


class FxService:
    """Kursy na konkretne dni z cache: baza (historia) + pamięć z TTL (dzień bieżący)."""

    def __init__(
        self,
        provider: FxRateProvider,
        repo: FxRepo,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._provider = provider
        self._repo = repo
        self._today = today

    async def rate_on(self, base: str, quote: str, on: date) -> FxRate:
        rates = await self.rates_on(base, quote, [on])
        if on not in rates:
            raise FxRateError(f"Brak kursu {base}/{quote} na {on.isoformat()}")
        return rates[on]

    async def current(self, base: str, quote: str) -> FxRate:
        return await self.rate_on(base, quote, self._today())

    async def rates_on(self, base: str, quote: str, days: Iterable[date]) -> dict[date, FxRate]:
        """Kursy base→quote na wskazane dni. Brak kursu dla dnia → dnia nie ma w wyniku."""
        base, quote = base.upper(), quote.upper()
        today = self._today()
        wanted = sorted({d for d in days if d <= today})
        if not wanted:
            return {}
        if base == quote:
            return {d: FxRate(rate=1.0, rate_date=d, source="identity") for d in wanted}

        result: dict[date, FxRate] = {}
        past = [d for d in wanted if d < today]
        if past:
            result.update(await self._repo.get_rates(base, quote, past))
        missing = [d for d in past if d not in result]

        if today in wanted:
            cached = _CURRENT_CACHE.get((base, quote, today))
            if cached and time.monotonic() - cached[0] < _CURRENT_TTL_SECONDS:
                result[today] = cached[1]
            else:
                missing.append(today)

        if missing:
            fetched = await self._fetch_days(base, quote, missing)
            result.update(fetched)
            to_save = {d: fx for d, fx in fetched.items() if d < today}
            if to_save:
                try:
                    await self._repo.save_rates(base, quote, to_save)
                except Exception as exc:  # zapis cache nie może wywrócić odczytu
                    log.warning("fx_cache_save_failed", pair=f"{base}/{quote}", reason=str(exc))
            if today in fetched:
                _CURRENT_CACHE[(base, quote, today)] = (time.monotonic(), fetched[today])
        return result

    async def _fetch_days(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]:
        start = min(days) - timedelta(days=_LOOKBACK_DAYS)
        end = max(days)
        observations = await self._provider.observations(base, quote, start, end)
        return fill_days(observations, days)


def default_fx_provider(client: httpx.AsyncClient) -> FallbackFxProvider:
    """NBP jako główne źródło (oficjalny kurs średni PLN), Frankfurter/EBC zapasowo."""
    return FallbackFxProvider(NbpProvider(client), FrankfurterProvider(client))
