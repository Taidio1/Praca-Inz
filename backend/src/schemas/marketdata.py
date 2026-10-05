from datetime import date

from pydantic import BaseModel


class PriceOnDateOut(BaseModel):
    price: float
    price_date: date
    source: str
    currency: str | None = None  # waluta notowania


class FxRateOut(BaseModel):
    base: str
    quote: str
    rate: float  # 1 base = rate quote
    rate_date: date  # dzień publikacji kursu (weekend/święto → wcześniejszy)
    requested_date: date
    source: str


class PricePoint(BaseModel):
    price_date: date
    price: float


class PriceSeriesOut(BaseModel):
    points: list[PricePoint]
    currency: str | None = None
