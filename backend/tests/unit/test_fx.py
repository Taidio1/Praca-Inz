from collections.abc import Callable, Iterator
from datetime import date

import httpx
import pytest

from src.marketdata import fx as fx_module
from src.marketdata.fx import (
    FallbackFxProvider,
    FrankfurterProvider,
    FxRate,
    FxRateError,
    FxService,
    NbpProvider,
    cross_rates,
    fill_days,
    parse_frankfurter,
    parse_nbp_rates,
)

FRI = date(2026, 10, 2)
SAT = date(2026, 10, 3)
SUN = date(2026, 10, 4)
MON = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def _clear_current_cache() -> Iterator[None]:
    fx_module._CURRENT_CACHE.clear()
    yield
    fx_module._CURRENT_CACHE.clear()


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _nbp_payload(code: str, rows: list[tuple[date, float]]) -> dict[str, object]:
    return {
        "table": "A",
        "code": code,
        "rates": [
            {"no": f"{i}/A/NBP/2026", "effectiveDate": d.isoformat(), "mid": mid}
            for i, (d, mid) in enumerate(rows)
        ],
    }


# ─── Parsery ────────────────────────────────────────────────────────────────


def test_parse_nbp_rates_sorts_by_date() -> None:
    data = _nbp_payload("USD", [(FRI, 3.8881), (date(2026, 10, 1), 3.8762)])
    assert parse_nbp_rates(data, "USD") == [(date(2026, 10, 1), 3.8762), (FRI, 3.8881)]


def test_parse_nbp_rates_bad_format_raises() -> None:
    with pytest.raises(FxRateError):
        parse_nbp_rates({"rates": [{"effectiveDate": "2026-10-02"}]}, "USD")


def test_cross_rate_through_pln() -> None:
    # 1 USD = 3,90 PLN, 1 EUR = 4,25 PLN → 1 USD = 0,9176 EUR
    out = cross_rates([(FRI, 3.90)], [(FRI, 4.25)], "nbp")
    assert out == [FxRate(rate=pytest.approx(3.90 / 4.25), rate_date=FRI, source="nbp")]


def test_cross_rate_from_pln_inverts_quote() -> None:
    out = cross_rates(None, [(FRI, 4.0)], "nbp")
    assert out[0].rate == pytest.approx(0.25)


def test_parse_frankfurter_range() -> None:
    data = {
        "amount": 1.0,
        "base": "USD",
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "rates": {"2026-10-01": {"PLN": 3.88}, "2026-10-02": {"PLN": 3.8998}},
    }
    out = parse_frankfurter(data, "PLN")
    assert [fx.rate_date for fx in out] == [date(2026, 10, 1), FRI]
    assert out[-1].rate == pytest.approx(3.8998)
    assert out[-1].source == "frankfurter"


def test_parse_frankfurter_single_day() -> None:
    data = {"amount": 1.0, "base": "USD", "date": "2026-10-02", "rates": {"PLN": 3.8998}}
    assert parse_frankfurter(data, "PLN") == [
        FxRate(rate=3.8998, rate_date=FRI, source="frankfurter")
    ]


# ─── Dni bez notowań ────────────────────────────────────────────────────────


def test_weekend_takes_last_working_day_rate() -> None:
    observations = [FxRate(rate=3.8881, rate_date=FRI, source="nbp")]
    out = fill_days(observations, [SAT, SUN])
    assert out[SAT].rate_date == FRI
    assert out[SUN].rate == 3.8881


def test_day_before_first_publication_has_no_rate() -> None:
    out = fill_days([FxRate(rate=3.9, rate_date=MON, source="nbp")], [SUN, MON])
    assert SUN not in out
    assert out[MON].rate == 3.9


# ─── Providery HTTP ─────────────────────────────────────────────────────────


async def test_nbp_provider_cross_pair_queries_both_currencies() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        code = request.url.path.split("/")[5]
        mid = 3.9 if code == "usd" else 4.25
        return httpx.Response(200, json=_nbp_payload(code.upper(), [(FRI, mid)]))

    out = await NbpProvider(_mock_client(handler)).observations("USD", "EUR", FRI, SUN)
    assert out[0].rate == pytest.approx(3.9 / 4.25)
    assert any("/rates/a/usd/" in path for path in seen)
    assert any("/rates/a/eur/" in path for path in seen)


async def test_nbp_provider_splits_long_ranges_into_93_day_chunks() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(404, text="404 NotFound - Not Found - Brak danych")

    out = await NbpProvider(_mock_client(handler)).observations(
        "USD", "PLN", date(2026, 1, 1), date(2026, 10, 1)
    )
    assert out == []  # „Brak danych” to pusty wynik, nie błąd
    assert len(seen) == 3  # 274 dni → 3 zapytania


async def test_nbp_provider_retries_server_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_nbp_payload("USD", [(FRI, 3.8881)]))

    out = await NbpProvider(_mock_client(handler)).observations("USD", "PLN", FRI, FRI)
    assert calls == 3
    assert out[0].rate == 3.8881


async def test_fallback_uses_frankfurter_when_nbp_has_no_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.nbp.pl":
            return httpx.Response(404, text="Brak danych")
        return httpx.Response(
            200, json={"rates": {"2026-10-02": {"PLN": 3.8998}}, "base": "USD"}
        )

    client = _mock_client(handler)
    provider = FallbackFxProvider(NbpProvider(client), FrankfurterProvider(client))
    out = await provider.observations("USD", "PLN", FRI, FRI)
    assert out == [FxRate(rate=3.8998, rate_date=FRI, source="frankfurter")]


async def test_fallback_raises_when_all_sources_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad"})

    client = _mock_client(handler)
    provider = FallbackFxProvider(NbpProvider(client), FrankfurterProvider(client))
    with pytest.raises(FxRateError):
        await provider.observations("USD", "PLN", FRI, FRI)


# ─── FxService: cache w bazie i w pamięci ───────────────────────────────────


class FakeProvider:
    def __init__(self, observations: list[FxRate]) -> None:
        self._observations = observations
        self.calls: list[tuple[str, str, date, date]] = []

    async def observations(
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxRate]:
        self.calls.append((base, quote, start, end))
        return [o for o in self._observations if start <= o.rate_date <= end]


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, date], FxRate] = {}

    async def get_rates(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]:
        return {d: self.rows[(base, quote, d)] for d in days if (base, quote, d) in self.rows}

    async def save_rates(self, base: str, quote: str, rates: dict[date, FxRate]) -> None:
        for d, fx in rates.items():
            self.rows[(base, quote, d)] = fx


def _service(observations: list[FxRate], today: date = MON) -> tuple[
    FxService, FakeProvider, FakeRepo
]:
    provider = FakeProvider(observations)
    repo = FakeRepo()
    return FxService(provider, repo, today=lambda: today), provider, repo


async def test_same_currency_is_identity_without_requests() -> None:
    svc, provider, _ = _service([])
    out = await svc.rate_on("PLN", "PLN", FRI)
    assert out.rate == 1.0
    assert provider.calls == []


async def test_historical_rate_is_fetched_once_and_stored() -> None:
    svc, provider, repo = _service([FxRate(rate=3.8881, rate_date=FRI, source="nbp")])
    first = await svc.rate_on("USD", "PLN", SAT)
    second = await svc.rate_on("USD", "PLN", SAT)
    assert first == second == FxRate(rate=3.8881, rate_date=FRI, source="nbp")
    assert len(provider.calls) == 1
    assert repo.rows[("USD", "PLN", SAT)].rate_date == FRI


async def test_today_rate_is_cached_in_memory_not_in_database() -> None:
    svc, provider, repo = _service([FxRate(rate=3.9, rate_date=MON, source="nbp")])
    await svc.current("USD", "PLN")
    await svc.current("USD", "PLN")
    assert len(provider.calls) == 1
    assert repo.rows == {}  # kurs dzisiejszy może się jeszcze zmienić


async def test_rates_for_many_days_use_one_provider_call() -> None:
    svc, provider, _ = _service(
        [
            FxRate(rate=4.0, rate_date=date(2026, 9, 1), source="nbp"),
            FxRate(rate=3.9, rate_date=FRI, source="nbp"),
        ]
    )
    out = await svc.rates_on("USD", "PLN", [date(2026, 9, 1), SAT, MON])
    assert out[date(2026, 9, 1)].rate == 4.0
    assert out[SAT].rate == 3.9
    assert out[MON].rate == 3.9  # tabela z poniedziałku jeszcze nieopublikowana
    assert len(provider.calls) == 1


async def test_missing_rate_raises() -> None:
    svc, _, _ = _service([])
    with pytest.raises(FxRateError):
        await svc.rate_on("USD", "PLN", FRI)
