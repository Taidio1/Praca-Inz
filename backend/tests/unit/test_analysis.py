from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest

from src.analysis import service as analysis_service
from src.analysis.metrics import compute_metrics, peer_median
from src.analysis.prices import beta, period_returns
from src.analysis.service import CompanyAnalysisService
from src.analysis.sources import (
    AnalysisSourceError,
    Bar,
    EarningsDate,
    EarningsResult,
    FinnhubProfile,
    PriceHistory,
    SecProfile,
    SecTicker,
    clean_company_name,
    parse_finnhub_earnings,
    parse_finnhub_profile,
    parse_sec_tickers,
    parse_yahoo_chart,
)
from src.analysis.xbrl import Fundamentals, parse_companyfacts, split_adjusted
from src.core.errors import NotFoundError


@pytest.fixture(autouse=True)
def _clear_analysis_cache() -> Iterator[None]:
    analysis_service.clear_cache()
    yield
    analysis_service.clear_cache()


def _row(
    start: str | None, end: str, val: float, form: str = "10-Q", filed: str = "2026-01-01"
) -> dict[str, Any]:
    row: dict[str, Any] = {"end": end, "val": val, "form": form, "filed": filed}
    if start:
        row["start"] = start
    return row


def _facts(concepts: dict[str, list[dict[str, Any]]], shares: float = 100.0) -> dict[str, Any]:
    return {
        "entityName": "Test Corp",
        "facts": {
            "us-gaap": {k: {"units": {"USD": v}} for k, v in concepts.items()},
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_row(None, "2025-07-15", shares, filed="2025-08-01")]}
                }
            },
        },
    }


REVENUE = [
    _row("2023-01-01", "2023-12-31", 1000, "10-K"),
    _row("2024-01-01", "2024-12-31", 1200, "10-K"),
    _row("2024-01-01", "2024-06-30", 500),  # YTD sprzed roku
    _row("2025-01-01", "2025-06-30", 700),  # bieżący YTD
    _row("2025-04-01", "2025-06-30", 380),  # sam kwartał — ignorowany przy TTM
]


def test_ttm_is_last_annual_plus_ytd_minus_prior_ytd() -> None:
    fin = parse_companyfacts(_facts({"Revenues": REVENUE}))
    assert fin.as_of == date(2025, 6, 30)
    assert fin.ttm.revenue == 1200 + 700 - 500
    assert {y: f.revenue for y, f in fin.annual.items()} == {2023: 1000, 2024: 1200}


def test_concept_priority_and_abandoned_concept() -> None:
    old = [_row("2018-01-01", "2018-12-31", 50, "10-K")]
    fin = parse_companyfacts(
        _facts(
            {
                "SalesRevenueNet": old,
                "RevenueFromContractWithCustomerExcludingAssessedTax": REVENUE,
            }
        )
    )
    assert fin.ttm.revenue == 1400
    assert fin.annual[2018].revenue == 50  # historia porzuconego konceptu zachowana


def test_stale_flow_gives_none() -> None:
    interest = [_row("2021-01-01", "2021-12-31", 10, "10-K")]
    fin = parse_companyfacts(_facts({"Revenues": REVENUE, "InterestExpense": interest}))
    assert fin.ttm.interest_expense is None


def test_instants_debt_and_fcf() -> None:
    fin = parse_companyfacts(
        _facts(
            {
                "Revenues": REVENUE,
                "NetCashProvidedByUsedInOperatingActivities": [
                    _row("2024-01-01", "2024-12-31", 300, "10-K")
                ],
                "PaymentsToAcquirePropertyPlantAndEquipment": [
                    _row("2024-01-01", "2024-12-31", 100, "10-K")
                ],
                "LongTermDebtNoncurrent": [_row(None, "2025-06-30", 80)],
                "LongTermDebtCurrent": [_row(None, "2025-06-30", 20)],
                "CommercialPaper": [_row(None, "2025-06-30", 5)],
            }
        )
    )
    assert fin.ttm.debt == 105
    assert fin.ttm.fcf == 200
    assert fin.ttm.shares == 100


def test_compute_metrics_and_negative_earnings() -> None:
    f = Fundamentals(
        revenue=1000,
        gross_profit=400,
        net_income=100,
        equity=500,
        shares=10,
        debt=200,
        cash=50,
        operating_income=150,
        ebitda=200,
    )
    m = compute_metrics(f, price=50)  # kapitalizacja 500
    assert m["pe"] == pytest.approx(5.0)
    assert m["ps"] == pytest.approx(0.5)
    assert m["gross_margin"] == pytest.approx(40.0)
    assert m["ev_ebitda"] == pytest.approx((500 + 200 - 50) / 200)
    assert m["debt_equity"] == pytest.approx(0.4)
    assert compute_metrics(Fundamentals(net_income=-5, shares=10), price=50)["pe"] is None


def test_split_adjustment_only_for_later_splits() -> None:
    f = Fundamentals(shares=100, shares_filed=date(2024, 3, 1))
    splits = [(date(2021, 7, 1), 4.0), (date(2024, 6, 10), 10.0)]
    assert split_adjusted(f, splits).shares == 1000


def test_peer_median_needs_two_values() -> None:
    assert peer_median([None, 3.0]) is None
    assert peer_median([1.0, 3.0, None, 10.0]) == 3.0


def _bars(start: date, closes: list[float]) -> list[Bar]:
    return [Bar(day=start + timedelta(days=i), close=c, volume=1.0) for i, c in enumerate(closes)]


def test_period_returns_and_short_history() -> None:
    bars = _bars(date(2026, 1, 1), [100.0] * 30 + [110.0])
    r = period_returns(bars, bars[-1].day)
    assert r["1M"] == pytest.approx(10.0)
    assert r["1Y"] is None


def test_beta_of_series_against_itself_is_one() -> None:
    closes = [100 + 10 * ((i * 37) % 11) + i * 0.1 for i in range(400)]
    bars = _bars(date(2024, 1, 1), closes)
    assert beta(bars, bars) == pytest.approx(1.0)


def test_parse_yahoo_chart_dividends_and_splits() -> None:
    data = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "regularMarketPrice": 12.0,
                        "longName": "Test Inc.",
                    },
                    "timestamp": [1704067200, 1704153600, 1704240000],
                    "indicators": {"quote": [{"close": [10.0, None, 11.0], "volume": [5, 5, 5]}]},
                    "events": {
                        "dividends": {"1": {"date": 1704153600, "amount": 0.25}},
                        "splits": {"2": {"date": 1704240000, "numerator": 4, "denominator": 1}},
                    },
                }
            ]
        }
    }
    ph = parse_yahoo_chart(data, "TEST")
    assert [b.close for b in ph.bars] == [10.0, 11.0]
    assert ph.price == 12.0 and ph.previous_close == 10.0
    assert ph.dividends == [(date(2024, 1, 2), 0.25)]
    assert ph.splits == [(date(2024, 1, 3), 4.0)]


def test_clean_company_name_and_tickers() -> None:
    assert clean_company_name("Apple Inc.") == "Apple"
    assert clean_company_name("NVIDIA CORP") == "NVIDIA"
    t = parse_sec_tickers({"0": {"cik_str": 1, "ticker": "aaa", "title": "A"}, "1": {"bad": 1}})
    assert t == {"AAA": SecTicker("AAA", 1, "A", 0)}


class _FakeSec:
    async def tickers(self) -> dict[str, SecTicker]:
        return {
            "AAPL": SecTicker("AAPL", 320193, "Apple Inc.", 1),
            "APLE": SecTicker("APLE", 2, "Apple Hospitality REIT", 50),
            "BRK-B": SecTicker("BRK-B", 3, "Berkshire", 5),
        }

    async def companyfacts(self, cik: int) -> dict[str, Any]:
        return _facts(
            {
                "Revenues": REVENUE,
                "NetIncomeLoss": [_row("2024-01-01", "2024-12-31", 120, "10-K")],
            }
        )

    async def submissions(self, cik: int) -> SecProfile:
        return SecProfile(
            "Apple Inc.", "3571", "Electronic Computers", "Technology", ["Nasdaq"], "0926", "CA", []
        )


class _FakeYahoo:
    async def history(self, ticker: str, range_: str = "10y") -> PriceHistory:
        return PriceHistory(
            currency="USD",
            long_name=None,
            exchange="NasdaqGS",
            price=20.0,
            previous_close=19.0,
            bars=_bars(date(2025, 6, 1), [19.0, 20.0]),
        )

    async def long_history(self, ticker: str) -> PriceHistory:
        # 2 lata kwartalnych dywidend; ceny miesięczne pod stopę roczną
        divs = [(date(2024, m, 10), 0.25) for m in (2, 5, 8, 11)] + [
            (date(2025, m, 10), 0.26) for m in (2, 5)
        ]
        return PriceHistory(
            currency="USD",
            long_name=None,
            exchange=None,
            price=20.0,
            previous_close=None,
            bars=_bars(date(2024, 12, 1), [25.0]),
            dividends=divs,
        )


class _FakeWiki:
    async def summary(self, name: str) -> None:
        return None


def _service() -> CompanyAnalysisService:
    return CompanyAnalysisService(_FakeSec(), _FakeYahoo(), _FakeWiki())  # type: ignore[arg-type]


async def test_search_ranks_exact_ticker_then_size() -> None:
    hits = await _service().search("apple")
    assert [h.ticker for h in hits] == ["AAPL", "APLE"]
    assert (await _service().search("aapl"))[0].ticker == "AAPL"


async def test_overview_assembles_metrics() -> None:
    o = await _service().overview("aapl")
    assert o.ticker == "AAPL" and o.sector == "Technology"
    assert o.market_cap == 2000.0
    pe = next(m for m in o.metrics if m.key == "pe")
    assert pe.value == pytest.approx(2000 / 120)
    assert o.change == pytest.approx(1.0)


async def test_overview_dot_ticker_and_unknown() -> None:
    assert (await _service().overview("BRK.B")).ticker == "BRK-B"
    with pytest.raises(NotFoundError):
        await _service().overview("ZZZZ")


# ─── Finnhub ─────────────────────────────────────────────────────────────────


def test_parse_finnhub_profile_and_unknown_symbol() -> None:
    p = parse_finnhub_profile(
        {
            "ticker": "AAPL",
            "name": "Apple Inc",
            "logo": "https://x/AAPL.png",
            "weburl": "https://www.apple.com/",
            "finnhubIndustry": "Technology",
            "ipo": "1980-12-12",
        }
    )
    assert p is not None and p.logo_url == "https://x/AAPL.png" and p.ipo == date(1980, 12, 12)
    assert parse_finnhub_profile({}) is None


def test_parse_finnhub_earnings_takes_nearest_future() -> None:
    data = {
        "earningsCalendar": [
            {"date": "2027-01-27", "hour": "", "quarter": 1, "year": 2027},
            {"date": "2026-10-29", "hour": "amc", "quarter": 4, "year": 2026},
            {"date": "2026-07-30", "hour": "amc", "quarter": 3, "year": 2026},
        ]
    }
    e = parse_finnhub_earnings(data, today=date(2026, 10, 5))
    assert e == EarningsDate(day=date(2026, 10, 29), hour="amc", fiscal_quarter="Q4 2026")
    assert parse_finnhub_earnings({"earningsCalendar": []}, date(2026, 1, 1)) is None


class _FakeFinnhub:
    enabled = True

    async def profile(self, ticker: str) -> FinnhubProfile:
        return FinnhubProfile(
            "Apple Inc", "https://x/logo.png", "https://apple.com", "Tech", None, "US"
        )

    async def peers(self, ticker: str) -> list[str]:
        return ["BRK-B", "ZZZZ", "AAPL", "APLE"]  # ZZZZ spoza SEC, AAPL = sama spółka

    async def next_earnings(self, ticker: str, today: date) -> EarningsDate:
        return EarningsDate(date(2026, 10, 29), "amc", "Q4 2026")

    async def earnings_history(self, ticker: str) -> list[EarningsResult]:
        return [EarningsResult(date(2025, 6, 30), "Q2 2025", 2.02, 1.89)]


class _BrokenFinnhub(_FakeFinnhub):
    async def profile(self, ticker: str) -> FinnhubProfile:
        raise AnalysisSourceError("HTTP 429")


def _fh_service(fh: object) -> CompanyAnalysisService:
    return CompanyAnalysisService(_FakeSec(), _FakeYahoo(), _FakeWiki(), fh)  # type: ignore[arg-type]


async def test_overview_uses_finnhub_and_peers_fallback() -> None:
    o = await _fh_service(_FakeFinnhub()).overview("AAPL")
    assert o.logo_url == "https://x/logo.png" and o.website == "https://apple.com"
    assert o.next_earnings is not None and o.next_earnings.d == date(2026, 10, 29)
    # AAPL jest w ręcznej grupie (peers z universe), więc Finnhub peers nie są użyte
    assert "MSFT" in o.peers


async def test_finnhub_peers_for_company_outside_universe() -> None:
    o = await _fh_service(_FakeFinnhub()).overview("APLE")
    assert o.peers == ["BRK-B", "AAPL"]
    assert o.peer_group == "branża wg Finnhub"


async def test_finnhub_failure_does_not_break_overview() -> None:
    o = await _fh_service(_BrokenFinnhub()).overview("AAPL")
    assert o.logo_url is None and o.next_earnings is not None


def test_stale_cover_share_count_falls_back_to_diluted() -> None:
    # Spółka z kilkoma klasami akcji: dei z 2010 r., aktualna liczba tylko jako rozwodniona średnia.
    data = _facts({"Revenues": REVENUE})
    data["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"] = [
        _row(None, "2010-01-27", 469.0, filed="2010-01-28")
    ]
    data["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"] = {
        "units": {
            "shares": [
                _row("2024-01-01", "2024-12-31", 1900.0, "10-K", filed="2025-02-01"),
                _row("2025-04-01", "2025-06-30", 1950.0, filed="2025-07-30"),
            ]
        }
    }
    fin = parse_companyfacts(data)
    assert fin.ttm.shares == 1950.0
    assert fin.ttm.shares_filed == date(2025, 7, 30)


def test_debt_including_current_maturities_concept() -> None:
    fin = parse_companyfacts(
        _facts(
            {
                "Revenues": REVENUE,
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": [
                    _row(None, "2025-06-30", 36.0)
                ],
                "ShortTermBorrowings": [_row(None, "2025-06-30", 0.4)],
            }
        )
    )
    assert fin.ttm.debt == pytest.approx(36.4)


def test_with_finnhub_shares_only_fills_missing() -> None:
    from src.analysis.service import with_finnhub_shares
    from src.analysis.xbrl import CompanyFinancials

    fin = CompanyFinancials("X", date(2026, 3, 31), Fundamentals(net_income=10.0), {}, {})
    prof = FinnhubProfile("X", None, None, None, None, "US", shares_outstanding=2e9)
    filled, used = with_finnhub_shares(fin, prof)
    assert (
        used and filled.ttm.shares == 2e9 and fin.ttm.shares is None
    )  # oryginał (cache) nietknięty
    fin.ttm.shares = 5.0
    assert with_finnhub_shares(fin, prof) == (fin, False)


async def test_overview_builds_dividends_and_earnings_rows() -> None:
    o = await _fh_service(_FakeFinnhub()).overview("AAPL")
    assert o.earnings_history[0].surprise_pct == pytest.approx((2.02 - 1.89) / 1.89 * 100)
    # przychód kwartału 2025-04-01..2025-06-30 = 380 dopasowany do okresu Finnhub
    assert o.earnings_history[0].revenue_actual == 380
    assert o.dividends is not None
    # dziś = 2.06.2025 (ostatnia sesja); wypłaty w oknie: 08.24, 11.24, 02.25, 05.25
    assert o.dividends.dps_ttm == pytest.approx(0.25 + 0.25 + 0.26 + 0.26)
    assert o.dividends.paying_streak == 1 and o.dividends.history_from == 2024
