"""Obliczenia dywidend i wyników kwartalnych — wartości oczekiwane policzone ręcznie."""

from datetime import date

import pytest

from src.analysis.dividends import (
    annual_dps,
    dividend_stats,
    dps_cagr,
    frequency_label,
    growth_streak,
    match_quarter_value,
    paying_streak,
    regular_rate,
    surprise_pct,
    ttm_dps,
)
from src.analysis.sources import Bar, parse_finnhub_earnings_history
from src.analysis.xbrl import Fact, quarterly_values


def _quarterly(year: int, amount: float) -> list[tuple[date, float]]:
    return [(date(year, m, 10), amount) for m in (2, 5, 8, 11)]


# Profil zbliżony do Apple: 0,20/kw. w 2021 → +~4% rocznie, start wypłat w 2012 (pół roku).
HISTORY = (
    [(date(2012, 8, 9), 0.095), (date(2012, 11, 7), 0.095)]
    + [d for y in range(2013, 2021) for d in _quarterly(y, 0.10 + 0.01 * (y - 2013))]
    + _quarterly(2021, 0.22)
    + _quarterly(2022, 0.23)
    + _quarterly(2023, 0.24)
    + _quarterly(2024, 0.25)
    + _quarterly(2025, 0.26)
    + [(date(2026, 2, 9), 0.27), (date(2026, 5, 11), 0.27), (date(2026, 8, 10), 0.27)]
)
TODAY = date(2026, 10, 5)


def test_annual_and_ttm_dps() -> None:
    by_year = annual_dps(HISTORY)
    assert by_year[2012] == pytest.approx(0.19)
    assert by_year[2025] == pytest.approx(1.04)
    assert by_year[2026] == pytest.approx(0.81)  # rok niepełny
    # TTM: 10.11.2025 (0,26) + 3 × 0,27 — okno (5.10.2025, 5.10.2026]
    assert ttm_dps(HISTORY, TODAY) == pytest.approx(0.26 + 3 * 0.27)


def test_streaks() -> None:
    by_year = annual_dps(HISTORY)
    # stawka rośnie w każdym roku 2013..2025 (13 lat), wypłaty 2012..2025 (14 lat)
    assert growth_streak(regular_rate(HISTORY), 2025) == 13
    assert paying_streak(by_year, 2025) == 14
    flat = {2023: 1.0, 2024: 1.0, 2025: 1.1}
    assert growth_streak(flat, 2025) == 1  # 2024 = 2023 → przerwa
    assert paying_streak({2025: 1.0}, 2025) == 1
    assert paying_streak({}, 2025) == 0


def test_cagr_matches_hand_calculation() -> None:
    by_year = annual_dps(HISTORY)
    # 3 lata: 0,92 (2022) → 1,04 (2025): (1,04/0,92)^(1/3) − 1 = 4,1714...%
    assert dps_cagr(by_year, 2025, 3) == pytest.approx(4.1714, abs=1e-3)
    # 10 lat: 2015 = 4 × 0,12 = 0,48 → 1,04: (1,04/0,48)^(1/10) − 1 = 8,0387...%
    assert dps_cagr(by_year, 2025, 10) == pytest.approx(8.0387, abs=1e-3)
    assert dps_cagr(by_year, 2025, 20) is None  # brak danych na początku okresu


@pytest.mark.parametrize(
    ("n", "label"),
    [
        (0, None),
        (1, "Rocznie"),
        (2, "Półrocznie"),
        (4, "Kwartalnie"),
        (5, "Kwartalnie"),
        (12, "Miesięcznie"),
        (7, "Nieregularnie"),
    ],
)
def test_frequency_label(n: int, label: str | None) -> None:
    assert frequency_label(n) == label


def test_dividend_stats_full() -> None:
    bars = [Bar(day=date(2025, 12, 1), close=260.0, volume=None)]
    st = dividend_stats(
        HISTORY,
        today=TODAY,
        price=335.0,
        monthly_bars=bars,
        dividends_paid_ttm=15.4e9,
        net_income_ttm=128.9e9,
        fcf_ttm=136.7e9,
        shares=14.6e9,
    )
    assert st is not None
    assert st.dps_ttm == pytest.approx(1.07)
    assert st.yield_ttm == pytest.approx(1.07 / 335 * 100)
    assert st.payout_ratio == pytest.approx(15.4 / 128.9 * 100)
    assert st.fcf_coverage == pytest.approx(136.7 / 15.4)
    assert st.frequency == "Kwartalnie" and st.payments_per_year == 4
    assert st.last_amount == 0.27 and st.last_ex_date == date(2026, 8, 10)
    y2025 = next(y for y in st.years if y.year == 2025)
    assert y2025.yield_pct == pytest.approx(1.04 / 260 * 100)
    assert not y2025.partial
    y2026 = next(y for y in st.years if y.year == 2026)
    assert y2026.partial and y2026.yield_pct is None
    # Brak ceny z danego roku (historia notowań krótsza) → brak stopy, a nie zła stopa
    assert next(y for y in st.years if y.year == 2013).yield_pct is None


def test_dividend_stats_fallback_and_non_payer() -> None:
    st = dividend_stats(
        HISTORY,
        today=TODAY,
        price=None,
        monthly_bars=[],
        dividends_paid_ttm=None,
        net_income_ttm=10.0,
        fcf_ttm=None,
        shares=2.0,
    )
    assert st is not None
    assert st.payout_ratio == pytest.approx(1.07 * 2 / 10 * 100)  # DPS × akcje / zysk
    assert st.yield_ttm is None and st.fcf_coverage is None
    # strata → wskaźnik wypłaty bez sensu
    loss = dividend_stats(
        HISTORY,
        today=TODAY,
        price=1.0,
        monthly_bars=[],
        dividends_paid_ttm=5.0,
        net_income_ttm=-3.0,
        fcf_ttm=1.0,
        shares=None,
    )
    assert loss is not None and loss.payout_ratio is None
    # ostatnia wypłata > 2 lata temu → spółka nie płaci
    old = [(date(2020, 3, 1), 0.5)]
    assert (
        dividend_stats(
            old,
            today=TODAY,
            price=1.0,
            monthly_bars=[],
            dividends_paid_ttm=None,
            net_income_ttm=None,
            fcf_ttm=None,
            shares=None,
        )
        is None
    )


def test_surprise_pct() -> None:
    # (2,02 − 1,89) / 1,89 = 6,878...%
    assert surprise_pct(2.02, 1.89) == pytest.approx(6.8783, abs=1e-3)
    assert surprise_pct(-0.5, -0.4) == pytest.approx(-25.0)  # strata większa niż prognoza
    assert surprise_pct(1.0, 0.0) is None
    assert surprise_pct(None, 1.0) is None


def test_quarterly_values_derive_q4_and_match_period() -> None:
    def f(start: str, end: str, val: float) -> Fact:
        return Fact(date.fromisoformat(start), date.fromisoformat(end), val, date(2026, 1, 1))

    facts = [
        f("2024-09-29", "2024-12-28", 124.3),
        f("2024-12-29", "2025-03-29", 95.4),
        f("2024-09-29", "2025-06-28", 313.7),  # 9 miesięcy narastająco
        f("2024-09-29", "2025-09-27", 416.2),  # rok obrotowy
    ]
    q = quarterly_values(facts)
    assert q[date(2025, 9, 27)] == pytest.approx(416.2 - 313.7)  # Q4 wyprowadzony
    assert q[date(2024, 12, 28)] == 124.3
    # Finnhub: koniec okresu 2025-09-30, spółka: 2025-09-27 → dopasowanie z tolerancją
    assert match_quarter_value(q, date(2025, 9, 30)) == pytest.approx(102.5)
    assert match_quarter_value(q, date(2025, 11, 30)) is None


def test_parse_finnhub_earnings_history() -> None:
    rows = parse_finnhub_earnings_history(
        [
            {"period": "2026-03-31", "actual": 2.01, "estimate": 1.95, "quarter": 2, "year": 2026},
            {"period": "2026-06-30", "actual": 1.91, "estimate": None, "quarter": 3, "year": 2026},
            {"bad": True},
        ]
    )
    assert [r.period for r in rows] == [date(2026, 6, 30), date(2026, 3, 31)]
    assert rows[0].eps_estimate is None and rows[1].fiscal_quarter == "Q2 2026"


def test_utc_day_handles_pre_1970_timestamps() -> None:
    from src.analysis.sources import utc_day

    assert utc_day(0) == date(1970, 1, 1)
    assert utc_day(-86400 * 365) == date(1969, 1, 1)  # Windows: fromtimestamp → OSError
    assert utc_day(1786368600) == date(2026, 8, 10)


def test_growth_streak_ignores_extra_payment_in_year() -> None:
    # Coca-Cola 2001 wg Yahoo: 5 wypłat (suma 0,54 > 0,40 w 2002) — stawka jednak rosła.
    divs = (
        [(date(2000, m, 1), 0.085) for m in (3, 6, 9, 12)]
        + [
            (date(2001, m, 1), a)
            for m, a in ((3, 0.09), (6, 0.09), (8, 0.18), (9, 0.09), (12, 0.09))
        ]
        + [(date(2002, m, 1), 0.10) for m in (3, 6, 9, 12)]
    )
    assert annual_dps(divs)[2001] > annual_dps(divs)[2002]  # suma myli
    assert regular_rate(divs) == {2000: 0.085, 2001: 0.09, 2002: 0.10}
    assert growth_streak(annual_dps(divs), 2002) == 0  # suma: fałszywa przerwa
    assert growth_streak(regular_rate(divs), 2002) == 2


def test_regular_rate_uses_year_end_rate_and_skips_special() -> None:
    # Microsoft 2009–2010: podwyżka 0,13 → 0,16 dopiero od wypłaty listopadowej
    msft = [(date(2009, m, 15), 0.13) for m in (2, 5, 8, 11)] + [
        (date(2010, m, 15), a) for m, a in ((2, 0.13), (5, 0.13), (8, 0.13), (11, 0.16))
    ]
    assert regular_rate(msft) == {2009: 0.13, 2010: 0.16}
    assert growth_streak(regular_rate(msft), 2010) == 1
    # Dodatkowa wypłata specjalna krótko po regularnej nie podbija stawki
    special = [(date(2024, m, 1), 0.5) for m in (3, 6, 9, 12)] + [(date(2024, 12, 20), 3.0)]
    assert regular_rate(special) == {2024: 0.5}
    # Duża podwyżka w zwykłym rytmie to podwyżka, nie wypłata specjalna (NVIDIA 2026)
    nvda = [(date(2026, 3, 11), 0.01), (date(2026, 6, 4), 0.25), (date(2026, 9, 10), 0.25)]
    assert regular_rate(nvda) == {2026: 0.25}


def test_indicated_annual() -> None:
    from src.analysis.dividends import indicated_annual

    # NVIDIA 2026: podwyżka 0,01 → 0,25 — stawka wskazana 4 × 0,25 (TTM to tylko 0,52)
    nvda = [
        (date(2025, 12, 4), 0.01),
        (date(2026, 3, 11), 0.01),
        (date(2026, 6, 4), 0.25),
        (date(2026, 9, 10), 0.25),
    ]
    assert indicated_annual(nvda, "Kwartalnie") == pytest.approx(1.0)
    # wypłata specjalna (dodatkowa, 20 dni po regularnej) nie zawyża stawki
    special = [(date(2026, m, 1), 0.5) for m in (1, 4, 7)] + [(date(2026, 7, 21), 3.0)]
    assert indicated_annual(special, "Kwartalnie") == pytest.approx(2.0)
    assert indicated_annual(nvda, "Nieregularnie") is None
    assert indicated_annual([], "Kwartalnie") is None
