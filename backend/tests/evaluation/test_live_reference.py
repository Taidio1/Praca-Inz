"""Walidacja obliczeń na danych rzeczywistych (sieć + FINNHUB_API_KEY).

Pomijana domyślnie. Uruchomienie:

    OPES_LIVE_VALIDATION=1 python -m pytest tests/evaluation -v

Domyślnie 12 spółek z różnych branż (~1,5 min, limit Finnhub). Wszystkie popularne:
OPES_VALIDATION_TICKERS=ALL, wybrane: OPES_VALIDATION_TICKERS=AAPL,KO,JPM
"""

import os

import pytest

from src.analysis import service as analysis_service
from src.analysis.universe import POPULAR
from tests.evaluation.reference import CompanyResult, collect, render_report, summarize

pytestmark = pytest.mark.skipif(
    os.environ.get("OPES_LIVE_VALIDATION") != "1",
    reason="Walidacja na żywo: ustaw OPES_LIVE_VALIDATION=1 (wymaga sieci i FINNHUB_API_KEY)",
)

# Przekrój branż: big tech, półprzewodniki, banki, płatności (wiele klas akcji),
# dywidendowe „królowe", energia (inne koncepty długu), przemysł, bez dywidendy.
DEFAULT_SAMPLE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "JPM",
    "V",
    "KO",
    "PG",
    "JNJ",
    "CVX",
    "CAT",
    "WMT",
    "TSLA",
]


def _tickers() -> list[str]:
    raw = os.environ.get("OPES_VALIDATION_TICKERS", "")
    if raw.upper() == "ALL":
        return [c.ticker for c in POPULAR]
    return [t.strip().upper() for t in raw.split(",") if t.strip()] or DEFAULT_SAMPLE


@pytest.fixture(scope="module")
async def results() -> list[CompanyResult]:
    analysis_service.clear_cache()
    data = await collect(_tickers())
    print("\n" + render_report(data))  # widoczne z `pytest -s`
    return data


async def test_all_companies_fetched(results: list[CompanyResult]) -> None:
    errors = {r.ticker: r.error for r in results if r.error}
    assert not errors, errors


async def test_metrics_agree_with_independent_reference(results: list[CompanyResult]) -> None:
    failed = [
        f"{s.check.label}: w tolerancji {s.share:.0%} (wymagane {s.check.min_share:.0%}), "
        f"mediana {s.median_dev}% (maks. {s.check.max_median_pct}%); odstające: {s.outliers}"
        for s in summarize(results)
        if not s.passed
    ]
    assert not failed, "\n".join(failed)


async def test_internal_consistency(results: list[CompanyResult]) -> None:
    failed = [
        f"{r.ticker}: {name} — {detail}"
        for r in results
        for name, ok, detail in r.consistency
        if not ok
    ]
    total = sum(len(r.consistency) for r in results)
    assert total > 0, "brak kontroli spójności — sprawdź dane wejściowe"
    assert not failed, "\n".join(failed)
