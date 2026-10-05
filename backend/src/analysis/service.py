"""Orkiestracja analizy spółki: SEC (fundamenty) + Yahoo (ceny) + Wikipedia (opis)
+ opcjonalnie Finnhub (logo, WWW, termin wyników, peers spoza listy popularnych).

Zależności HTTP tworzone są per request, więc cache żyje na poziomie modułu.
Sprawozdania zmieniają się raz na kwartał — długie TTL chronią limity SEC.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import structlog

from src.analysis import universe
from src.analysis.dividends import (
    dividend_stats,
    match_quarter_value,
    surprise_pct,
)
from src.analysis.metrics import (
    METRICS,
    average,
    compute_metrics,
    enterprise_value,
    market_cap,
    peer_median,
)
from src.analysis.prices import avg_daily_turnover, beta, close_on_or_before, period_returns
from src.analysis.sources import (
    AnalysisSourceError,
    EarningsDate,
    EarningsResult,
    FinnhubCompanyClient,
    FinnhubProfile,
    PriceHistory,
    SecClient,
    SecProfile,
    SecTicker,
    WikipediaClient,
    WikiSummary,
    YahooChartClient,
)
from src.analysis.xbrl import CompanyFinancials, parse_companyfacts, split_adjusted
from src.core.errors import NotFoundError
from src.schemas.analysis import (
    ChartEventOut,
    CompanyOverviewOut,
    CompanySearchHitOut,
    DividendsOut,
    DividendYearOut,
    EarningsRowOut,
    FilingOut,
    FinancialYearOut,
    MetricOut,
    NextEarningsOut,
    PeerComparisonOut,
    PeerRowOut,
    PopularCompanyOut,
    PricePointOut,
)

log = structlog.get_logger(__name__)

_TTL_TICKERS = 24 * 3600.0
_TTL_FACTS = 12 * 3600.0
_TTL_PROFILE = 12 * 3600.0
_TTL_PRICES = 15 * 60.0
_TTL_WIKI = 7 * 24 * 3600.0
_TTL_FINNHUB_PROFILE = 24 * 3600.0
_TTL_FINNHUB_PEERS = 24 * 3600.0
_TTL_FINNHUB_EARNINGS = 6 * 3600.0
_TTL_LONG_HISTORY = 12 * 3600.0
_HISTORY_YEARS = 5
BENCHMARK = "SPY"

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
# SEC: maks. ~10 req/s — kilka równoległych pobrań przy porównaniu z peerami.
_SEC_SEMAPHORE = asyncio.Semaphore(4)


def clear_cache() -> None:
    _CACHE.clear()
    _LOCKS.clear()


async def _cached[T](key: str, ttl: float, load: Callable[[], Awaitable[T]]) -> T:
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]  # type: ignore[no-any-return]
    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:  # równoległe żądania o tę samą spółkę → jedno pobranie
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[no-any-return]
        value = await load()
        _CACHE[key] = (time.monotonic(), value)
        return value


def with_finnhub_shares(
    fin: CompanyFinancials, profile: FinnhubProfile | None
) -> tuple[CompanyFinancials, bool]:
    """Uzupełnia brakującą w SEC liczbę akcji (spółki raportujące ją tylko per klasę) z Finnhub.

    Liczba z Finnhub jest bieżąca, więc data „złożenia” = dziś (bez korekty o splity)."""
    if fin.ttm.shares is not None or profile is None or not profile.shares_outstanding:
        return fin, False
    ttm = replace(fin.ttm, shares=profile.shares_outstanding, shares_filed=date.today())
    return replace(fin, ttm=ttm), True


class CompanyAnalysisService:
    def __init__(
        self,
        sec: SecClient,
        yahoo: YahooChartClient,
        wiki: WikipediaClient,
        finnhub: FinnhubCompanyClient | None = None,
    ) -> None:
        self._sec = sec
        self._yahoo = yahoo
        self._wiki = wiki
        self._finnhub = finnhub

    # ── źródła z cache ──

    async def _tickers(self) -> dict[str, SecTicker]:
        return await _cached("sec:tickers", _TTL_TICKERS, self._sec.tickers)

    async def _resolve(self, ticker: str) -> SecTicker:
        tickers = await self._tickers()
        key = ticker.upper()
        found = tickers.get(key) or tickers.get(key.replace(".", "-"))  # SEC: BRK-B
        if found is None:
            raise NotFoundError(f"Nie znaleziono spółki {ticker.upper()} w rejestrze SEC")
        return found

    async def _financials(self, cik: int) -> CompanyFinancials:
        async def load() -> CompanyFinancials:
            async with _SEC_SEMAPHORE:
                raw = await self._sec.companyfacts(cik)
            return parse_companyfacts(raw)  # trzymamy przetworzone, nie surowe MB JSON-a

        return await _cached(f"sec:facts:{cik}", _TTL_FACTS, load)

    async def _profile(self, cik: int) -> SecProfile:
        async def load() -> SecProfile:
            async with _SEC_SEMAPHORE:
                return await self._sec.submissions(cik)

        return await _cached(f"sec:sub:{cik}", _TTL_PROFILE, load)

    async def _prices(self, ticker: str) -> PriceHistory:
        return await _cached(
            f"yahoo:{ticker.upper()}", _TTL_PRICES, lambda: self._yahoo.history(ticker)
        )

    async def _wiki_summary(self, name: str) -> WikiSummary | None:
        return await _cached(f"wiki:{name}", _TTL_WIKI, lambda: self._wiki.summary(name))

    # Finnhub jest dodatkiem: błąd lub brak klucza = brak pola, nigdy błąd całej analizy.
    async def _fh_profile(self, ticker: str) -> FinnhubProfile | None:
        fh = self._finnhub
        if fh is None or not fh.enabled:
            return None
        try:
            return await _cached(
                f"fh:profile:{ticker}", _TTL_FINNHUB_PROFILE, lambda: fh.profile(ticker)
            )
        except AnalysisSourceError as exc:
            log.warning("analysis_finnhub_failed", what="profile", ticker=ticker, error=str(exc))
            return None

    async def _fh_earnings(self, ticker: str) -> EarningsDate | None:
        fh = self._finnhub
        if fh is None or not fh.enabled:
            return None
        try:
            return await _cached(
                f"fh:earn:{ticker}",
                _TTL_FINNHUB_EARNINGS,
                lambda: fh.next_earnings(ticker, date.today()),
            )
        except AnalysisSourceError as exc:
            log.warning("analysis_finnhub_failed", what="earnings", ticker=ticker, error=str(exc))
            return None

    async def _long_history(self, ticker: str) -> PriceHistory | None:
        try:
            return await _cached(
                f"yahoo:max:{ticker.upper()}",
                _TTL_LONG_HISTORY,
                lambda: self._yahoo.long_history(ticker),
            )
        except AnalysisSourceError as exc:
            log.warning("analysis_dividends_failed", ticker=ticker, error=str(exc))
            return None

    async def _fh_earnings_history(self, ticker: str) -> list[EarningsResult]:
        fh = self._finnhub
        if fh is None or not fh.enabled:
            return []
        try:
            return await _cached(
                f"fh:hist:{ticker}", _TTL_FINNHUB_EARNINGS, lambda: fh.earnings_history(ticker)
            )
        except AnalysisSourceError as exc:
            log.warning("analysis_finnhub_failed", what="history", ticker=ticker, error=str(exc))
            return []

    async def _peer_tickers(self, sec: SecTicker) -> tuple[list[str], str | None]:
        """Ręczna grupa branżowa; spoza listy — peers z Finnhub (tylko raportujące do SEC)."""
        own = universe.peers_of(sec.ticker)
        if own:
            return own, universe.group_of(sec.ticker)
        fh = self._finnhub
        if fh is None or not fh.enabled:
            return [], None
        try:
            raw = await _cached(
                f"fh:peers:{sec.ticker}", _TTL_FINNHUB_PEERS, lambda: fh.peers(sec.ticker)
            )
        except AnalysisSourceError as exc:
            log.warning("analysis_finnhub_failed", what="peers", ticker=sec.ticker, error=str(exc))
            return [], None
        known = await self._tickers()
        peers = [t for t in raw if t != sec.ticker and t in known][: universe.MAX_PEERS]
        return peers, "branża wg Finnhub" if peers else None

    # ── API ──

    @staticmethod
    def popular() -> list[PopularCompanyOut]:
        return [
            PopularCompanyOut(
                ticker=c.ticker, name=c.name, group=c.group, group_label=universe.GROUPS[c.group]
            )
            for c in universe.POPULAR
        ]

    async def search(self, q: str, limit: int = 10) -> list[CompanySearchHitOut]:
        needle = q.strip().upper()
        if not needle:
            return []
        scored: list[tuple[int, int, SecTicker]] = []
        for t in (await self._tickers()).values():
            name = t.name.upper()
            if t.ticker == needle:
                rank = 0
            elif t.ticker.startswith(needle):
                rank = 1
            elif name.startswith(needle):
                rank = 2
            elif needle in name:
                rank = 3
            else:
                continue
            scored.append((rank, t.rank, t))
        scored.sort(key=lambda r: (r[0], r[1]))
        return [CompanySearchHitOut(ticker=t.ticker, name=t.name) for *_, t in scored[:limit]]

    async def overview(self, ticker: str) -> CompanyOverviewOut:
        sec = await self._resolve(ticker)
        warnings: list[str] = []

        fin_r, prof_r, px_r, bench_r = await asyncio.gather(
            self._financials(sec.cik),
            self._profile(sec.cik),
            self._prices(sec.ticker),
            self._prices(BENCHMARK),
            return_exceptions=True,
        )
        fh_profile, fh_earnings, (peers, peer_group), long_px, fh_history = await asyncio.gather(
            self._fh_profile(sec.ticker),
            self._fh_earnings(sec.ticker),
            self._peer_tickers(sec),
            self._long_history(sec.ticker),
            self._fh_earnings_history(sec.ticker),
        )
        fin = fin_r if isinstance(fin_r, CompanyFinancials) else None
        profile = prof_r if isinstance(prof_r, SecProfile) else None
        px = px_r if isinstance(px_r, PriceHistory) else None
        bench = bench_r if isinstance(bench_r, PriceHistory) else None
        for label, res in (("SEC XBRL", fin_r), ("SEC profil", prof_r), ("notowania", px_r)):
            if isinstance(res, BaseException):
                log.warning(
                    "analysis_source_failed", source=label, ticker=sec.ticker, error=str(res)
                )
                warnings.append(f"Niedostępne źródło: {label}")
        if fin is not None and fin.as_of == date.min:
            warnings.append("Brak danych finansowych w formacie US-GAAP (np. emitent zagraniczny)")
            fin = None

        if fin is not None:
            fin, from_finnhub = with_finnhub_shares(fin, fh_profile)
            if from_finnhub:
                warnings.append(
                    "Liczba akcji z Finnhub — SEC raportuje ją tylko w podziale na klasy akcji; "
                    "mnożniki historyczne (vs 5Y) mogą być niedostępne"
                )
            elif fin.ttm.shares is None:
                warnings.append(
                    "Brak liczby akcji w raportach (np. kilka klas akcji) — "
                    "mnożniki wyceny niedostępne"
                )

        name = (px.long_name if px and px.long_name else None) or sec.name
        wiki: WikiSummary | None = None
        try:
            wiki = await self._wiki_summary(name)
        except AnalysisSourceError:
            wiki = None

        price = px.price if px else None
        bars = px.bars if px else []
        today = bars[-1].day if bars else date.today()

        splits = px.splits if px else []
        metrics = self._metrics_with_history(fin, price, bars, splits)
        financials = (
            [
                FinancialYearOut(
                    fiscal_year=y,
                    period_end=fin.fiscal_year_ends[y],
                    revenue=f.revenue,
                    gross_profit=f.gross_profit,
                    operating_income=f.operating_income,
                    net_income=f.net_income,
                    ocf=f.ocf,
                    fcf=f.fcf,
                )
                for y, f in sorted(fin.annual.items())
            ]
            if fin
            else []
        )

        five_y_ago = today - timedelta(days=5 * 365)
        window = [b for b in bars if b.day >= five_y_ago]

        events: list[ChartEventOut] = []
        if profile and bars:
            events += [
                ChartEventOut(
                    d=f.filing_date,
                    kind="earnings",
                    label=f"{f.form} za okres do {f.report_date or '?'}",
                )
                for f in profile.filings
                if f.filing_date >= five_y_ago
            ]
        if px:
            events += [
                ChartEventOut(d=d, kind="dividend", label=f"Dywidenda {amt:.2f} {px.currency}")
                for d, amt in px.dividends
                if d >= five_y_ago
            ]

        last_filing = profile.filings[-1] if profile and profile.filings else None

        dividends: DividendsOut | None = None
        if long_px is not None:
            ttm_fund = split_adjusted(fin.ttm, splits) if fin else None
            stats = dividend_stats(
                long_px.dividends,
                today=today,
                price=price,
                monthly_bars=long_px.bars,
                dividends_paid_ttm=ttm_fund.dividends_paid if ttm_fund else None,
                net_income_ttm=ttm_fund.net_income if ttm_fund else None,
                fcf_ttm=ttm_fund.fcf if ttm_fund else None,
                shares=ttm_fund.shares if ttm_fund else None,
            )
            if stats is not None:
                dividends = DividendsOut(
                    dps_ttm=stats.dps_ttm,
                    indicated_annual=stats.indicated_annual,
                    yield_ttm=stats.yield_ttm,
                    payout_ratio=stats.payout_ratio,
                    fcf_coverage=stats.fcf_coverage,
                    growth_streak=stats.growth_streak,
                    paying_streak=stats.paying_streak,
                    cagr=stats.cagr,
                    frequency=stats.frequency,
                    payments_per_year=stats.payments_per_year,
                    last_amount=stats.last_amount,
                    last_ex_date=stats.last_ex_date,
                    history_from=long_px.dividends[0][0].year,
                    years=[
                        DividendYearOut(
                            year=y.year, dps=y.dps, yield_pct=y.yield_pct, partial=y.partial
                        )
                        for y in stats.years
                    ],
                )

        quarterly_rev = fin.quarterly_revenue if fin else {}
        earnings_rows = [
            EarningsRowOut(
                period=e.period,
                fiscal_quarter=e.fiscal_quarter,
                eps_actual=e.eps_actual,
                eps_estimate=e.eps_estimate,
                surprise_pct=surprise_pct(e.eps_actual, e.eps_estimate),
                revenue_actual=match_quarter_value(
                    quarterly_rev,
                    e.period,
                    e.fiscal_quarter,
                    fin.quarter_ends if fin else None,
                ),
            )
            for e in fh_history
        ]
        change = price - px.previous_close if px and price and px.previous_close else None

        return CompanyOverviewOut(
            ticker=sec.ticker,
            name=name,
            cik=sec.cik,
            exchange=(px.exchange if px else None)
            or (profile.exchanges[0] if profile and profile.exchanges else None),
            sector=(profile.sector if profile else None)
            or (fh_profile.industry if fh_profile else None),
            industry=profile.sic_description if profile else None,
            state=profile.state if profile else None,
            fiscal_year_end=profile.fiscal_year_end if profile else None,
            description=wiki.text if wiki else None,
            description_url=wiki.url if wiki else None,
            logo_url=fh_profile.logo_url if fh_profile else None,
            website=fh_profile.website if fh_profile else None,
            category=fh_profile.industry if fh_profile else None,
            ipo_date=fh_profile.ipo if fh_profile else None,
            next_earnings=NextEarningsOut(
                d=fh_earnings.day,
                hour=fh_earnings.hour,
                fiscal_quarter=fh_earnings.fiscal_quarter,
                eps_estimate=fh_earnings.eps_estimate,
                revenue_estimate=fh_earnings.revenue_estimate,
            )
            if fh_earnings
            else None,
            currency=px.currency if px else "USD",
            price=price,
            change=change,
            change_pct=(change / px.previous_close * 100)
            if change is not None and px and px.previous_close
            else None,
            last_close_date=bars[-1].day if bars else None,
            market_cap=market_cap(split_adjusted(fin.ttm, splits), price) if fin else None,
            enterprise_value=enterprise_value(split_adjusted(fin.ttm, splits), price)
            if fin
            else None,
            shares_outstanding=split_adjusted(fin.ttm, splits).shares if fin else None,
            beta=beta(window, bench.bars) if bench else None,
            range_5y_low=min((b.close for b in window), default=None),
            range_5y_high=max((b.close for b in window), default=None),
            avg_daily_turnover_5y=avg_daily_turnover(window),
            returns=period_returns(bars, today),
            prices=[PricePointOut(d=b.day, close=round(b.close, 4)) for b in window],
            events=sorted(events, key=lambda e: e.d),
            metrics=metrics,
            financials=financials,
            peers=peers,
            peer_group=peer_group,
            fundamentals_as_of=fin.as_of if fin else None,
            last_filing=FilingOut(
                form=last_filing.form,
                filing_date=last_filing.filing_date,
                report_date=last_filing.report_date,
            )
            if last_filing
            else None,
            warnings=warnings,
            earnings_history=earnings_rows,
            dividends=dividends,
        )

    @staticmethod
    def _metrics_with_history(
        fin: CompanyFinancials | None,
        price: float | None,
        bars: list[Any],
        splits: list[tuple[date, float]],
    ) -> list[MetricOut]:
        current = compute_metrics(split_adjusted(fin.ttm, splits), price) if fin else {}
        history: dict[int, dict[str, float | None]] = {}
        if fin:
            for year in sorted(fin.annual)[-_HISTORY_YEARS:]:
                # Mnożniki historyczne: cena z dnia końca roku obrotowego.
                year_price = close_on_or_before(bars, fin.fiscal_year_ends[year]) if bars else None
                if bars and fin.fiscal_year_ends[year] < bars[0].day:
                    year_price = None
                history[year] = compute_metrics(
                    split_adjusted(fin.annual[year], splits), year_price
                )
        return [
            MetricOut(
                key=m.key,
                label=m.label,
                group=m.group,  # type: ignore[arg-type]
                fmt=m.fmt,
                better=m.better,
                value=current.get(m.key),
                avg_5y=average([h[m.key] for h in history.values()]),
                history={y: h[m.key] for y, h in history.items()},
            )
            for m in METRICS
        ]

    async def peer_comparison(self, ticker: str) -> PeerComparisonOut:
        sec = await self._resolve(ticker)
        tickers_map = await self._tickers()
        peer_list, _ = await self._peer_tickers(sec)
        peers = [tickers_map[p] for p in peer_list if p in tickers_map]

        async def row(peer: SecTicker) -> PeerRowOut | None:
            try:
                fin, px = await asyncio.gather(
                    self._financials(peer.cik), self._prices(peer.ticker)
                )
            except AnalysisSourceError as exc:
                log.warning("analysis_peer_failed", ticker=peer.ticker, error=str(exc))
                return None
            if fin.ttm.shares is None:
                fin, _ = with_finnhub_shares(fin, await self._fh_profile(peer.ticker))
            return PeerRowOut(
                ticker=peer.ticker,
                name=px.long_name or peer.name,
                metrics=compute_metrics(split_adjusted(fin.ttm, px.splits), px.price),
            )

        rows = [r for r in await asyncio.gather(*(row(p) for p in peers)) if r is not None]
        medians = {m.key: peer_median([r.metrics.get(m.key) for r in rows]) for m in METRICS}
        return PeerComparisonOut(peers=rows, medians=medians)
