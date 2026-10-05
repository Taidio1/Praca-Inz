from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from pydantic import ValidationError as PydanticValidationError

from src.schemas.portfolio import PositionCreate, TransactionUpdate
from src.schemas.settings import SettingsUpdate


def test_position_create_valid() -> None:
    p = PositionCreate(ticker="btc", asset_type="crypto", quantity=0.5)
    assert p.ticker == "btc"
    assert p.quantity == 0.5


@pytest.mark.parametrize(
    "payload",
    [
        {"ticker": "", "asset_type": "crypto", "quantity": 1},
        {"ticker": "BTC", "asset_type": "forex", "quantity": 1},
        {"ticker": "BTC", "asset_type": "crypto", "quantity": 0},
        {"ticker": "BTC", "asset_type": "crypto", "quantity": -2},
    ],
)
def test_position_create_rejects_bad_payloads(payload: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError):
        PositionCreate(**payload)


def test_settings_update_threshold_bounds() -> None:
    assert SettingsUpdate(relevance_threshold=0.7).relevance_threshold == 0.7
    with pytest.raises(ValidationError):
        SettingsUpdate(relevance_threshold=1.5)


def test_position_create_rejects_non_positive_buy_price() -> None:
    with pytest.raises(ValidationError):
        PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=0)


def test_position_create_defaults_purchased_at_to_today_and_price_none() -> None:
    p = PositionCreate(ticker="BTC", asset_type="crypto", quantity=1)
    assert p.purchased_at == date.today()
    assert p.price is None


def test_position_create_accepts_past_date_and_price() -> None:
    p = PositionCreate(
        ticker="AAPL",
        asset_type="stock",
        quantity=2,
        price=215.75,
        purchased_at=date(2026, 7, 1),
    )
    assert p.price == 215.75
    assert p.purchased_at == date(2026, 7, 1)


def test_position_create_rejects_future_purchase_date() -> None:
    with pytest.raises(PydanticValidationError):
        PositionCreate(
            ticker="BTC",
            asset_type="crypto",
            quantity=1,
            purchased_at=date.today() + timedelta(days=1),
        )


def test_transaction_update_valid() -> None:
    tx = TransactionUpdate(quantity=1.5, price=50000.0, purchased_at=date(2026, 7, 1))
    assert tx.quantity == 1.5
    assert tx.price == 50000.0


def test_transaction_update_allows_null_price() -> None:
    tx = TransactionUpdate(quantity=1, price=None, purchased_at=date(2026, 7, 1))
    assert tx.price is None


def test_transaction_update_rejects_future_date() -> None:
    with pytest.raises(ValidationError):
        TransactionUpdate(quantity=1, price=1.0, purchased_at=date.today() + timedelta(days=1))


@pytest.mark.parametrize(
    "payload",
    [
        {"quantity": 0, "price": 1.0, "purchased_at": date(2026, 7, 1)},
        {"quantity": -1, "price": 1.0, "purchased_at": date(2026, 7, 1)},
        {"quantity": 1, "price": 0, "purchased_at": date(2026, 7, 1)},
        {"quantity": 1, "price": -5, "purchased_at": date(2026, 7, 1)},
    ],
)
def test_transaction_update_rejects_bad_payloads(payload: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError):
        TransactionUpdate(**payload)
