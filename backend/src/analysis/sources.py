"""Klienty publicznych źródeł analizy spółek (bez kluczy API).

- SEC EDGAR: lista tickerów → CIK, `companyfacts` (XBRL), `submissions` (profil, raporty).
  SEC wymaga nagłówka User-Agent z danymi kontaktowymi i limitu ~10 req/s.
- Yahoo Finance chart v8: dzienne notowania + dywidendy.
- Wikipedia REST: krótki opis spółki (najpierw polska, potem angielska).
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

SEC_USER_AGENT = "Opes research tool (praca inzynierska) opes-research@example.com"


class AnalysisSourceError(Exception):
    """Nieudane pobranie danych z zewnętrznego źródła."""


async def _get(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    try:
        res = await client.get(url, params=params, headers=headers)
        res.raise_for_status()
        return res.json()
    except httpx.HTTPError as exc:
        # Timeouty mają pusty str(exc) — nazwa klasy mówi, co się stało.
        raise AnalysisSourceError(f"HTTP {url}: {type(exc).__name__} {exc}".strip()) from exc
    except ValueError as exc:
        raise AnalysisSourceError(f"Odpowiedź {url} nie jest JSON-em") from exc


# ─── SEC EDGAR ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SecTicker:
    ticker: str
    cik: int
    name: str
    rank: int = 0  # pozycja na liście SEC — z grubsza wg kapitalizacji


@dataclass(frozen=True)
class Filing:
    form: str
    filing_date: date
    report_date: date | None


@dataclass(frozen=True)
class SecProfile:
    name: str
    sic: str | None
    sic_description: str | None
    sector: str | None
    exchanges: list[str]
    fiscal_year_end: str | None  # MMDD
    state: str | None
    filings: list[Filing]


def parse_sec_tickers(data: dict[str, Any]) -> dict[str, SecTicker]:
    out: dict[str, SecTicker] = {}
    for i, row in enumerate(data.values()):
        try:
            ticker = str(row["ticker"]).upper()
            out.setdefault(ticker, SecTicker(ticker, int(row["cik_str"]), str(row["title"]), i))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_sec_submissions(data: dict[str, Any]) -> SecProfile:
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    filed = recent.get("filingDate") or []
    reported = recent.get("reportDate") or []
    filings = []
    for i, form in enumerate(forms):
        if form not in ("10-K", "10-Q"):
            continue
        try:
            fd = date.fromisoformat(filed[i])
        except (IndexError, ValueError):
            continue
        rd: date | None
        try:
            rd = date.fromisoformat(reported[i]) if reported[i] else None
        except (IndexError, ValueError):
            rd = None
        filings.append(Filing(form=form, filing_date=fd, report_date=rd))
    owner = str(data.get("ownerOrg") or "")
    sector = re.sub(r"^\d+\s*", "", owner) or None  # "06 Technology" → "Technology"
    return SecProfile(
        name=str(data.get("name") or ""),
        sic=str(data["sic"]) if data.get("sic") else None,
        sic_description=data.get("sicDescription") or None,
        sector=sector,
        exchanges=[str(e) for e in data.get("exchanges") or [] if e],
        fiscal_year_end=data.get("fiscalYearEnd") or None,
        state=data.get("stateOfIncorporation") or None,
        filings=sorted(filings, key=lambda f: f.filing_date),
    )


class SecClient:
    def __init__(self, client: httpx.AsyncClient, user_agent: str = SEC_USER_AGENT) -> None:
        self._client = client
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}

    async def tickers(self) -> dict[str, SecTicker]:
        data = await _get(
            self._client, "https://www.sec.gov/files/company_tickers.json", headers=self._headers
        )
        return parse_sec_tickers(data)

    async def companyfacts(self, cik: int) -> dict[str, Any]:
        data: dict[str, Any] = await _get(
            self._client,
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            headers=self._headers,
        )
        return data

    async def submissions(self, cik: int) -> SecProfile:
        data = await _get(
            self._client,
            f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            headers=self._headers,
        )
        return parse_sec_submissions(data)


# ─── Yahoo chart ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Bar:
    day: date
    close: float
    volume: float | None


@dataclass
class PriceHistory:
    currency: str
    long_name: str | None
    exchange: str | None
    price: float | None
    previous_close: float | None
    bars: list[Bar] = field(default_factory=list)
    dividends: list[tuple[date, float]] = field(default_factory=list)
    splits: list[tuple[date, float]] = field(default_factory=list)  # (dzień, mnożnik akcji)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_HISTORY_START = int((datetime(1950, 1, 1, tzinfo=UTC) - _EPOCH).total_seconds())


def utc_day(ts: Any) -> date:
    """Unix timestamp → data UTC. Działa też dla dat sprzed 1970 (ujemne znaczniki czasu),
    na których `datetime.fromtimestamp` rzuca OSError na Windowsie (np. dywidendy Coca-Coli)."""
    return (_EPOCH + timedelta(seconds=int(ts))).date()


def yahoo_symbol(ticker: str) -> str:
    return ticker.upper().replace(".", "-")  # BRK.B → BRK-B


def parse_yahoo_chart(data: dict[str, Any], symbol: str) -> PriceHistory:
    chart = data.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        err = (chart.get("error") or {}).get("description")
        raise AnalysisSourceError(f"Yahoo: brak notowań dla {symbol} ({err})")
    r = results[0]
    meta = r.get("meta") or {}
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars: dict[date, Bar] = {}
    for i, ts in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        vol = volumes[i] if i < len(volumes) else None
        day = utc_day(ts)
        bars[day] = Bar(day=day, close=float(close), volume=float(vol) if vol else None)
    ordered = [bars[d] for d in sorted(bars)]

    divs = []
    for ev in ((r.get("events") or {}).get("dividends") or {}).values():
        try:
            divs.append((utc_day(ev["date"]), float(ev["amount"])))
        except (KeyError, TypeError, ValueError):
            continue

    splits = []
    for ev in ((r.get("events") or {}).get("splits") or {}).values():
        try:
            num, den = float(ev["numerator"]), float(ev["denominator"])
            day = utc_day(ev["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if num > 0 and den > 0:
            splits.append((day, num / den))

    price = meta.get("regularMarketPrice")
    prev = ordered[-2].close if len(ordered) >= 2 else None
    return PriceHistory(
        currency=str(meta.get("currency") or "USD"),
        long_name=meta.get("longName") or meta.get("shortName"),
        exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
        price=float(price) if price is not None else (ordered[-1].close if ordered else None),
        previous_close=prev,
        bars=ordered,
        dividends=sorted(divs),
        splits=sorted(splits),
    )


class YahooChartClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def history(self, ticker: str, range_: str = "10y") -> PriceHistory:
        symbol = yahoo_symbol(ticker)
        data = await _get(
            self._client,
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": range_, "interval": "1d", "events": "div|split"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        return parse_yahoo_chart(data, symbol)

    async def long_history(self, ticker: str) -> PriceHistory:
        """Cała historia notowań (interwał miesięczny) z wszystkimi dywidendami.

        Jawny zakres dat zamiast range=max: przy range=max Yahoo gubi zdarzenia
        (np. Coca-Cola: brak dywidend 2004–2025), przy period1/period2 lista jest pełna."""
        symbol = yahoo_symbol(ticker)
        period2 = int((datetime.now(UTC) - _EPOCH).total_seconds())
        data = await _get(
            self._client,
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={
                "period1": str(_HISTORY_START),
                "period2": str(period2),
                "interval": "1mo",
                "events": "div|split",
            },
            headers={"User-Agent": "Mozilla/5.0"},
        )
        return parse_yahoo_chart(data, symbol)


# ─── Wikipedia ───────────────────────────────────────────────────────────────

_LEGAL_SUFFIX = re.compile(
    r"[,.]?\s+(inc|corp|corporation|co|company|ltd|plc|holdings|group|& co)\.?$", re.I
)


def clean_company_name(name: str) -> str:
    prev = None
    out = name.strip()
    while prev != out:
        prev = out
        out = _LEGAL_SUFFIX.sub("", out).strip()
    return out


_WIKI_MIN_GOOD_CHARS = 350


@dataclass(frozen=True)
class WikiSummary:
    text: str
    url: str
    lang: str


class WikipediaClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._headers = {"User-Agent": SEC_USER_AGENT}

    async def _intro(self, lang: str, base: str, key_word: str) -> WikiSummary | None:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        found = await _get(
            self._client,
            api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{base} przedsiębiorstwo" if lang == "pl" else f"{base} company",
                "srlimit": "3",
                "format": "json",
            },
            headers=self._headers,
        )
        for hit in (found.get("query") or {}).get("search") or []:
            title = str(hit.get("title") or "")
            if key_word not in title.lower():  # chroni przed trafieniem w inny artykuł
                continue
            page = await _get(
                self._client,
                api,
                params={
                    "action": "query",
                    "prop": "extracts|info",
                    "exintro": "1",
                    "explaintext": "1",
                    "inprop": "url",
                    "redirects": "1",
                    "titles": title,
                    "format": "json",
                },
                headers=self._headers,
            )
            for p in ((page.get("query") or {}).get("pages") or {}).values():
                text = re.sub(r"\n{2,}", "\n", str(p.get("extract") or "")).strip()
                if len(text) > 80 and "may refer to" not in text:
                    return WikiSummary(text=text, url=str(p.get("fullurl") or ""), lang=lang)
        return None

    async def summary(self, company_name: str) -> WikiSummary | None:
        """Wstęp artykułu: polski, chyba że jest szczątkowy — wtedy dłuższy angielski."""
        base = clean_company_name(company_name)
        if not base:
            return None
        key_word = base.split()[0].lower()
        best: WikiSummary | None = None
        for lang in ("pl", "en"):
            try:
                found = await self._intro(lang, base, key_word)
            except AnalysisSourceError:
                continue
            if found and (best is None or len(found.text) > len(best.text)):
                best = found
            if best and len(best.text) >= _WIKI_MIN_GOOD_CHARS:
                break
        return best


# ─── Finnhub (darmowy plan) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class FinnhubProfile:
    name: str | None
    logo_url: str | None
    website: str | None
    industry: str | None
    ipo: date | None
    country: str | None
    shares_outstanding: float | None = None  # sztuki, łącznie dla wszystkich klas


@dataclass(frozen=True)
class EarningsDate:
    day: date
    hour: str | None  # "bmo" przed sesją, "amc" po sesji, None gdy nieznane
    fiscal_quarter: str | None  # np. "Q4 2026"
    eps_estimate: float | None = None  # konsensus analityków
    revenue_estimate: float | None = None


@dataclass(frozen=True)
class EarningsResult:
    period: date  # koniec kwartału (znormalizowany przez Finnhub do końca miesiąca)
    fiscal_quarter: str | None
    eps_actual: float | None  # EPS raportowany/skorygowany wg Finnhub
    eps_estimate: float | None


def _opt_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_finnhub_earnings_history(data: Any) -> list[EarningsResult]:
    out = []
    for row in data if isinstance(data, list) else []:
        try:
            period = date.fromisoformat(str(row["period"]))
        except (KeyError, ValueError):
            continue
        q, y = row.get("quarter"), row.get("year")
        out.append(
            EarningsResult(
                period=period,
                fiscal_quarter=f"Q{q} {y}" if q and y else None,
                eps_actual=_opt_float(row.get("actual")),
                eps_estimate=_opt_float(row.get("estimate")),
            )
        )
    return sorted(out, key=lambda e: e.period, reverse=True)


def parse_finnhub_profile(data: dict[str, Any]) -> FinnhubProfile | None:
    if not data or not data.get("ticker"):  # nieznany symbol → pusty obiekt
        return None
    ipo: date | None
    try:
        ipo = date.fromisoformat(str(data["ipo"])) if data.get("ipo") else None
    except ValueError:
        ipo = None
    return FinnhubProfile(
        name=data.get("name") or None,
        logo_url=data.get("logo") or None,
        website=data.get("weburl") or None,
        industry=data.get("finnhubIndustry") or None,
        ipo=ipo,
        country=data.get("country") or None,
        # Finnhub podaje liczbę akcji w milionach
        shares_outstanding=float(data["shareOutstanding"]) * 1e6
        if data.get("shareOutstanding")
        else None,
    )


def parse_finnhub_earnings(data: dict[str, Any], today: date) -> EarningsDate | None:
    upcoming = []
    for row in data.get("earningsCalendar") or []:
        try:
            day = date.fromisoformat(str(row["date"]))
        except (KeyError, ValueError):
            continue
        if day < today:
            continue
        q, y = row.get("quarter"), row.get("year")
        upcoming.append(
            EarningsDate(
                day=day,
                hour=row.get("hour") or None,
                fiscal_quarter=f"Q{q} {y}" if q and y else None,
                eps_estimate=_opt_float(row.get("epsEstimate")),
                revenue_estimate=_opt_float(row.get("revenueEstimate")),
            )
        )
    return min(upcoming, key=lambda e: e.day) if upcoming else None


class FinnhubCompanyClient:
    """Profil, peers i kalendarz wyników z Finnhub. Bez klucza każda metoda zwraca brak danych."""

    def __init__(
        self, client: httpx.AsyncClient, api_key: str, base_url: str = "https://finnhub.io"
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def _call(self, path: str, params: dict[str, str]) -> Any:
        return await _get(
            self._client,
            f"{self._base_url}/api/v1{path}",
            params={**params, "token": self._api_key},
        )

    async def profile(self, ticker: str) -> FinnhubProfile | None:
        if not self.enabled:
            return None
        return parse_finnhub_profile(await self._call("/stock/profile2", {"symbol": ticker}))

    async def peers(self, ticker: str) -> list[str]:
        if not self.enabled:
            return []
        data = await self._call("/stock/peers", {"symbol": ticker})
        return [str(t).upper() for t in data] if isinstance(data, list) else []

    async def next_earnings(self, ticker: str, today: date) -> EarningsDate | None:
        if not self.enabled:
            return None
        data = await self._call(
            "/calendar/earnings",
            {
                "symbol": ticker,
                "from": today.isoformat(),
                "to": date.fromordinal(today.toordinal() + 200).isoformat(),
            },
        )
        return parse_finnhub_earnings(data, today)

    async def earnings_history(self, ticker: str) -> list[EarningsResult]:
        """Ostatnie kwartały: EPS rzeczywisty vs konsensus (darmowy plan: 4 kwartały)."""
        if not self.enabled:
            return []
        return parse_finnhub_earnings_history(
            await self._call("/stock/earnings", {"symbol": ticker})
        )
