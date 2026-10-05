"""Wskaźniki fundamentalne liczone z `Fundamentals` + ceny. Czyste funkcje, bez I/O.

Kierunek `better` służy wyłącznie do kolorowania porównań (wyżej/niżej niż punkt
odniesienia) — system nie wydaje ocen inwestycyjnych.
"""

from collections.abc import Callable
from dataclasses import dataclass
from statistics import median
from typing import Literal

from src.analysis.xbrl import Fundamentals

Fmt = Literal["x", "pct", "usd"]
Better = Literal["low", "high"]


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    group: str
    fmt: Fmt
    better: Better
    fn: Callable[[Fundamentals, float | None], float | None]


def _div(a: float | None, b: float | None, *, positive_b: bool = True) -> float | None:
    if a is None or b is None or b == 0 or (positive_b and b < 0):
        return None
    return a / b


def _pct(a: float | None, b: float | None) -> float | None:
    r = _div(a, b)
    return r * 100 if r is not None else None


def market_cap(f: Fundamentals, price: float | None) -> float | None:
    if price is None or f.shares is None:
        return None
    return price * f.shares


def enterprise_value(f: Fundamentals, price: float | None) -> float | None:
    mcap = market_cap(f, price)
    if mcap is None:
        return None
    return mcap + (f.debt or 0.0) - (f.cash or 0.0)


def _fcf_ps(f: Fundamentals, _: float | None) -> float | None:
    return _div(f.fcf, f.shares)


def _quick(f: Fundamentals, _: float | None) -> float | None:
    if f.current_assets is None:
        return None
    return _div(f.current_assets - (f.inventory or 0.0), f.current_liabilities)


METRICS: list[MetricDef] = [
    # Wycena — mnożnik ujemny (strata) nie ma sensu porównawczego → None
    MetricDef(
        "pe", "P/E TTM", "valuation", "x", "low", lambda f, p: _div(market_cap(f, p), f.net_income)
    ),
    MetricDef(
        "ps", "P/S TTM", "valuation", "x", "low", lambda f, p: _div(market_cap(f, p), f.revenue)
    ),
    MetricDef("pb", "P/B", "valuation", "x", "low", lambda f, p: _div(market_cap(f, p), f.equity)),
    MetricDef(
        "pfcf", "P/FCF TTM", "valuation", "x", "low", lambda f, p: _div(market_cap(f, p), f.fcf)
    ),
    MetricDef(
        "pocf", "P/OCF TTM", "valuation", "x", "low", lambda f, p: _div(market_cap(f, p), f.ocf)
    ),
    MetricDef(
        "ev_ebitda",
        "EV/EBITDA",
        "valuation",
        "x",
        "low",
        lambda f, p: _div(enterprise_value(f, p), f.ebitda),
    ),
    # Rentowność
    MetricDef(
        "gross_margin",
        "Marża brutto",
        "profitability",
        "pct",
        "high",
        lambda f, _: _pct(f.gross_profit, f.revenue),
    ),
    MetricDef(
        "operating_margin",
        "Marża operacyjna",
        "profitability",
        "pct",
        "high",
        lambda f, _: _pct(f.operating_income, f.revenue),
    ),
    MetricDef(
        "ebitda_margin",
        "Marża EBITDA",
        "profitability",
        "pct",
        "high",
        lambda f, _: _pct(f.ebitda, f.revenue),
    ),
    MetricDef(
        "net_margin",
        "Marża netto",
        "profitability",
        "pct",
        "high",
        lambda f, _: _pct(f.net_income, f.revenue),
    ),
    MetricDef(
        "roe", "ROE", "profitability", "pct", "high", lambda f, _: _pct(f.net_income, f.equity)
    ),
    # Przepływy pieniężne
    MetricDef(
        "ocf_sales",
        "OCF / sprzedaż",
        "cashflow",
        "pct",
        "high",
        lambda f, _: _pct(f.ocf, f.revenue),
    ),
    MetricDef("fcf_ocf", "FCF / OCF", "cashflow", "pct", "high", lambda f, _: _pct(f.fcf, f.ocf)),
    MetricDef("fcf_ps", "FCF na akcję", "cashflow", "usd", "high", _fcf_ps),
    MetricDef(
        "ocf_ps", "OCF na akcję", "cashflow", "usd", "high", lambda f, _: _div(f.ocf, f.shares)
    ),
    MetricDef(
        "fcf_yield",
        "FCF yield",
        "cashflow",
        "pct",
        "high",
        lambda f, p: _pct(f.fcf, market_cap(f, p)),
    ),
    # Bilans
    MetricDef(
        "debt_equity", "Dług / kapitał", "balance", "x", "low", lambda f, _: _div(f.debt, f.equity)
    ),
    MetricDef(
        "debt_assets", "Dług / aktywa", "balance", "x", "low", lambda f, _: _div(f.debt, f.assets)
    ),
    MetricDef(
        "interest_coverage",
        "Pokrycie odsetek",
        "balance",
        "x",
        "high",
        lambda f, _: _div(f.operating_income, f.interest_expense),
    ),
    MetricDef(
        "current_ratio",
        "Płynność bieżąca",
        "balance",
        "x",
        "high",
        lambda f, _: _div(f.current_assets, f.current_liabilities),
    ),
    MetricDef("quick_ratio", "Płynność szybka", "balance", "x", "high", _quick),
    MetricDef(
        "cash_ps", "Gotówka na akcję", "balance", "usd", "high", lambda f, _: _div(f.cash, f.shares)
    ),
]

METRIC_BY_KEY = {m.key: m for m in METRICS}


def compute_metrics(f: Fundamentals, price: float | None) -> dict[str, float | None]:
    return {m.key: m.fn(f, price) for m in METRICS}


def average(values: list[float | None], min_count: int = 2) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if len(present) >= min_count else None


def peer_median(values: list[float | None], min_count: int = 2) -> float | None:
    present = [v for v in values if v is not None]
    return median(present) if len(present) >= min_count else None
