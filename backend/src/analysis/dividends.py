"""Statystyki dywidendowe z historii wypłat (data odcięcia, kwota na akcję). Czyste funkcje.

Kwoty z Yahoo są skorygowane o splity, więc wieloletnie porównania są spójne.
Lata liczone kalendarzowo po dacie odcięcia prawa (ex-date). Dywidendy specjalne
nie są odróżniane od zwykłych — źródło tego nie rozróżnia.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.analysis.sources import Bar

Dividend = tuple[date, float]

# Wzrost rok do roku liczony z tolerancją na zaokrąglenia kwot po korekcie o splity.
_GROWTH_EPS = 0.001


@dataclass(frozen=True)
class DividendYear:
    year: int
    dps: float
    yield_pct: float | None  # dywidenda roczna / cena zamknięcia na koniec roku
    partial: bool  # bieżący, niezakończony rok


@dataclass
class DividendStats:
    dps_ttm: float
    indicated_annual: float | None  # bieżąca stawka × liczba wypłat w roku
    yield_ttm: float | None
    payout_ratio: float | None  # % zysku netto
    fcf_coverage: float | None  # krotność: FCF / wypłacone dywidendy
    growth_streak: int  # kolejne lata wzrostu DPS
    paying_streak: int  # kolejne lata z wypłatą
    cagr: dict[int, float | None]  # lata → CAGR DPS w %
    frequency: str | None
    payments_per_year: int
    last_amount: float | None
    last_ex_date: date | None
    years: list[DividendYear] = field(default_factory=list)


def annual_dps(divs: list[Dividend]) -> dict[int, float]:
    out: dict[int, float] = {}
    for day, amount in divs:
        out[day.year] = out.get(day.year, 0.0) + amount
    return dict(sorted(out.items()))


_SPECIAL_FACTOR = 1.5
# Dodatkowa wypłata krótko po regularnej = specjalna. Podwyżkę (nawet 25×, jak NVIDIA
# 0,01 → 0,25) odróżnia to, że przychodzi w zwykłym rytmie, a nie wielkość.
_SPECIAL_MAX_GAP_DAYS = 45


def _is_special(prev: Dividend | None, cur: Dividend) -> bool:
    if prev is None:
        return False
    return cur[1] > prev[1] * _SPECIAL_FACTOR and (cur[0] - prev[0]).days < _SPECIAL_MAX_GAP_DAYS


def _regular_payments(divs: list[Dividend]) -> list[Dividend]:
    ordered = sorted(divs)
    return [d for i, d in enumerate(ordered) if not _is_special(ordered[i - 1] if i else None, d)]


def regular_rate(divs: list[Dividend]) -> dict[int, float]:
    """Stawka dywidendy obowiązująca na koniec każdego roku kalendarzowego
    (ostatnia regularna wypłata roku, z pominięciem wypłat specjalnych).

    Lepsza niż suma roczna, która skacze przy przesunięciu daty odcięcia (3 lub 5 wypłat
    w roku, np. Coca-Cola 2001) i lepsza niż mediana, która nie widzi podwyżki z ostatniej
    wypłaty roku (np. Microsoft podnosi dywidendę od wypłaty listopadowej)."""
    out: dict[int, float] = {}
    for day, amount in _regular_payments(divs):
        out[day.year] = amount  # posortowane — zostaje ostatnia wypłata roku
    return out


def ttm_dps(divs: list[Dividend], today: date) -> float:
    since = today - timedelta(days=365)
    return sum(a for d, a in divs if since < d <= today)


def growth_streak(rate_by_year: dict[int, float], last_full_year: int) -> int:
    """Kolejne lata (do ostatniego pełnego), w których stawka wzrosła względem roku poprzedniego."""
    by_year = rate_by_year
    streak = 0
    year = last_full_year
    while year - 1 in by_year and by_year.get(year, 0.0) > by_year[year - 1] * (1 + _GROWTH_EPS):
        streak += 1
        year -= 1
    return streak


def paying_streak(by_year: dict[int, float], last_full_year: int) -> int:
    streak = 0
    year = last_full_year
    while by_year.get(year, 0.0) > 0:
        streak += 1
        year -= 1
    return streak


def dps_cagr(by_year: dict[int, float], last_full_year: int, years: int) -> float | None:
    end = by_year.get(last_full_year)
    start = by_year.get(last_full_year - years)
    if not end or not start or end <= 0 or start <= 0:
        return None
    return float(((end / start) ** (1 / years) - 1) * 100)


_PAYMENTS_BY_LABEL = {"Miesięcznie": 12, "Kwartalnie": 4, "Półrocznie": 2, "Rocznie": 1}


def indicated_annual(divs: list[Dividend], frequency: str | None) -> float | None:
    """Roczna dywidenda wg bieżącej stawki: ostatnia regularna wypłata × liczba wypłat w roku.

    Niezależna od okna czasowego (TTM zależy od tego, ile dat odcięcia wpadło w 365 dni)."""
    per_year = _PAYMENTS_BY_LABEL.get(frequency or "")
    regular = _regular_payments(divs)
    if not regular or per_year is None:
        return None
    return regular[-1][1] * per_year


def frequency_label(payments_last_year: int) -> str | None:
    if payments_last_year == 0:
        return None
    if payments_last_year >= 11:
        return "Miesięcznie"
    if 3 <= payments_last_year <= 5:
        return "Kwartalnie"
    if payments_last_year == 2:
        return "Półrocznie"
    if payments_last_year == 1:
        return "Rocznie"
    return "Nieregularnie"


def _close_on_or_before(bars: list[Bar], day: date) -> float | None:
    idx = bisect_right([b.day for b in bars], day) - 1
    return bars[idx].close if idx >= 0 else None


def dividend_stats(
    divs: list[Dividend],
    *,
    today: date,
    price: float | None,
    monthly_bars: list[Bar],
    dividends_paid_ttm: float | None,
    net_income_ttm: float | None,
    fcf_ttm: float | None,
    shares: float | None,
) -> DividendStats | None:
    """None, gdy spółka nie wypłaciła dywidendy w ostatnich 2 latach."""
    divs = sorted(d for d in divs if d[0] <= today and d[1] > 0)
    if not divs or divs[-1][0] < today - timedelta(days=730):
        return None

    by_year = annual_dps(divs)
    last_full = today.year - 1
    dps = ttm_dps(divs, today)

    # Wypłacone dywidendy wg SEC; gdy brak konceptu — przybliżenie DPS × liczba akcji.
    paid = dividends_paid_ttm
    if paid is None and shares:
        paid = dps * shares
    payout = paid / net_income_ttm * 100 if paid and net_income_ttm and net_income_ttm > 0 else None
    coverage = fcf_ttm / paid if paid and fcf_ttm is not None else None

    since = today - timedelta(days=365)
    payments = sum(1 for d, _ in divs if since < d <= today)

    years = []
    for year, value in by_year.items():
        partial = year == today.year
        close = None if partial else _close_on_or_before(monthly_bars, date(year, 12, 31))
        # Cena z barów tylko, gdy bar faktycznie pochodzi z tego roku (brak starszej historii).
        if close is not None and monthly_bars and monthly_bars[0].day > date(year, 12, 31):
            close = None
        years.append(
            DividendYear(
                year=year,
                dps=value,
                yield_pct=value / close * 100 if close else None,
                partial=partial,
            )
        )

    freq = frequency_label(payments)
    return DividendStats(
        dps_ttm=dps,
        indicated_annual=indicated_annual(divs, freq),
        yield_ttm=dps / price * 100 if price else None,
        payout_ratio=payout,
        fcf_coverage=coverage,
        growth_streak=growth_streak(regular_rate(divs), last_full),
        paying_streak=paying_streak(by_year, last_full),
        cagr={n: dps_cagr(by_year, last_full, n) for n in (3, 5, 10)},
        frequency=freq,
        payments_per_year=payments,
        last_amount=divs[-1][1],
        last_ex_date=divs[-1][0],
        years=years,
    )


@dataclass(frozen=True)
class EarningsSurprise:
    period: date
    fiscal_quarter: str | None
    eps_actual: float | None
    eps_estimate: float | None
    surprise_pct: float | None
    revenue_actual: float | None


def surprise_pct(actual: float | None, estimate: float | None) -> float | None:
    if actual is None or estimate is None or estimate == 0:
        return None
    return (actual - estimate) / abs(estimate) * 100


def match_quarter_value(
    values: dict[date, float],
    period: date,
    fiscal_quarter: str | None = None,
    quarter_ends: dict[str, date] | None = None,
    slack_days: int = 10,
) -> float | None:
    """Dopasowanie kwartału z Finnhub do przychodów z SEC.

    1) Po etykiecie fiskalnej („Q2 2027") — jedyne pewne dla spółek z przesuniętym rokiem
       obrotowym (NVIDIA: kwartał do 26.07 Finnhub opisuje datą 30.09).
    2) Awaryjnie po dacie z tolerancją — Finnhub normalizuje do końca miesiąca (30.06),
       a spółki kończą kwartał np. w ostatnią sobotę (Apple: 27.06)."""
    if fiscal_quarter and quarter_ends and fiscal_quarter in quarter_ends:
        return values.get(quarter_ends[fiscal_quarter])
    best = min(values, key=lambda d: abs((d - period).days), default=None)
    if best is None or abs((best - period).days) > slack_days:
        return None
    return values[best]
