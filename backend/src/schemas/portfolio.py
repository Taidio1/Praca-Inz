from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.marketdata.fx import SUPPORTED_CURRENCIES
from src.schemas.assets import AssetOut, AssetType, SnapshotOut

# Forma fizycznego metalu (moneta, sztabka, inna); tylko opis, wycena zawsze po cenie spot.
PhysicalForm = Literal["coin", "bar", "other"]


def _check_currency(v: str | None) -> str | None:
    if v is None:
        return None
    code = v.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Nieobsługiwana waluta: {v}")
    return code


class PositionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    asset_type: AssetType
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    # Waluta, w której podano cenę; brak = waluta notowania aktywa
    currency: str | None = None
    purchased_at: date = Field(default_factory=date.today)
    # Tylko asset_type="commodity": ilość w uncjach trojańskich, cena za uncję
    physical_form: PhysicalForm | None = None

    @field_validator("purchased_at")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Data zakupu nie może być z przyszłości")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_supported(cls, v: str | None) -> str | None:
        return _check_currency(v)


class TransactionOut(BaseModel):
    id: UUID
    quantity: float
    price: float | None = None  # w walucie transakcji
    currency: str
    fx_rate: float  # kurs waluty transakcji → waluty notowania z dnia zakupu
    fx_rate_date: date
    price_in_quote: float | None = None  # cena przeliczona na walutę notowania
    physical_form: PhysicalForm | None = None
    purchased_at: date
    created_at: datetime


class TransactionUpdate(BaseModel):
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    # Brak = bez zmiany waluty transakcji
    currency: str | None = None
    purchased_at: date

    @field_validator("purchased_at")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Data zakupu nie może być z przyszłości")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_supported(cls, v: str | None) -> str | None:
        return _check_currency(v)


class TransactionDeleteResult(BaseModel):
    position_removed: bool


class PortfolioHistoryPoint(BaseModel):
    point_date: date
    value: float  # w walucie bazowej, po kursie z danego dnia
    cost: float  # w walucie bazowej, po kursach z dni zakupu


class PortfolioHistoryOut(BaseModel):
    points: list[PortfolioHistoryPoint]
    skipped_tickers: list[str] = Field(default_factory=list)
    base_currency: str = "PLN"
    fx_rate_date: date | None = None  # najnowszy kurs użyty na wykresie
    fx_sources: list[str] = Field(default_factory=list)


class PortfolioPositionOut(BaseModel):
    id: UUID
    asset: AssetOut
    quantity: float
    currency: str | None = None  # waluta notowania (cena, średnia cena zakupu)
    base_currency: str | None = None  # waluta wartości i wyniku
    avg_buy_price: float | None = None  # w walucie notowania
    current_value_quote: float | None = None
    current_value: float | None = None  # w walucie bazowej
    cost_basis: float | None = None  # w walucie bazowej, po kursach z dni zakupu
    profit_loss_value: float | None = None  # w walucie bazowej
    profit_loss_pct: float | None = None
    profit_loss_price: float | None = None  # część wyniku ze zmiany ceny
    profit_loss_fx: float | None = None  # część wyniku ze zmiany kursu
    fx_rate: float | None = None  # bieżący kurs waluty notowania → bazowej
    fx_rate_date: date | None = None
    fx_source: str | None = None
    snapshot: SnapshotOut | None = None
    latest_sentiment_score: float | None = None
    latest_sentiment_label: str | None = None
