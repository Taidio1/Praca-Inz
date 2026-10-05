from datetime import date
from typing import Literal

from pydantic import BaseModel


class PopularCompanyOut(BaseModel):
    ticker: str
    name: str
    group: str
    group_label: str


class CompanySearchHitOut(BaseModel):
    ticker: str
    name: str


class MetricOut(BaseModel):
    key: str
    label: str
    group: Literal["valuation", "profitability", "cashflow", "balance"]
    fmt: Literal["x", "pct", "usd"]
    better: Literal["low", "high"]
    value: float | None
    avg_5y: float | None
    history: dict[int, float | None]  # rok obrotowy → wartość (podstawa avg_5y)


class PricePointOut(BaseModel):
    d: date
    close: float


class ChartEventOut(BaseModel):
    d: date
    kind: Literal["earnings", "dividend"]
    label: str


class FinancialYearOut(BaseModel):
    fiscal_year: int
    period_end: date
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None
    ocf: float | None
    fcf: float | None


class FilingOut(BaseModel):
    form: str
    filing_date: date
    report_date: date | None


class NextEarningsOut(BaseModel):
    d: date
    hour: str | None  # "bmo" przed sesją, "amc" po sesji
    fiscal_quarter: str | None
    eps_estimate: float | None = None  # konsensus analityków (Finnhub)
    revenue_estimate: float | None = None


class EarningsRowOut(BaseModel):
    period: date
    fiscal_quarter: str | None
    eps_actual: float | None
    eps_estimate: float | None
    surprise_pct: float | None
    revenue_actual: float | None  # SEC XBRL, przychody kwartału


class DividendYearOut(BaseModel):
    year: int
    dps: float
    yield_pct: float | None
    partial: bool


class DividendsOut(BaseModel):
    dps_ttm: float
    indicated_annual: float | None
    yield_ttm: float | None
    payout_ratio: float | None
    fcf_coverage: float | None
    growth_streak: int
    paying_streak: int
    cagr: dict[int, float | None]
    frequency: str | None
    payments_per_year: int
    last_amount: float | None
    last_ex_date: date | None
    history_from: int  # pierwszy rok w dostępnej historii (streak może być ograniczony)
    years: list[DividendYearOut]


class CompanyOverviewOut(BaseModel):
    ticker: str
    name: str
    cik: int
    exchange: str | None
    sector: str | None
    industry: str | None
    state: str | None
    fiscal_year_end: str | None
    description: str | None
    description_url: str | None
    logo_url: str | None = None
    website: str | None = None
    category: str | None = None  # branża wg Finnhub
    ipo_date: date | None = None
    next_earnings: NextEarningsOut | None = None
    earnings_history: list[EarningsRowOut] = []
    dividends: DividendsOut | None = None
    currency: str
    price: float | None
    change: float | None
    change_pct: float | None
    last_close_date: date | None
    market_cap: float | None
    enterprise_value: float | None
    shares_outstanding: float | None
    beta: float | None
    range_5y_low: float | None
    range_5y_high: float | None
    avg_daily_turnover_5y: float | None
    returns: dict[str, float | None]
    prices: list[PricePointOut]
    events: list[ChartEventOut]
    metrics: list[MetricOut]
    financials: list[FinancialYearOut]
    peers: list[str]
    peer_group: str | None
    fundamentals_as_of: date | None
    last_filing: FilingOut | None
    warnings: list[str]


class PeerRowOut(BaseModel):
    ticker: str
    name: str
    metrics: dict[str, float | None]


class PeerComparisonOut(BaseModel):
    peers: list[PeerRowOut]
    medians: dict[str, float | None]
