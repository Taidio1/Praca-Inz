"""GDELT DOC 2.0 (artlist): newsy po nazwie aktywa, PL dla GPW i EN dla reszty.

Limit API: ok. 1 zapytanie na 5 s. Przy przekroczeniu GDELT zwraca HTTP 429 (czasem 200)
z tekstem „Please limit requests…” zamiast JSON (zaobserwowane 2026-10-05). Po 429 nie
pytamy już w tym cyklu: każde kolejne zapytanie przedłuża blokadę.
"""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from src.sources.base import (
    FetchResult,
    Market,
    RateLimitedError,
    RawItem,
    SourceFetchError,
    SourceName,
    SourceState,
    TrackedAsset,
    since_for,
)
from src.sources.http import MinIntervalLimiter, get_with_retry

log = structlog.get_logger(__name__)

_LANG: dict[Market, str] = {
    "gpw": "polish",
    "crypto": "english",
    "us": "english",
    "eu_etf": "english",
}
_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(inc|corp|corporation|co|ltd|plc|s\.?a|ag|se|n\.?v|spa|ab|asa|oyj|"
    r"holdings?|group|ucits\s+etf|etf)\.?$",
    re.IGNORECASE,
)
_TIME_FMT = "%Y%m%d%H%M%S"
_SKIPPED = "HTTP 429 (pominięte w tym cyklu)"
# Indeks DOC aktualizuje się co ~15 min: nakładka = cykl + opóźnienie indeksu.
_OVERLAP = timedelta(minutes=30)


def gdelt_term(name: str) -> str | None:
    term = name.strip()
    while True:
        stripped = _LEGAL_SUFFIX.sub("", term).strip()
        if stripped == term:
            break
        term = stripped
    term = term.replace('"', "")
    return term if len(term) >= 3 else None


def parse_artlist(text: str) -> list[RawItem]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        if "limit requests" in text:
            raise RateLimitedError("GDELT: przekroczony limit zapytań") from exc
        raise SourceFetchError(f"GDELT: odpowiedź nie jest JSON-em: {text[:80]!r}") from exc
    if not isinstance(data, dict):
        raise SourceFetchError(f"GDELT: nieoczekiwany format odpowiedzi: {text[:80]!r}")
    items: list[RawItem] = []
    for art in data.get("articles") or []:
        url = (art.get("url") or "").strip()
        title = (art.get("title") or "").strip()
        if not url or not title:
            continue
        seen = art.get("seendate")
        try:
            published = (
                datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC) if seen else None
            )
        except ValueError as exc:
            raise SourceFetchError(f"GDELT: nieczytelna data {seen!r}") from exc
        items.append(
            RawItem(
                source="gdelt",
                url=url,
                title=title,
                snippet=None,
                published_at=published,
                raw={
                    "domain": art.get("domain"),
                    "language": art.get("language"),
                    "sourcecountry": art.get("sourcecountry"),
                },
            )
        )
    return items


def _query(terms: list[str], lang: str) -> str:
    phrases = " OR ".join(f'"{t}"' for t in terms)
    # GDELT dopuszcza nawiasy tylko wokół alternatywy OR
    return f"({phrases}) sourcelang:{lang}" if len(terms) > 1 else f"{phrases} sourcelang:{lang}"


class GdeltSource:
    name: SourceName = "gdelt"

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: MinIntervalLimiter,
        lookback_hours: int = 72,
        max_records: int = 75,
        chunk_size: int = 8,
        base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._lookback = lookback_hours
        self._max_records = max_records
        self._chunk = chunk_size
        self._base_url = base_url

    async def fetch(
        self, assets: list[TrackedAsset], states: Mapping[str, SourceState], now: datetime
    ) -> FetchResult:
        groups: dict[str, list[tuple[TrackedAsset, str]]] = {}
        for asset in assets:
            term = gdelt_term(asset.name)
            if term is not None:
                groups.setdefault(_LANG[asset.market], []).append((asset, term))

        result = FetchResult()
        rate_limited = False
        for lang, entries in groups.items():
            for start in range(0, len(entries), self._chunk):
                chunk = entries[start : start + self._chunk]
                keys = [f"gdelt:{a.id}" for a, _ in chunk]
                if rate_limited:
                    result.errors.update(dict.fromkeys(keys, _SKIPPED))
                    continue
                since = min(since_for(k, states, now, self._lookback, _OVERLAP) for k in keys)
                params = {
                    "query": _query([t for _, t in chunk], lang),
                    "mode": "artlist",
                    "format": "json",
                    "sort": "datedesc",
                    "maxrecords": str(self._max_records),
                    "startdatetime": since.astimezone(UTC).strftime(_TIME_FMT),
                    "enddatetime": now.astimezone(UTC).strftime(_TIME_FMT),
                }
                await self._limiter.wait()
                try:
                    # Bez ponowień: retry omijałby limiter 6 s; spróbuje następny cykl.
                    res = await get_with_retry(
                        self._http, self._base_url, params=params, attempts=1
                    )
                    if res.status_code >= 400:
                        raise SourceFetchError(f"HTTP {res.status_code}")
                    result.items.extend(parse_artlist(res.text))
                except SourceFetchError as exc:
                    log.warning("gdelt_failed", query=params["query"], reason=str(exc))
                    rate_limited = isinstance(exc, RateLimitedError)
                    for key in keys:
                        result.errors[key] = str(exc)
                    continue
                for key in keys:
                    result.ok[key] = (None, None)
        return result
