from datetime import date, timedelta

import pytest

from src.marketdata.fx import FxRate, FxRateError
from src.marketdata.historical import HistoricalPrice, HistoricalPriceError
from src.services.portfolio_history import PortfolioHistoryService

ASSET_BTC = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "ticker": "BTC",
    "name": "Bitcoin",
    "asset_type": "crypto",
    "currency": "USD",
}
ASSET_AAPL = {
    "id": "aaaaaaaa-0000-0000-0000-000000000002",
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "asset_type": "stock",
    "currency": "USD",
}
POSITION_BTC = "eeeeeeee-0000-0000-0000-000000000001"
POSITION_AAPL = "eeeeeeee-0000-0000-0000-000000000002"

TODAY = date.today()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


class FakePortfolioRepo:
    def __init__(self, positions: list[dict], transactions: list[dict]) -> None:  # type: ignore[type-arg]
        self._positions = positions
        self._transactions = transactions

    async def list_positions(self) -> list[dict]:  # type: ignore[type-arg]
        return self._positions

    async def list_all_transactions(self) -> list[dict]:  # type: ignore[type-arg]
        return self._transactions


class FakePrices:
    def __init__(self, series: dict[str, list[HistoricalPrice]]) -> None:
        self._series = series
        self.calls: list[tuple[str, str, int]] = []

    async def price_series(self, ticker: str, asset_type: str, days: int) -> list[HistoricalPrice]:
        self.calls.append((ticker, asset_type, days))
        if ticker not in self._series:
            raise HistoricalPriceError(f"brak notowań dla {ticker}")
        return self._series[ticker]


def flat_series(price: float, days: int, source: str = "bybit") -> list[HistoricalPrice]:
    return [
        HistoricalPrice(price=price, price_date=days_ago(n), source=source)
        for n in reversed(range(days))
    ]


class FakeFx:
    """Kurs per para jako funkcja dnia; brak pary = FxRateError."""

    def __init__(self, rates: dict[tuple[str, str], dict[date, float]] | None = None) -> None:
        self._rates = rates or {}

    async def rate_on(self, base: str, quote: str, on: date) -> FxRate:
        return (await self.rates_on(base, quote, [on]))[on]

    async def rates_on(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]:
        if base == quote:
            return {d: FxRate(rate=1.0, rate_date=d, source="identity") for d in days}
        if (base, quote) not in self._rates:
            raise FxRateError(f"brak {base}/{quote}")
        table = self._rates[(base, quote)]
        return {d: FxRate(rate=table[d], rate_date=d, source="nbp") for d in days if d in table}


class FakeSettings:
    def __init__(self, base_currency: str = "USD") -> None:
        self._base = base_currency

    async def get(self) -> dict:  # type: ignore[type-arg]
        return {"base_currency": self._base}


def make_service(
    positions: list[dict],  # type: ignore[type-arg]
    transactions: list[dict],  # type: ignore[type-arg]
    series: dict[str, list[HistoricalPrice]],
    fx: FakeFx | None = None,
    base: str = "USD",
) -> tuple[PortfolioHistoryService, FakePrices]:
    prices = FakePrices(series)
    return PortfolioHistoryService(
        portfolio=FakePortfolioRepo(positions, transactions),
        prices=prices,
        fx=fx or FakeFx(),
        settings=FakeSettings(base),
    ), prices


async def test_empty_portfolio_returns_no_points() -> None:
    svc, _ = make_service([], [], {})
    out = await svc.history(30)
    assert out.points == []
    assert out.skipped_tickers == []


async def test_series_starts_at_first_purchase_not_at_window_start() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(3).isoformat(),
            }
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    assert [p.point_date for p in out.points] == [days_ago(n) for n in (3, 2, 1, 0)]
    assert out.points[0].value == pytest.approx(60000.0)
    assert out.points[0].cost == pytest.approx(50000.0)


async def test_later_purchase_raises_value_and_cost_from_its_day() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 2, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(4).isoformat(),
            },
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 55000.0,
                "purchased_at": days_ago(2).isoformat(),
            },
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    by_date = {p.point_date: p for p in out.points}
    assert by_date[days_ago(3)].value == pytest.approx(60000.0)
    assert by_date[days_ago(3)].cost == pytest.approx(50000.0)
    assert by_date[days_ago(2)].value == pytest.approx(120000.0)
    assert by_date[days_ago(2)].cost == pytest.approx(105000.0)


async def test_missing_quote_is_carried_forward_from_last_trading_day() -> None:
    svc, _ = make_service(
        [{"id": POSITION_AAPL, "quantity": 10, "assets": ASSET_AAPL}],
        [
            {
                "position_id": POSITION_AAPL,
                "quantity": 10,
                "price": 200.0,
                "purchased_at": days_ago(3).isoformat(),
            }
        ],
        {
            "AAPL": [
                HistoricalPrice(price=210.0, price_date=days_ago(3), source="stooq"),
                HistoricalPrice(price=220.0, price_date=days_ago(1), source="stooq"),
            ]
        },
    )
    out = await svc.history(30)
    by_date = {p.point_date: p for p in out.points}
    assert by_date[days_ago(2)].value == pytest.approx(2100.0)
    assert by_date[days_ago(0)].value == pytest.approx(2200.0)


async def test_transaction_without_price_counts_in_value_but_not_in_cost() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 2, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(2).isoformat(),
            },
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": None,
                "purchased_at": days_ago(2).isoformat(),
            },
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    assert out.points[-1].value == pytest.approx(120000.0)
    assert out.points[-1].cost == pytest.approx(50000.0)


async def test_asset_without_quotes_is_skipped_and_reported() -> None:
    svc, _ = make_service(
        [
            {"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC},
            {"id": POSITION_AAPL, "quantity": 10, "assets": ASSET_AAPL},
        ],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(2).isoformat(),
            },
            {
                "position_id": POSITION_AAPL,
                "quantity": 10,
                "price": 200.0,
                "purchased_at": days_ago(2).isoformat(),
            },
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    assert out.skipped_tickers == ["AAPL"]
    assert out.points[-1].value == pytest.approx(60000.0)
    assert out.points[-1].cost == pytest.approx(50000.0)


async def test_no_asset_has_quotes_returns_no_points() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(2).isoformat(),
            }
        ],
        {},
    )
    out = await svc.history(30)
    assert out.points == []
    assert out.skipped_tickers == ["BTC"]


async def test_purchase_older_than_window_starts_at_window_edge() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(90).isoformat(),
            }
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    assert len(out.points) == 30
    assert out.points[0].point_date == days_ago(29)
    assert out.points[0].cost == pytest.approx(50000.0)


async def test_position_without_transactions_yields_no_points() -> None:
    svc, _ = make_service(
        [{"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC}],
        [],
        {"BTC": flat_series(60000.0, 30)},
    )
    out = await svc.history(30)
    assert out.points == []


async def test_each_asset_is_queried_once_per_request() -> None:
    svc, prices = make_service(
        [{"id": POSITION_BTC, "quantity": 2, "assets": ASSET_BTC}],
        [
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 50000.0,
                "purchased_at": days_ago(4).isoformat(),
            },
            {
                "position_id": POSITION_BTC,
                "quantity": 1,
                "price": 55000.0,
                "purchased_at": days_ago(2).isoformat(),
            },
        ],
        {"BTC": flat_series(60000.0, 30)},
    )
    await svc.history(30)
    assert prices.calls == [("BTC", "crypto", 30)]


# ─── Waluta bazowa: kurs z danego dnia ───────────────────────────────────────


def daily_rates(values: dict[int, float], days: int = 40) -> dict[date, float]:
    """Kurs na każdy dzień: wartości z `values` (dni temu → kurs), pozostałe dni dziedziczą
    ostatni wcześniejszy kurs (tak jak FxService dla weekendów)."""
    out: dict[date, float] = {}
    last = values[max(values)]
    for n in reversed(range(days)):
        last = values.get(n, last)
        out[days_ago(n)] = last
    return out


async def test_each_point_uses_rate_from_its_own_day() -> None:
    rates = daily_rates({3: 4.0, 2: 4.0, 1: 3.8, 0: 3.9})
    svc, _ = make_service(
        [{"id": POSITION_AAPL, "quantity": 10, "assets": ASSET_AAPL}],
        [
            {
                "position_id": POSITION_AAPL,
                "quantity": 10,
                "price": 200.0,
                "fx_rate": 1,
                "purchased_at": days_ago(3).isoformat(),
            }
        ],
        {"AAPL": flat_series(210.0, 30, source="yahoo")},
        fx=FakeFx({("USD", "PLN"): rates}),
        base="PLN",
    )
    out = await svc.history(30)
    by_date = {p.point_date: p for p in out.points}
    assert out.base_currency == "PLN"
    assert by_date[days_ago(3)].value == pytest.approx(10 * 210.0 * 4.0)
    assert by_date[days_ago(1)].value == pytest.approx(10 * 210.0 * 3.8)
    assert by_date[days_ago(0)].value == pytest.approx(10 * 210.0 * 3.9)
    # koszt po kursie z dnia zakupu — nie zmienia się razem z kursem
    assert all(p.cost == pytest.approx(10 * 200.0 * 4.0) for p in out.points)
    assert out.fx_rate_date == TODAY
    assert out.fx_sources == ["nbp"]


async def test_transaction_currency_rate_applies_to_cost() -> None:
    """Zakup za EUR: fx_rate (EUR→USD z dnia zakupu) × kurs USD→PLN z tego dnia."""
    svc, _ = make_service(
        [{"id": POSITION_AAPL, "quantity": 1, "assets": ASSET_AAPL}],
        [
            {
                "position_id": POSITION_AAPL,
                "quantity": 1,
                "price": 180.0,  # EUR
                "fx_rate": 1.1,
                "purchased_at": days_ago(2).isoformat(),
            }
        ],
        {"AAPL": flat_series(210.0, 30, source="yahoo")},
        fx=FakeFx({("USD", "PLN"): daily_rates({2: 4.0, 0: 3.9})}),
        base="PLN",
    )
    out = await svc.history(30)
    assert out.points[0].cost == pytest.approx(180.0 * 1.1 * 4.0)


async def test_asset_without_fx_rates_is_skipped_not_summed_in_wrong_currency() -> None:
    svc, _ = make_service(
        [
            {"id": POSITION_BTC, "quantity": 1, "assets": ASSET_BTC},
            {"id": POSITION_AAPL, "quantity": 1,
             "assets": {**ASSET_AAPL, "currency": "CHF"}},
        ],
        [
            {"position_id": POSITION_BTC, "quantity": 1, "price": 100.0,
             "purchased_at": days_ago(2).isoformat()},
            {"position_id": POSITION_AAPL, "quantity": 1, "price": 100.0,
             "purchased_at": days_ago(2).isoformat()},
        ],
        {"BTC": flat_series(110.0, 30), "AAPL": flat_series(210.0, 30)},
        fx=FakeFx({("USD", "PLN"): daily_rates({2: 4.0})}),
        base="PLN",
    )
    out = await svc.history(30)
    assert out.skipped_tickers == ["AAPL"]
    assert out.points[-1].value == pytest.approx(110.0 * 4.0)
