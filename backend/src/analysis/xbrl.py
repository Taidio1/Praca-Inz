"""Parsowanie SEC companyfacts (XBRL) do wartości TTM, stanów bilansowych i serii rocznych.

Spółki zmieniają z czasem koncepty (np. Apple: SalesRevenueNet → RevenueFrom...),
więc każdy wskaźnik ma listę kandydatów scalanych z priorytetem. Kwartał Q4 nie jest
raportowany osobno (siedzi w 10-K), dlatego TTM liczymy jako:
    ostatni rok obrotowy + bieżący YTD − YTD sprzed roku.
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
_ANNUAL_MIN_DAYS = 350
_ANNUAL_MAX_DAYS = 380
_DATE_SLACK_DAYS = 7
# Wartość starsza niż tyle względem ostatniego raportu spółki = koncept porzucony.
_STALE_FLOW_DAYS = 400
_STALE_INSTANT_DAYS = 120
_STALE_SHARES_DAYS = 200


@dataclass(frozen=True)
class Fact:
    start: date | None
    end: date
    val: float
    filed: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days if self.start else 0


# Koncepty w kolejności priorytetu — pierwszy kandydat wygrywa dla tego samego okresu.
FLOW_CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "dep_amort": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    # Gotówka wypłacona akcjonariuszom (rachunek przepływów) — podstawa payout i pokrycia FCF
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
    ],
}

INSTANT_CONCEPTS: dict[str, list[str]] = {
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "inventory": ["InventoryNet"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "lt_debt_total": [
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
        # Chevron i in.: dług łącznie z bieżącą częścią i leasingiem finansowym
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    ],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent"],
    "lt_debt_current": ["LongTermDebtCurrent"],
    "commercial_paper": ["CommercialPaper"],
    "short_term_borrowings": ["ShortTermBorrowings"],
}


def _parse_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _concept_facts(gaap: dict[str, Any], concept: str, unit: str) -> list[Fact]:
    node = gaap.get(concept)
    if not node:
        return []
    out = []
    for row in (node.get("units") or {}).get(unit) or []:
        if row.get("form") not in _FORMS:
            continue
        end = _parse_date(row.get("end"))
        filed = _parse_date(row.get("filed"))
        if end is None or filed is None or row.get("val") is None:
            continue
        start = _parse_date(row["start"]) if row.get("start") else None
        out.append(Fact(start=start, end=end, val=float(row["val"]), filed=filed))
    return out


def merged_facts(gaap: dict[str, Any], concepts: list[str], unit: str = "USD") -> list[Fact]:
    """Scala fakty wielu konceptów; dla tego samego okresu wygrywa wyższy priorytet,
    a w obrębie konceptu — najpóźniej złożony (korekty w kolejnych raportach)."""
    by_period: dict[tuple[date | None, date], tuple[int, Fact]] = {}
    for prio, concept in enumerate(concepts):
        for f in _concept_facts(gaap, concept, unit):
            key = (f.start, f.end)
            cur = by_period.get(key)
            if cur is None or prio < cur[0] or (prio == cur[0] and f.filed > cur[1].filed):
                by_period[key] = (prio, f)
    return sorted((f for _, f in by_period.values()), key=lambda f: (f.end, f.days))


def _close(a: date, b: date, slack: int = _DATE_SLACK_DAYS) -> bool:
    return abs((a - b).days) <= slack


def annual_facts(facts: list[Fact]) -> list[Fact]:
    """Pełne lata obrotowe, po jednym na rok kalendarzowy końca okresu."""
    by_year: dict[int, Fact] = {}
    for f in facts:
        if f.start and _ANNUAL_MIN_DAYS <= f.days <= _ANNUAL_MAX_DAYS:
            by_year[f.end.year] = f  # posortowane po end — zostaje najpóźniejszy
    return [by_year[y] for y in sorted(by_year)]


def ttm(facts: list[Fact], as_of: date) -> float | None:
    annual = annual_facts(facts)
    if not annual:
        return None
    last = annual[-1]
    if (as_of - last.end).days > _STALE_FLOW_DAYS:
        return None
    fy_start = last.end + timedelta(days=1)
    ytd = [
        f
        for f in facts
        if f.start and f.end > last.end and _close(f.start, fy_start) and f.days < _ANNUAL_MIN_DAYS
    ]
    if not ytd:
        return last.val
    cur = max(ytd, key=lambda f: f.end)
    assert last.start is not None
    prior = [
        f for f in facts if f.start and _close(f.start, last.start) and abs(f.days - cur.days) <= 10
    ]
    if not prior:
        return last.val
    return last.val + cur.val - prior[-1].val


def quarterly_values(facts: list[Fact]) -> dict[date, float]:
    """Wartości kwartalne (3 mies.) po dacie końca kwartału.

    Q4 rzadko jest raportowany osobno (siedzi w 10-K), więc go wyprowadzamy:
    rok obrotowy − narastająco 9 miesięcy tego samego roku."""
    out = {f.end: f.val for f in facts if f.start and 80 <= f.days <= 100}
    for year in annual_facts(facts):
        if year.end in out or year.start is None:
            continue
        nine_months = [
            f
            for f in facts
            if f.start and _close(f.start, year.start) and 260 <= f.days <= 285 and f.end < year.end
        ]
        if nine_months:
            out[year.end] = year.val - max(nine_months, key=lambda f: f.end).val
    return dict(sorted(out.items()))


_QUARTER_FP = {"Q1": 1, "Q2": 2, "Q3": 3, "FY": 4}


def fiscal_quarter_ends(gaap: dict[str, Any], concepts: list[str]) -> dict[str, date]:
    """Etykieta kwartału fiskalnego („Q2 2027") → data końca kwartału wg spółki.

    Pola fy/fp opisują raport, a nie każdy fakt (raport zawiera też okresy porównawcze),
    więc etykietę dostaje tylko najpóźniejszy okres z danego raportu (accn)."""
    newest_by_filing: dict[str, tuple[date, int, str]] = {}
    for concept in concepts:
        for row in ((gaap.get(concept) or {}).get("units") or {}).get("USD") or []:
            fp, fy, accn = row.get("fp"), row.get("fy"), row.get("accn")
            if fp not in _QUARTER_FP or not fy or not accn or row.get("form") not in _FORMS:
                continue
            end = _parse_date(row.get("end"))
            if end is None:
                continue
            cur = newest_by_filing.get(accn)
            if cur is None or end > cur[0]:
                newest_by_filing[accn] = (end, int(fy), fp)
    return {f"Q{_QUARTER_FP[fp]} {fy}": end for end, fy, fp in newest_by_filing.values()}


def latest_instant(facts: list[Fact], as_of: date) -> float | None:
    inst = [f for f in facts if f.start is None]
    if not inst:
        return None
    last = inst[-1]
    if (as_of - last.end).days > _STALE_INSTANT_DAYS:
        return None
    return last.val


def instant_at(facts: list[Fact], on: date) -> float | None:
    for f in reversed(facts):
        if f.start is None and _close(f.end, on):
            return f.val
    return None


@dataclass
class Fundamentals:
    """Jeden przekrój danych finansowych (TTM albo rok obrotowy). None = brak danych."""

    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    ocf: float | None = None
    fcf: float | None = None
    interest_expense: float | None = None
    equity: float | None = None
    assets: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None
    cash: float | None = None
    debt: float | None = None
    shares: float | None = None
    # Data złożenia raportu z liczbą akcji — splity późniejsze niż ta data wymagają korekty.
    shares_filed: date | None = None
    dividends_paid: float | None = None


def split_adjusted(f: Fundamentals, splits: list[tuple[date, float]]) -> Fundamentals:
    """Liczba akcji w jednostkach po wszystkich późniejszych splitach (jak ceny z Yahoo)."""
    if f.shares is None or f.shares_filed is None:
        return f
    factor = 1.0
    for day, ratio in splits:
        if day > f.shares_filed and ratio > 0:
            factor *= ratio
    return f if factor == 1.0 else replace(f, shares=f.shares * factor)


def _sum_opt(*vals: float | None) -> float | None:
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _debt(inst: dict[str, float | None]) -> float | None:
    long_term = inst.get("lt_debt_total")
    if long_term is None:
        long_term = _sum_opt(inst.get("lt_debt_noncurrent"), inst.get("lt_debt_current"))
    return _sum_opt(long_term, inst.get("commercial_paper"), inst.get("short_term_borrowings"))


def _assemble(flows: dict[str, float | None], inst: dict[str, float | None]) -> Fundamentals:
    rev = flows.get("revenue")
    gp = flows.get("gross_profit")
    if gp is None and rev is not None and flows.get("cost_of_revenue") is not None:
        gp = rev - flows["cost_of_revenue"]  # type: ignore[operator]
    op = flows.get("operating_income")
    da = flows.get("dep_amort")
    ocf = flows.get("ocf")
    capex = flows.get("capex")
    return Fundamentals(
        revenue=rev,
        gross_profit=gp,
        operating_income=op,
        net_income=flows.get("net_income"),
        ebitda=op + da if op is not None and da is not None else None,
        ocf=ocf,
        fcf=ocf - capex if ocf is not None and capex is not None else None,
        interest_expense=flows.get("interest_expense"),
        dividends_paid=flows.get("dividends_paid"),
        equity=inst.get("equity"),
        assets=inst.get("assets"),
        current_assets=inst.get("current_assets"),
        current_liabilities=inst.get("current_liabilities"),
        inventory=inst.get("inventory"),
        cash=inst.get("cash"),
        debt=_debt(inst),
    )


@dataclass
class CompanyFinancials:
    entity_name: str
    as_of: date  # koniec ostatniego okresu sprawozdawczego
    ttm: Fundamentals
    annual: dict[int, Fundamentals]  # rok końca roku obrotowego → dane
    fiscal_year_ends: dict[int, date]
    quarterly_revenue: dict[date, float] = field(default_factory=dict)
    quarter_ends: dict[str, date] = field(default_factory=dict)  # "Q2 2027" → koniec kwartału


def parse_companyfacts(data: dict[str, Any]) -> CompanyFinancials:
    facts = data.get("facts") or {}
    gaap: dict[str, Any] = facts.get("us-gaap") or {}
    dei: dict[str, Any] = facts.get("dei") or {}

    flows = {k: merged_facts(gaap, c) for k, c in FLOW_CONCEPTS.items()}
    insts = {k: merged_facts(gaap, c) for k, c in INSTANT_CONCEPTS.items()}

    anchors = flows["revenue"] or flows["net_income"]
    # Banki potrafią porzucić koncept przychodów w 10-Q — data raportu z obu źródeł.
    as_of = max((f.end for f in flows["revenue"] + flows["net_income"]), default=date.min)

    ttm_flows = {k: ttm(v, as_of) for k, v in flows.items()}
    ttm_inst = {k: latest_instant(v, as_of) for k, v in insts.items()}
    current = _assemble(ttm_flows, ttm_inst)

    # Liczba akcji z okładki raportu (dei) — tylko świeża. Spółki z kilkoma klasami akcji
    # (np. Visa, Mastercard, Nike) raportują ją wymiarowo per klasa, czego companyfacts nie
    # zawiera; zostaje wtedy wartość sprzed lat, która zaniżałaby kapitalizację wielokrotnie.
    shares_facts = _concept_facts(dei, "EntityCommonStockSharesOutstanding", "shares")
    if shares_facts:
        latest_shares = max(shares_facts, key=lambda f: (f.end, f.filed))
        if abs((latest_shares.end - as_of).days) <= _STALE_SHARES_DAYS:
            current.shares, current.shares_filed = latest_shares.val, latest_shares.filed
    all_diluted = merged_facts(gaap, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
    if current.shares is None and all_diluted:
        # Rozwodniona średnia z najnowszego okresu — dla wielu klas liczona w ekwiwalencie
        # akcji podstawowej, czyli właściwa podstawa kapitalizacji.
        newest = max(all_diluted, key=lambda f: (f.end, f.filed))
        if (as_of - newest.end).days <= _STALE_SHARES_DAYS:
            current.shares, current.shares_filed = newest.val, newest.filed
    diluted = annual_facts(all_diluted)
    diluted_by_year = {f.end.year: f for f in diluted}

    annual_flows = {k: {f.end.year: f.val for f in annual_facts(v)} for k, v in flows.items()}
    annual: dict[int, Fundamentals] = {}
    fy_ends: dict[int, date] = {}
    for anchor in annual_facts(anchors):
        year = anchor.end.year
        fy_ends[year] = anchor.end
        year_flows = {k: by_year.get(year) for k, by_year in annual_flows.items()}
        year_inst = {k: instant_at(v, anchor.end) for k, v in insts.items()}
        fund = _assemble(year_flows, year_inst)
        if year in diluted_by_year:
            fund.shares = diluted_by_year[year].val
            fund.shares_filed = diluted_by_year[year].filed
        annual[year] = fund

    return CompanyFinancials(
        entity_name=str(data.get("entityName") or ""),
        as_of=as_of,
        ttm=current,
        annual=annual,
        fiscal_year_ends=fy_ends,
        quarterly_revenue=quarterly_values(flows["revenue"]),
        quarter_ends=fiscal_quarter_ends(gaap, FLOW_CONCEPTS["revenue"]),
    )
