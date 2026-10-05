"""Dzienna wycena całego portfela: wartość rynkowa vs kapitał zainwestowany.

Stan posiadania odtwarzany z transakcji (a nie z agregatu pozycji), dzięki czemu
punkt sprzed dokupienia pokazuje ilość faktycznie posiadaną tamtego dnia.

Wszystko w walucie bazowej użytkownika: wartość punktu po kursie z danego dnia,
koszt transakcji po kursie z dnia zakupu (stały w czasie).
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any, Protocol

import structlog

from src.marketdata.fx import FxRate, FxRateError
from src.marketdata.historical import HistoricalPrice, HistoricalPriceError
from src.schemas.assets import AssetType
from src.schemas.portfolio import PortfolioHistoryOut, PortfolioHistoryPoint
from src.services.portfolio import FxRates, SettingsRepo, base_currency_of

log = structlog.get_logger(__name__)

Row = dict[str, Any]


class PortfolioRepo(Protocol):
    async def list_positions(self) -> list[Row]: ...
    async def list_all_transactions(self) -> list[Row]: ...


class HistoricalPrices(Protocol):
    async def price_series(
        self, ticker: str, asset_type: AssetType, days: int
    ) -> list[HistoricalPrice]: ...


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _daily_closes(series: list[HistoricalPrice], window: list[date]) -> dict[date, float]:
    """Close na każdy dzień okna: weekend/święto → ostatnie notowanie,
    dni przed początkiem serii → pierwsze znane notowanie."""
    ordered = sorted(series, key=lambda hp: hp.price_date)
    resolved: dict[date, float] = {}
    idx = 0
    last = ordered[0].price
    for day in window:
        while idx < len(ordered) and ordered[idx].price_date <= day:
            last = ordered[idx].price
            idx += 1
        resolved[day] = last
    return resolved


class PortfolioHistoryService:
    def __init__(
        self,
        portfolio: PortfolioRepo,
        prices: HistoricalPrices,
        fx: FxRates,
        settings: SettingsRepo,
    ) -> None:
        self._portfolio = portfolio
        self._prices = prices
        self._fx = fx
        self._settings = settings

    async def history(self, days: int) -> PortfolioHistoryOut:
        assets_by_position = {
            row["id"]: row["assets"]
            for row in await self._portfolio.list_positions()
            if row.get("assets")
        }
        base = await base_currency_of(self._settings)
        if not assets_by_position:
            return PortfolioHistoryOut(points=[], base_currency=base)

        assets = {asset["id"]: asset for asset in assets_by_position.values()}
        closes, skipped = await self._collect_closes(assets.values(), days)
        if not closes:
            return PortfolioHistoryOut(points=[], skipped_tickers=skipped, base_currency=base)

        transactions = [
            tx
            for tx in await self._portfolio.list_all_transactions()
            if assets_by_position.get(tx["position_id"], {}).get("id") in closes
        ]
        if not transactions:
            return PortfolioHistoryOut(points=[], skipped_tickers=skipped, base_currency=base)

        today = date.today()
        first_purchase = min(_as_date(tx["purchased_at"]) for tx in transactions)
        start = max(today - timedelta(days=days - 1), first_purchase)
        if start > today:
            return PortfolioHistoryOut(points=[], skipped_tickers=skipped, base_currency=base)
        window = [start + timedelta(days=i) for i in range((today - start).days + 1)]

        # Kursy waluta notowania → bazowa na każdy dzień okna i każdy dzień zakupu.
        days_by_currency: dict[str, set[date]] = defaultdict(set)
        for tx in transactions:
            currency = assets_by_position[tx["position_id"]]["currency"]
            days_by_currency[currency].update(window)
            days_by_currency[currency].add(_as_date(tx["purchased_at"]))
        fx_tables: dict[str, dict[date, FxRate]] = {}
        for currency, fx_days in days_by_currency.items():
            try:
                fx_tables[currency] = await self._fx.rates_on(currency, base, sorted(fx_days))
            except FxRateError as exc:
                log.warning("fx_unavailable", pair=f"{currency}/{base}", reason=str(exc))
                fx_tables[currency] = {}

        # Aktywo bez kompletu kursów wypada z wykresu, tak jak aktywo bez notowań.
        fx_skipped: set[str] = set()
        for tx in transactions:
            asset = assets_by_position[tx["position_id"]]
            table = fx_tables[asset["currency"]]
            needed = [*window, _as_date(tx["purchased_at"])]
            if any(day not in table for day in needed):
                fx_skipped.add(asset["id"])
        if fx_skipped:
            skipped = sorted(
                {*skipped, *(assets[a]["ticker"] for a in fx_skipped)}
            )
            transactions = [
                tx for tx in transactions
                if assets_by_position[tx["position_id"]]["id"] not in fx_skipped
            ]
            if not transactions:
                return PortfolioHistoryOut(
                    points=[], skipped_tickers=skipped, base_currency=base
                )
        currency_of = {a["id"]: a["currency"] for a in assets.values()}

        prices = {
            asset_id: _daily_closes(series, window) for asset_id, series in closes.items()
        }
        ordered = sorted(
            (
                (
                    _as_date(tx["purchased_at"]),
                    assets_by_position[tx["position_id"]]["id"],
                    float(tx["quantity"]),
                    tx.get("price"),
                    float(tx.get("fx_rate") or 1.0),
                )
                for tx in transactions
            ),
            key=lambda tx: tx[0],
        )

        held: dict[str, float] = {}
        cost = 0.0
        idx = 0
        points: list[PortfolioHistoryPoint] = []
        for day in window:
            while idx < len(ordered) and ordered[idx][0] <= day:
                bought, asset_id, quantity, price, tx_fx = ordered[idx]
                held[asset_id] = held.get(asset_id, 0.0) + quantity
                if price is not None:
                    to_base = fx_tables[currency_of[asset_id]][bought].rate
                    cost += quantity * float(price) * tx_fx * to_base
                idx += 1
            value = sum(
                qty * prices[asset_id][day] * fx_tables[currency_of[asset_id]][day].rate
                for asset_id, qty in held.items()
            )
            points.append(
                PortfolioHistoryPoint(
                    point_date=day, value=round(value, 2), cost=round(cost, 2)
                )
            )

        used = [
            fx_tables[currency_of[asset_id]][today]
            for asset_id in held
            if currency_of[asset_id] != base
        ]
        return PortfolioHistoryOut(
            points=points,
            skipped_tickers=skipped,
            base_currency=base,
            fx_rate_date=max((fx.rate_date for fx in used), default=None),
            fx_sources=sorted({fx.source for fx in used}),
        )

    async def _collect_closes(
        self, assets: Iterable[Row], days: int
    ) -> tuple[dict[str, list[HistoricalPrice]], list[str]]:
        """Aktywo bez notowań nie wywraca odpowiedzi — wypada z wyceny i z kosztu,
        a jego ticker wraca w skipped_tickers."""
        closes: dict[str, list[HistoricalPrice]] = {}
        skipped: list[str] = []
        for asset in assets:
            try:
                series = await self._prices.price_series(
                    asset["ticker"], asset["asset_type"], days
                )
            except HistoricalPriceError:
                series = []
            if series:
                closes[asset["id"]] = series
            else:
                skipped.append(asset["ticker"])
        return closes, sorted(skipped)
