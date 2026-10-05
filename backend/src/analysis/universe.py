"""Wybrane popularne spółki z USA (raportujące do SEC) pogrupowane branżowo.

Grupa wyznacza spółki porównawcze („vs peers"). Lista jest świadomie ręczna —
automatyczne grupowanie po kodzie SIC daje zbyt heterogeniczne zestawy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PopularCompany:
    ticker: str
    name: str
    group: str


GROUPS: dict[str, str] = {
    "bigtech": "Big Tech i oprogramowanie",
    "semis": "Półprzewodniki",
    "finance": "Finanse i płatności",
    "health": "Ochrona zdrowia",
    "consumer": "Konsumpcja",
    "energy": "Energia",
    "industrial": "Przemysł",
    "auto": "Motoryzacja",
}

_RAW: dict[str, list[tuple[str, str]]] = {
    "bigtech": [
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("GOOGL", "Alphabet"),
        ("AMZN", "Amazon"),
        ("META", "Meta Platforms"),
        ("ORCL", "Oracle"),
        ("CRM", "Salesforce"),
        ("ADBE", "Adobe"),
        ("NFLX", "Netflix"),
    ],
    "semis": [
        ("NVDA", "NVIDIA"),
        ("AMD", "Advanced Micro Devices"),
        ("INTC", "Intel"),
        ("AVGO", "Broadcom"),
        ("QCOM", "Qualcomm"),
        ("TXN", "Texas Instruments"),
        ("MU", "Micron Technology"),
    ],
    "finance": [
        ("JPM", "JPMorgan Chase"),
        ("BAC", "Bank of America"),
        ("WFC", "Wells Fargo"),
        ("GS", "Goldman Sachs"),
        ("MS", "Morgan Stanley"),
        ("V", "Visa"),
        ("MA", "Mastercard"),
    ],
    "health": [
        ("LLY", "Eli Lilly"),
        ("JNJ", "Johnson & Johnson"),
        ("UNH", "UnitedHealth"),
        ("MRK", "Merck"),
        ("ABBV", "AbbVie"),
        ("PFE", "Pfizer"),
    ],
    "consumer": [
        ("WMT", "Walmart"),
        ("COST", "Costco"),
        ("PG", "Procter & Gamble"),
        ("KO", "Coca-Cola"),
        ("PEP", "PepsiCo"),
        ("MCD", "McDonald's"),
        ("NKE", "Nike"),
        ("HD", "Home Depot"),
        ("SBUX", "Starbucks"),
    ],
    "energy": [("XOM", "ExxonMobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips")],
    "industrial": [
        ("CAT", "Caterpillar"),
        ("BA", "Boeing"),
        ("GE", "GE Aerospace"),
        ("HON", "Honeywell"),
        ("UPS", "UPS"),
    ],
    "auto": [("TSLA", "Tesla"), ("GM", "General Motors"), ("F", "Ford")],
}

POPULAR: list[PopularCompany] = [
    PopularCompany(ticker, name, group) for group, rows in _RAW.items() for ticker, name in rows
]
_BY_TICKER = {c.ticker: c for c in POPULAR}

MAX_PEERS = 6


def peers_of(ticker: str) -> list[str]:
    company = _BY_TICKER.get(ticker.upper())
    if company is None:
        return []
    return [c.ticker for c in POPULAR if c.group == company.group and c.ticker != company.ticker][
        :MAX_PEERS
    ]


def group_of(ticker: str) -> str | None:
    company = _BY_TICKER.get(ticker.upper())
    return GROUPS[company.group] if company else None
