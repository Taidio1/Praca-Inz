"""Wycena pozycji w walucie bazowej użytkownika.

Oznaczenia (X = kurs waluty notowania → waluty bazowej):
  wartość bieżąca = Q · P_teraz · X_teraz
  koszt           = Σ q_i · c_i · X_i         (c_i — cena zakupu w walucie notowania,
                                               X_i — kurs z dnia zakupu)
  efekt ceny      = Σ q_i · (P_teraz − c_i) · X_i
  efekt kursu     = Σ q_i · P_teraz · (X_teraz − X_i)
  zysk/strata     = efekt ceny + efekt kursu = wartość (części z ceną zakupu) − koszt

Transakcje bez ceny zakupu liczą się do wartości bieżącej, ale nie do kosztu ani wyniku.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from src.marketdata.fx import FxRate

Row = dict[str, Any]


@dataclass(frozen=True)
class Lot:
    quantity: float
    unit_cost: float | None  # cena zakupu w walucie notowania (price · fx_rate)
    purchased_at: date


@dataclass(frozen=True)
class PositionValuation:
    current_value_quote: float | None = None
    current_value: float | None = None
    cost_basis: float | None = None
    profit_loss_value: float | None = None
    profit_loss_pct: float | None = None
    profit_loss_price: float | None = None
    profit_loss_fx: float | None = None
    fx_rate: float | None = None
    fx_rate_date: date | None = None
    fx_source: str | None = None


def as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def lot_from_tx(tx: Row) -> Lot:
    price = tx.get("price")
    fx_rate = tx.get("fx_rate")
    unit_cost = (
        float(price) * float(fx_rate if fx_rate is not None else 1.0)
        if price is not None
        else None
    )
    return Lot(
        quantity=float(tx["quantity"]),
        unit_cost=unit_cost,
        purchased_at=as_date(tx["purchased_at"]),
    )


def average_unit_cost(lots: Iterable[Lot]) -> float | None:
    """Średnia ważona ceny zakupu w walucie notowania (transakcje bez ceny pominięte)."""
    priced = [lot for lot in lots if lot.unit_cost is not None]
    qty = sum(lot.quantity for lot in priced)
    if not qty:
        return None
    return sum(lot.quantity * (lot.unit_cost or 0.0) for lot in priced) / qty


def value_position(
    quantity: float,
    price: float | None,
    lots: list[Lot],
    fx_now: FxRate | None,
    fx_at: dict[date, FxRate],
) -> PositionValuation:
    value_quote = quantity * price if price is not None else None
    result = PositionValuation(
        current_value_quote=value_quote,
        current_value=(
            value_quote * fx_now.rate if value_quote is not None and fx_now is not None else None
        ),
        fx_rate=fx_now.rate if fx_now else None,
        fx_rate_date=fx_now.rate_date if fx_now else None,
        fx_source=fx_now.source if fx_now else None,
    )

    priced = [lot for lot in lots if lot.unit_cost is not None]
    if not priced or any(lot.purchased_at not in fx_at for lot in priced):
        return result

    cost = sum(
        lot.quantity * (lot.unit_cost or 0.0) * fx_at[lot.purchased_at].rate for lot in priced
    )
    if price is None or fx_now is None:
        return replace(result, cost_basis=cost)

    pl_price = sum(
        lot.quantity * (price - (lot.unit_cost or 0.0)) * fx_at[lot.purchased_at].rate
        for lot in priced
    )
    pl_fx = sum(
        lot.quantity * price * (fx_now.rate - fx_at[lot.purchased_at].rate) for lot in priced
    )
    pl = pl_price + pl_fx
    return replace(
        result,
        cost_basis=cost,
        profit_loss_value=pl,
        profit_loss_pct=pl / cost * 100 if cost else None,
        profit_loss_price=pl_price,
        profit_loss_fx=pl_fx,
    )
