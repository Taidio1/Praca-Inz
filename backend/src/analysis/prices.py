"""Statystyki z dziennych notowań: stopy zwrotu, beta, cena na dzień. Czyste funkcje."""

from bisect import bisect_right
from datetime import date, timedelta

from src.analysis.sources import Bar

RETURN_WINDOWS: dict[str, int] = {"1M": 30, "3M": 91, "1Y": 365, "5Y": 1826}


def close_on_or_before(bars: list[Bar], day: date) -> float | None:
    idx = bisect_right([b.day for b in bars], day) - 1
    return bars[idx].close if idx >= 0 else None


def period_returns(bars: list[Bar], today: date) -> dict[str, float | None]:
    if not bars:
        return {k: None for k in [*RETURN_WINDOWS, "YTD"]}
    last = bars[-1].close
    out: dict[str, float | None] = {}

    def ret(since: date) -> float | None:
        if bars[0].day > since + timedelta(days=7):  # historia za krótka
            return None
        base = close_on_or_before(bars, since) or bars[0].close
        return (last / base - 1) * 100 if base else None

    for key, days in RETURN_WINDOWS.items():
        out[key] = ret(today - timedelta(days=days))
    out["YTD"] = ret(date(today.year, 1, 1) - timedelta(days=1))
    return {k: out[k] for k in ["1M", "3M", "YTD", "1Y", "5Y"]}


def beta(bars: list[Bar], benchmark: list[Bar], min_points: int = 120) -> float | None:
    """Beta z tygodniowych stóp zwrotu (mniej szumu niż dzienne, różne święta giełd)."""
    bench = {b.day: b.close for b in benchmark}
    common = [(b.close, bench[b.day]) for b in bars if b.day in bench]
    weekly = common[::5]
    rs = [
        (a2 / a1 - 1, b2 / b1 - 1) for (a1, b1), (a2, b2) in zip(weekly, weekly[1:], strict=False)
    ]
    if len(rs) < min_points // 5:
        return None
    mean_a = sum(r[0] for r in rs) / len(rs)
    mean_b = sum(r[1] for r in rs) / len(rs)
    cov = sum((a - mean_a) * (b - mean_b) for a, b in rs)
    var = sum((b - mean_b) ** 2 for _, b in rs)
    return cov / var if var else None


def avg_daily_turnover(bars: list[Bar]) -> float | None:
    vals = [b.close * b.volume for b in bars if b.volume]
    return sum(vals) / len(vals) if vals else None
