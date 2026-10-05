"""Walidacja obliczeń analizy spółek na danych rzeczywistych.

Dwa niezależne rodzaje kontroli:

1. **Referencja zewnętrzna** — wskaźniki Opes (SEC XBRL + Yahoo) vs wartości policzone
   niezależnie przez Finnhub (`/stock/metric`, `/stock/earnings`). Różnice metodologiczne
   istnieją (np. moment ceny, definicja długu), dlatego kryterium to odsetek spółek
   w tolerancji i mediana odchylenia, a nie równość każdej wartości.
2. **Spójność wewnętrzna** — ta sama wielkość policzona dwiema niezależnymi ścieżkami
   kodu (np. TTM z rocznych/narastających vs suma 4 kwartałów). Tu tolerancje są ostre.

Uruchomienie raportu (np. do rozdziału z wynikami):

    cd backend
    python -m tests.evaluation.reference            # wszystkie popularne spółki
    python -m tests.evaluation.reference AAPL KO    # wybrane
    python -m tests.evaluation.reference --out raport.md
"""

import argparse
import asyncio
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from src.analysis.service import CompanyAnalysisService
from src.analysis.sources import (
    FinnhubCompanyClient,
    SecClient,
    WikipediaClient,
    YahooChartClient,
)
from src.analysis.universe import POPULAR
from src.analysis.xbrl import CompanyFinancials
from src.core.config import get_settings
from src.schemas.analysis import CompanyOverviewOut

FINNHUB = "https://finnhub.io/api/v1"
# Darmowy plan Finnhub: 60 zapytań/min; overview + referencja ≈ 6 zapytań na spółkę.
SECONDS_PER_COMPANY = 6.5


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    ours: Callable[[CompanyOverviewOut], float | None]
    ref: Callable[[dict[str, Any]], float | None]
    tolerance_pct: float  # odchylenie pojedynczej spółki uznane za zgodne
    min_share: float  # wymagany odsetek spółek w tolerancji
    max_median_pct: float  # wymagana mediana odchylenia
    strict: bool  # False = tylko raport (znane różnice metodologiczne)
    note: str = ""


def _metric(key: str) -> Callable[[CompanyOverviewOut], float | None]:
    def get(o: CompanyOverviewOut) -> float | None:
        return next((m.value for m in o.metrics if m.key == key), None)

    return get


def _ref(key: str, scale: float = 1.0) -> Callable[[dict[str, Any]], float | None]:
    def get(ref: dict[str, Any]) -> float | None:
        v = (ref.get("metric") or {}).get(key)
        return float(v) * scale if isinstance(v, int | float) else None

    return get


def _div(attr: str) -> Callable[[CompanyOverviewOut], float | None]:
    def get(o: CompanyOverviewOut) -> float | None:
        return getattr(o.dividends, attr) if o.dividends else None

    return get


def _cagr5(o: CompanyOverviewOut) -> float | None:
    return o.dividends.cagr.get(5) if o.dividends else None


CHECKS: list[Check] = [
    Check(
        "mcap",
        "Kapitalizacja",
        lambda o: o.market_cap,
        _ref("marketCapitalization", 1e6),
        15,
        0.90,
        3,
        True,
    ),
    Check(
        "pe",
        "P/E TTM",
        _metric("pe"),
        _ref("peTTM"),
        15,
        0.85,
        3,
        True,
        "odchylenia: opóźnienie raportu SEC vs komunikat prasowy (np. MU)",
    ),
    Check(
        "ps",
        "P/S TTM",
        _metric("ps"),
        _ref("psTTM"),
        15,
        0.85,
        3,
        True,
        "banki: inna definicja przychodu",
    ),
    Check(
        "gross_margin",
        "Marża brutto",
        _metric("gross_margin"),
        _ref("grossMarginTTM"),
        5,
        0.85,
        1,
        True,
    ),
    Check(
        "operating_margin",
        "Marża operacyjna",
        _metric("operating_margin"),
        _ref("operatingMarginTTM"),
        15,
        0.80,
        2,
        True,
    ),
    Check(
        "net_margin",
        "Marża netto",
        _metric("net_margin"),
        _ref("netProfitMarginTTM"),
        15,
        0.90,
        1,
        True,
    ),
    Check(
        "current_ratio",
        "Płynność bieżąca",
        _metric("current_ratio"),
        _ref("currentRatioQuarterly"),
        5,
        0.90,
        1,
        True,
    ),
    Check(
        "dps_indicated",
        "Dywidenda wskazana (roczna)",
        _div("indicated_annual"),
        _ref("dividendIndicatedAnnual"),
        5,
        0.75,
        1,
        True,
        "różnica, gdy podwyżka ogłoszona, a data odcięcia jeszcze nie minęła (np. JPM, MSFT)",
    ),
    Check(
        "payout",
        "Wskaźnik wypłaty",
        _div("payout_ratio"),
        _ref("payoutRatioTTM"),
        15,
        0.75,
        5,
        True,
        "Opes: gotówka wypłacona/zysk (SEC); Finnhub: DPS/EPS",
    ),
    # Tylko raport — różnice definicji, opisane w odpowiedzi do pracy
    Check(
        "dps_ttm",
        "Dywidenda na akcję TTM",
        _div("dps_ttm"),
        _ref("dividendPerShareTTM"),
        5,
        0,
        100,
        False,
        "Finnhub TTM niespójne z rejestrem wypłat (np. KO: 2,57 = 5 wypłat w 12 mies.; "
        "NVDA: 0,2795 nie jest sumą żadnych 4 kolejnych wypłat) — Opes: suma wg dat odcięcia",
    ),
    Check(
        "dividend_yield",
        "Stopa dywidendy TTM",
        _div("yield_ttm"),
        _ref("currentDividendYieldTTM"),
        10,
        0,
        100,
        False,
        "pochodna DPS TTM — jw.; spójność yield = DPS/cena sprawdzana wewnętrznie",
    ),
    Check(
        "pb",
        "P/B",
        _metric("pb"),
        _ref("pbQuarterly"),
        15,
        0,
        100,
        False,
        "Finnhub: kwartalna cena/wartość księgowa (inny moment ceny)",
    ),
    Check(
        "roe",
        "ROE",
        _metric("roe"),
        _ref("roeTTM"),
        15,
        0,
        100,
        False,
        "Opes: kapitał na koniec okresu; Finnhub: średni",
    ),
    Check(
        "quick_ratio",
        "Płynność szybka",
        _metric("quick_ratio"),
        _ref("quickRatioQuarterly"),
        15,
        0,
        100,
        False,
        "Opes: (aktywa obrotowe − zapasy); Finnhub: gotówka + należności",
    ),
    Check(
        "debt_equity",
        "Dług / kapitał",
        _metric("debt_equity"),
        _ref("totalDebt/totalEquityQuarterly"),
        15,
        0,
        100,
        False,
        "Finnhub wlicza leasing i (banki) depozyty/inne finansowanie",
    ),
    Check(
        "beta",
        "Beta",
        lambda o: o.beta,
        _ref("beta"),
        15,
        0,
        100,
        False,
        "Opes: tygodniowe stopy 5Y vs SPY",
    ),
    Check(
        "dividend_cagr5",
        "CAGR dywidendy 5L",
        _cagr5,
        _ref("dividendGrowthRate5Y"),
        15,
        0,
        100,
        False,
        "Opes: lata kalendarzowe wg dat odcięcia",
    ),
]


@dataclass
class CompanyResult:
    ticker: str
    pairs: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    consistency: list[tuple[str, bool, str]] = field(default_factory=list)
    error: str | None = None


def deviation_pct(ours: float, ref: float) -> float:
    return abs(ours - ref) / abs(ref) * 100


def consistency_checks(
    o: CompanyOverviewOut, fin: CompanyFinancials | None, surprises: dict[str, float]
) -> list[tuple[str, bool, str]]:
    """Kontrole, w których ta sama wielkość wychodzi z dwóch niezależnych ścieżek kodu."""
    out: list[tuple[str, bool, str]] = []

    def check(name: str, a: float | None, b: float | None, tol_pct: float) -> None:
        if a is None or b is None or b == 0:
            return
        dev = deviation_pct(a, b)
        out.append((name, dev <= tol_pct, f"{a:.6g} vs {b:.6g} ({dev:.2f}%)"))

    # Kapitalizacja = cena × liczba akcji
    if o.price is not None and o.shares_outstanding is not None:
        check("mcap = cena × akcje", o.market_cap, o.price * o.shares_outstanding, 0.01)
    # Stopa dywidendy = DPS / cena
    if o.dividends and o.price:
        check(
            "yield = DPS / cena", o.dividends.yield_ttm, o.dividends.dps_ttm / o.price * 100, 0.01
        )
    # TTM (rok + YTD − YTD rok wcześniej) vs suma 4 ostatnich kwartałów (inna ścieżka: 3-mies.
    # fakty + Q4 wyprowadzony z 10-K). Obie z tych samych raportów, ale różnym kodem.
    if fin and len(fin.quarterly_revenue) >= 4:
        ends = sorted(fin.quarterly_revenue)[-4:]
        # 4 kolejne kwartały kończące się na dacie TTM (bez luk > ~100 dni)
        contiguous = all((b - a).days <= 100 for a, b in zip(ends, ends[1:], strict=False))
        if contiguous and ends[-1] == fin.as_of:
            check(
                "TTM przychody = Σ 4 kwartały",
                fin.ttm.revenue,
                sum(fin.quarterly_revenue[e] for e in ends),
                0.5,
            )
    # Zaskoczenie EPS: nasz wzór vs pole surprisePercent z Finnhub
    for row in o.earnings_history:
        ref = surprises.get(row.period.isoformat())
        if row.surprise_pct is not None and ref is not None and abs(ref) > 0.05:
            check(f"zaskoczenie EPS {row.fiscal_quarter}", row.surprise_pct, ref, 1.0)
    # Roczny DPS = suma wypłat; stopa roczna dodatnia i < 100%
    if o.dividends:
        for y in o.dividends.years:
            if y.yield_pct is not None and not 0 < y.yield_pct < 100:
                out.append((f"stopa dywidendy {y.year} w zakresie", False, f"{y.yield_pct}"))
    return out


async def _finnhub_json(h: httpx.AsyncClient, path: str, **params: str) -> Any:
    key = get_settings().finnhub_api_key
    res = await h.get(f"{FINNHUB}{path}", params={**params, "token": key})
    res.raise_for_status()
    return res.json()


async def collect(tickers: list[str], pace: bool = True) -> list[CompanyResult]:
    settings = get_settings()
    if not settings.finnhub_api_key:
        raise RuntimeError("Walidacja wymaga FINNHUB_API_KEY w backend/.env")
    results = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as h:
        svc = CompanyAnalysisService(
            SecClient(h, settings.sec_user_agent),
            YahooChartClient(h),
            WikipediaClient(h),
            FinnhubCompanyClient(h, settings.finnhub_api_key),
        )
        for i, ticker in enumerate(tickers):
            r = CompanyResult(ticker)
            try:
                o = await svc.overview(ticker)
                fin = await svc._financials(o.cik)
                ref = await _finnhub_json(h, "/stock/metric", symbol=ticker, metric="all")
                hist = await _finnhub_json(h, "/stock/earnings", symbol=ticker)
                surprises = {
                    str(x["period"]): float(x["surprisePercent"])
                    for x in hist
                    if x.get("surprisePercent") is not None
                }
                for c in CHECKS:
                    r.pairs[c.key] = (c.ours(o), c.ref(ref))
                r.consistency = consistency_checks(o, fin, surprises)
            except Exception as exc:  # raport ma objąć wszystkie spółki
                r.error = f"{type(exc).__name__}: {exc}"
            results.append(r)
            print(f"[{i + 1}/{len(tickers)}] {ticker}", file=sys.stderr, flush=True)
            if pace and i < len(tickers) - 1:
                await asyncio.sleep(SECONDS_PER_COMPANY)
    return results


@dataclass
class CheckSummary:
    check: Check
    compared: int
    within: int
    median_dev: float | None
    outliers: list[str]

    @property
    def share(self) -> float:
        return self.within / self.compared if self.compared else 0.0

    @property
    def passed(self) -> bool:
        if not self.check.strict:
            return True
        return (
            self.compared > 0
            and self.share >= self.check.min_share
            and self.median_dev is not None
            and self.median_dev <= self.check.max_median_pct
        )


def summarize(results: list[CompanyResult]) -> list[CheckSummary]:
    out = []
    for c in CHECKS:
        devs: list[float] = []
        outliers: list[str] = []
        for r in results:
            ours, ref = r.pairs.get(c.key, (None, None))
            if ours is None or ref is None or ref == 0:
                continue
            d = deviation_pct(ours, ref)
            devs.append(d)
            if d > c.tolerance_pct:
                outliers.append(f"{r.ticker} ({ours:.4g} vs {ref:.4g})")
        out.append(
            CheckSummary(
                c,
                len(devs),
                sum(1 for d in devs if d <= c.tolerance_pct),
                statistics.median(devs) if devs else None,
                outliers,
            )
        )
    return out


def render_report(results: list[CompanyResult]) -> str:
    lines = [
        f"# Walidacja obliczeń analizy spółek — {date.today().isoformat()}",
        "",
        f"Spółek: {len(results)}. Referencja: Finnhub `/stock/metric` i `/stock/earnings`.",
        "",
        "## Zgodność z referencją zewnętrzną",
        "",
        "| Wskaźnik | Porównań | W tolerancji | Mediana odch. | Tolerancja | Wynik | Uwagi |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in summarize(results):
        status = ("✅ OK" if s.passed else "❌ BŁĄD") if s.check.strict else "ℹ️ raport"
        med = f"{s.median_dev:.1f}%" if s.median_dev is not None else "—"
        lines.append(
            f"| {s.check.label} | {s.compared} | {s.within} ({s.share:.0%}) | {med} | "
            f"±{s.check.tolerance_pct:g}% | {status} | {s.check.note} |"
        )
    lines += ["", "## Odchylenia ponad tolerancję", ""]
    for s in summarize(results):
        if s.outliers:
            lines.append(f"- **{s.check.label}:** " + "; ".join(s.outliers))
    lines += ["", "## Spójność wewnętrzna (dwie niezależne ścieżki obliczeń)", ""]
    total = [c for r in results for c in r.consistency]
    failed = [(r.ticker, c) for r in results for c in r.consistency if not c[1]]
    lines.append(f"Kontroli: {len(total)}, niezgodnych: {len(failed)}.")
    for ticker, (name, _, detail) in failed:
        lines.append(f"- ❌ {ticker}: {name} — {detail}")
    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "## Błędy pobierania", ""]
        lines += [f"- {r.ticker}: {r.error}" for r in errors]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("tickers", nargs="*", help="domyślnie: wszystkie popularne spółki")
    parser.add_argument("--out", help="zapisz raport Markdown do pliku")
    args = parser.parse_args()
    tickers = [t.upper() for t in args.tickers] or [c.ticker for c in POPULAR]
    report = render_report(asyncio.run(collect(tickers)))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(report)


if __name__ == "__main__":
    main()
