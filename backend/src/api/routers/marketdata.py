from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_fx_service,
    get_historical_price_service,
)
from src.core.errors import NotFoundError, ValidationError
from src.marketdata.fx import SUPPORTED_CURRENCIES, FxRateError, FxService
from src.marketdata.historical import HistoricalPriceError, HistoricalPriceService
from src.schemas.assets import AssetType
from src.schemas.marketdata import FxRateOut, PriceOnDateOut, PricePoint, PriceSeriesOut

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.get("/price-on-date")
async def price_on_date(
    ticker: Annotated[str, Query(min_length=1, max_length=16)],
    asset_type: AssetType,
    on: Annotated[date, Query(alias="date")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[HistoricalPriceService, Depends(get_historical_price_service)],
) -> PriceOnDateOut:
    """Dzienna cena zamknięcia dla daty zakupu (weekend → ostatni dzień notowań)."""
    if on > date.today():
        raise ValidationError("Data nie może być z przyszłości")
    try:
        hp = await service.price_on(ticker, asset_type, on)
    except HistoricalPriceError as exc:
        raise NotFoundError(
            f"Brak ceny dla {ticker.upper()} na {on.isoformat()}"
        ) from exc
    currency = "USD" if asset_type == "crypto" else hp.currency
    return PriceOnDateOut(
        price=hp.price, price_date=hp.price_date, source=hp.source, currency=currency
    )


@router.get("/price-series")
async def price_series(
    ticker: Annotated[str, Query(min_length=1, max_length=16)],
    asset_type: AssetType,
    days: Annotated[int, Query(ge=1, le=365)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[HistoricalPriceService, Depends(get_historical_price_service)],
) -> PriceSeriesOut:
    """Seria dziennych cen zamknięcia pod wykres (30/90/365 dni). Błąd źródła → puste points."""
    try:
        series = await service.price_series(ticker, asset_type, days)
    except HistoricalPriceError:
        return PriceSeriesOut(points=[])
    return PriceSeriesOut(
        points=[PricePoint(price_date=hp.price_date, price=hp.price) for hp in series],
        currency=series[-1].currency if series else None,
    )


@router.get("/fx-rate")
async def fx_rate(
    base: Annotated[str, Query(alias="from", min_length=3, max_length=3)],
    quote: Annotated[str, Query(alias="to", min_length=3, max_length=3)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[FxService, Depends(get_fx_service)],
    on: Annotated[date | None, Query(alias="date")] = None,
) -> FxRateOut:
    """Kurs średni: 1 jednostka waluty from = rate jednostek to, na dzień (domyślnie dziś).
    Weekend lub święto: ostatnia wcześniejsza publikacja."""
    base, quote = base.upper(), quote.upper()
    for code in (base, quote):
        if code not in SUPPORTED_CURRENCIES:
            raise ValidationError(f"Nieobsługiwana waluta: {code}")
    day = on or date.today()
    if day > date.today():
        raise ValidationError("Data nie może być z przyszłości")
    try:
        fx = await service.rate_on(base, quote, day)
    except FxRateError as exc:
        raise NotFoundError(f"Brak kursu {base}/{quote} na {day.isoformat()}") from exc
    return FxRateOut(
        base=base, quote=quote, rate=fx.rate, rate_date=fx.rate_date,
        requested_date=day, source=fx.source,
    )
