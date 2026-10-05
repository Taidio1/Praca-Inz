from collections import defaultdict
from datetime import date
from typing import Any, Protocol
from uuid import UUID

import structlog

from src.core.errors import NotFoundError, ValidationError
from src.marketdata.fx import FxRate, FxRateError
from src.marketdata.providers import QuoteError
from src.marketdata.symbol_search import SymbolMatch
from src.schemas.assets import AssetType
from src.schemas.portfolio import (
    PortfolioPositionOut,
    PositionCreate,
    TransactionDeleteResult,
    TransactionOut,
    TransactionUpdate,
)
from src.services.mappers import asset_from_row, snapshot_from_row
from src.services.valuation import Lot, average_unit_cost, lot_from_tx, value_position

Row = dict[str, Any]

log = structlog.get_logger(__name__)

DEFAULT_BASE_CURRENCY = "PLN"


class AssetsRepo(Protocol):
    async def find_by_ticker(self, ticker: str, asset_type: str) -> Row | None: ...
    async def get(self, asset_id: str) -> Row | None: ...


class AssetsWriter(Protocol):
    async def create(
        self, ticker: str, name: str, asset_type: str, aliases: list[str], currency: str
    ) -> Row: ...


class AssetSearch(Protocol):
    async def lookup(self, ticker: str, asset_type: AssetType) -> SymbolMatch | None: ...


class QuoteCurrencies(Protocol):
    async def quote_currency(self, ticker: str, asset_type: AssetType) -> str: ...


class FxRates(Protocol):
    async def rate_on(self, base: str, quote: str, on: date) -> FxRate: ...
    async def rates_on(
        self, base: str, quote: str, days: list[date]
    ) -> dict[date, FxRate]: ...


class SettingsRepo(Protocol):
    async def get(self) -> Row | None: ...


class PortfolioRepo(Protocol):
    async def list_positions(self) -> list[Row]: ...
    async def list_all_transactions(self) -> list[Row]: ...
    async def get_position(self, position_id: str) -> Row | None: ...
    async def find_position(self, user_id: str, asset_id: str) -> Row | None: ...
    async def create_position(
        self, user_id: str, asset_id: str, quantity: float, avg_buy_price: float | None
    ) -> Row: ...
    async def update_position_aggregate(
        self, position_id: str, quantity: float, avg_buy_price: float | None
    ) -> Row: ...
    async def add_transaction(
        self, position_id: str, user_id: str, quantity: float,
        price: float | None, purchased_at: str,
        currency: str, fx_rate: float, fx_rate_date: str,
    ) -> Row: ...
    async def list_transactions(self, position_id: str) -> list[Row]: ...
    async def get_transaction(self, position_id: str, tx_id: str) -> Row | None: ...
    async def update_transaction(
        self, position_id: str, tx_id: str, quantity: float,
        price: float | None, purchased_at: str,
        currency: str, fx_rate: float, fx_rate_date: str,
    ) -> Row: ...
    async def delete_transaction(self, position_id: str, tx_id: str) -> bool: ...
    async def delete(self, position_id: str) -> bool: ...


class SnapshotsRepo(Protocol):
    async def latest_for_assets(self, asset_ids: list[str]) -> dict[str, Row]: ...


class LatestInsightsRepo(Protocol):
    async def latest_per_asset(self, asset_ids: list[str]) -> dict[str, Row]: ...


async def base_currency_of(settings: SettingsRepo) -> str:
    row = await settings.get()
    return str((row or {}).get("base_currency") or DEFAULT_BASE_CURRENCY)


class PortfolioService:
    def __init__(
        self,
        assets: AssetsRepo,
        assets_writer: AssetsWriter,
        asset_search: AssetSearch,
        portfolio: PortfolioRepo,
        snapshots: SnapshotsRepo,
        insights: LatestInsightsRepo,
        currencies: QuoteCurrencies,
        fx: FxRates,
        settings: SettingsRepo,
    ) -> None:
        self._assets = assets
        self._assets_writer = assets_writer
        self._asset_search = asset_search
        self._portfolio = portfolio
        self._snapshots = snapshots
        self._insights = insights
        self._currencies = currencies
        self._fx = fx
        self._settings = settings

    async def list_positions(self) -> list[PortfolioPositionOut]:
        rows = await self._portfolio.list_positions()
        if not rows:
            return []
        asset_ids = [row["assets"]["id"] for row in rows]
        snaps = await self._snapshots.latest_for_assets(asset_ids)
        latest = await self._insights.latest_per_asset(asset_ids)
        lots_by_position: dict[str, list[Lot]] = defaultdict(list)
        for tx in await self._portfolio.list_all_transactions():
            lots_by_position[tx["position_id"]].append(lot_from_tx(tx))
        base = await base_currency_of(self._settings)
        fx = await self._fx_tables(
            base, [(row["assets"]["currency"], lots_by_position[row["id"]]) for row in rows]
        )
        return [
            self._build_position(
                row["id"], row["assets"], row["quantity"], row.get("avg_buy_price"),
                lots_by_position[row["id"]], snaps, latest, base, fx,
            )
            for row in rows
        ]

    async def add_position(
        self, user_id: str, payload: PositionCreate
    ) -> PortfolioPositionOut:
        asset = await self._assets.find_by_ticker(payload.ticker, payload.asset_type)
        if asset is None:
            match = await self._asset_search.lookup(payload.ticker, payload.asset_type)
            if match is None:
                raise ValidationError(
                    f"Nieznany ticker: {payload.ticker} ({payload.asset_type})"
                )
            try:
                quote_currency = await self._currencies.quote_currency(
                    match.ticker, match.asset_type
                )
            except QuoteError as exc:
                raise ValidationError(str(exc)) from exc
            asset = await self._assets_writer.create(
                ticker=match.ticker,
                name=match.name,
                asset_type=match.asset_type,
                aliases=[match.name.lower(), match.ticker.lower()],
                currency=quote_currency,
            )
        tx_currency = payload.currency or asset["currency"]
        fx = await self._tx_rate(tx_currency, asset["currency"], payload.purchased_at)
        position = await self._portfolio.find_position(user_id, asset["id"])
        if position is None:
            position = await self._portfolio.create_position(
                user_id, asset["id"], payload.quantity,
                payload.price * fx.rate if payload.price is not None else None,
            )
        await self._portfolio.add_transaction(
            position["id"], user_id, payload.quantity,
            payload.price, payload.purchased_at.isoformat(),
            tx_currency, fx.rate, fx.rate_date.isoformat(),
        )
        return await self._refresh_position(position["id"], asset)

    async def list_transactions(self, position_id: str) -> list[TransactionOut]:
        position = await self._portfolio.get_position(position_id)
        if position is None:
            raise NotFoundError("Pozycja nie istnieje")
        rows = await self._portfolio.list_transactions(position_id)
        return [self._tx_out(r) for r in rows]

    async def update_transaction(
        self, position_id: str, tx_id: str, payload: TransactionUpdate
    ) -> PortfolioPositionOut:
        position = await self._portfolio.get_position(position_id)
        if position is None:
            raise NotFoundError("Pozycja nie istnieje")
        tx = await self._portfolio.get_transaction(position_id, tx_id)
        if tx is None:
            raise NotFoundError("Transakcja nie istnieje")
        asset = await self._assets.get(position["asset_id"])
        if asset is None:
            raise NotFoundError("Aktywo nie istnieje")
        tx_currency = payload.currency or tx.get("currency") or asset["currency"]
        fx = await self._tx_rate(tx_currency, asset["currency"], payload.purchased_at)
        await self._portfolio.update_transaction(
            position_id, tx_id, payload.quantity, payload.price,
            payload.purchased_at.isoformat(),
            tx_currency, fx.rate, fx.rate_date.isoformat(),
        )
        return await self._refresh_position(position_id, asset)

    async def delete_transaction(self, position_id: str, tx_id: str) -> TransactionDeleteResult:
        position = await self._portfolio.get_position(position_id)
        if position is None:
            raise NotFoundError("Pozycja nie istnieje")
        tx = await self._portfolio.get_transaction(position_id, tx_id)
        if tx is None:
            raise NotFoundError("Transakcja nie istnieje")
        await self._portfolio.delete_transaction(position_id, tx_id)
        transactions = await self._portfolio.list_transactions(position_id)
        if not transactions:
            await self._portfolio.delete(position_id)
            return TransactionDeleteResult(position_removed=True)
        quantity, avg_price = self._aggregate(transactions)
        await self._portfolio.update_position_aggregate(position_id, quantity, avg_price)
        return TransactionDeleteResult(position_removed=False)

    async def remove_position(self, position_id: str) -> None:
        deleted = await self._portfolio.delete(position_id)
        if not deleted:
            raise NotFoundError("Pozycja nie istnieje")

    async def _refresh_position(self, position_id: str, asset: Row) -> PortfolioPositionOut:
        """Przelicza agregat pozycji z transakcji i zwraca ją wycenioną."""
        transactions = await self._portfolio.list_transactions(position_id)
        quantity, avg_price = self._aggregate(transactions)
        row = await self._portfolio.update_position_aggregate(position_id, quantity, avg_price)
        lots = [lot_from_tx(t) for t in transactions]
        snaps = await self._snapshots.latest_for_assets([asset["id"]])
        latest = await self._insights.latest_per_asset([asset["id"]])
        base = await base_currency_of(self._settings)
        fx = await self._fx_tables(base, [(asset["currency"], lots)])
        return self._build_position(
            row["id"], asset, row["quantity"], row.get("avg_buy_price"),
            lots, snaps, latest, base, fx,
        )

    async def _tx_rate(self, tx_currency: str, quote_currency: str, on: date) -> FxRate:
        """Kurs waluty transakcji → waluty notowania z dnia zakupu (historyczny, nie bieżący)."""
        try:
            return await self._fx.rate_on(tx_currency, quote_currency, on)
        except FxRateError as exc:
            raise ValidationError(
                f"Brak kursu {tx_currency}/{quote_currency} na {on.isoformat()}"
            ) from exc

    async def _fx_tables(
        self, base: str, positions: list[tuple[str, list[Lot]]]
    ) -> dict[str, dict[date, FxRate]]:
        """Kursy waluta notowania → bazowa: na dziś i na każdy dzień zakupu.
        Niedostępne źródło kursów nie wywraca listy — pozycja zostaje bez wartości bazowych."""
        today = date.today()
        days_by_currency: dict[str, set[date]] = defaultdict(set)
        for currency, lots in positions:
            days_by_currency[currency].add(today)
            days_by_currency[currency].update(lot.purchased_at for lot in lots)
        tables: dict[str, dict[date, FxRate]] = {}
        for currency, days in days_by_currency.items():
            try:
                tables[currency] = await self._fx.rates_on(currency, base, sorted(days))
            except FxRateError as exc:
                log.warning("fx_unavailable", pair=f"{currency}/{base}", reason=str(exc))
                tables[currency] = {}
        return tables

    @staticmethod
    def _aggregate(transactions: list[Row]) -> tuple[float, float | None]:
        """Suma ilości + średnia ważona cen w walucie notowania; transakcje bez ceny
        pomijane w średniej."""
        total_qty = sum(float(t["quantity"]) for t in transactions)
        return total_qty, average_unit_cost(lot_from_tx(t) for t in transactions)

    @staticmethod
    def _tx_out(r: Row) -> TransactionOut:
        price = r.get("price")
        fx_rate = float(r["fx_rate"])
        return TransactionOut(
            id=UUID(r["id"]),
            quantity=r["quantity"],
            price=price,
            currency=r["currency"],
            fx_rate=fx_rate,
            fx_rate_date=r["fx_rate_date"],
            price_in_quote=float(price) * fx_rate if price is not None else None,
            purchased_at=r["purchased_at"],
            created_at=r["created_at"],
        )

    @staticmethod
    def _build_position(
        position_id: str,
        asset: Row,
        quantity: float,
        avg_buy_price: float | None,
        lots: list[Lot],
        snaps: dict[str, Row],
        latest: dict[str, Row],
        base: str,
        fx: dict[str, dict[date, FxRate]],
    ) -> PortfolioPositionOut:
        sentiment = latest.get(asset["id"])
        snap = snaps.get(asset["id"])
        price: float | None = snap.get("price") if snap else None
        table = fx.get(asset["currency"], {})
        valuation = value_position(
            float(quantity), float(price) if price is not None else None,
            lots, table.get(date.today()), table,
        )
        return PortfolioPositionOut(
            id=UUID(position_id),
            asset=asset_from_row(asset),
            quantity=quantity,
            currency=asset["currency"],
            base_currency=base,
            avg_buy_price=avg_buy_price,
            current_value_quote=valuation.current_value_quote,
            current_value=valuation.current_value,
            cost_basis=valuation.cost_basis,
            profit_loss_value=valuation.profit_loss_value,
            profit_loss_pct=valuation.profit_loss_pct,
            profit_loss_price=valuation.profit_loss_price,
            profit_loss_fx=valuation.profit_loss_fx,
            fx_rate=valuation.fx_rate,
            fx_rate_date=valuation.fx_rate_date,
            fx_source=valuation.fx_source,
            snapshot=snapshot_from_row(snap),
            latest_sentiment_score=sentiment.get("sentiment_score") if sentiment else None,
            latest_sentiment_label=sentiment.get("sentiment_label") if sentiment else None,
        )
