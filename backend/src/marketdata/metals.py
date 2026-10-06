"""Fizyczne metale szlachetne (typ aktywa 'commodity'): złoto i srebro.

Ilość pozycji to uncje trojańskie, cena to USD za uncję. Notowania bierzemy z Yahoo
z najbliższego kontraktu terminowego COMEX (GC=F, SI=F): publiczne źródło bez klucza,
które w praktyce odbiega od ceny spot o ułamek procenta. Yahoo nie publikuje już
par spot XAUUSD=X, a Stooq blokuje pobieranie wyzwaniem JavaScript.
"""

from dataclasses import dataclass
from datetime import date

from src.marketdata.historical import HistoricalPrice, HistoricalPriceError, YahooChartProvider
from src.marketdata.providers import Quote, QuoteError, YahooQuoteProvider


@dataclass(frozen=True)
class Metal:
    ticker: str
    name: str
    yahoo_symbol: str
    aliases: tuple[str, ...]


METALS: dict[str, Metal] = {
    "XAU": Metal(
        ticker="XAU",
        name="Złoto (fizyczne)",
        yahoo_symbol="GC=F",
        aliases=("złoto", "zloto", "gold", "xau", "kruszec", "bullion"),
    ),
    "XAG": Metal(
        ticker="XAG",
        name="Srebro (fizyczne)",
        yahoo_symbol="SI=F",
        aliases=("srebro", "silver", "xag"),
    ),
}

METAL_CURRENCY = "USD"


def metal(ticker: str) -> Metal | None:
    return METALS.get(ticker.strip().upper())


def _yahoo_symbol(ticker: str) -> str:
    found = metal(ticker)
    if found is None:
        raise QuoteError(f"Nieobsługiwany metal: {ticker.upper()}")
    return found.yahoo_symbol


class MetalQuoteProvider:
    """Bieżąca cena metalu za uncję (USD) z Yahoo."""

    def __init__(self, yahoo: YahooQuoteProvider) -> None:
        self._yahoo = yahoo

    async def quote(self, ticker: str) -> Quote:
        return await self._yahoo.quote(_yahoo_symbol(ticker))


class MetalPriceProvider:
    """Dzienne zamknięcia metalu za uncję (USD) z Yahoo."""

    def __init__(self, yahoo: YahooChartProvider) -> None:
        self._yahoo = yahoo

    async def price_on(self, ticker: str, on: date) -> HistoricalPrice:
        return await self._yahoo.price_on(self._symbol(ticker), on)

    async def price_series(self, ticker: str, days: int) -> list[HistoricalPrice]:
        return await self._yahoo.price_series(self._symbol(ticker), days)

    @staticmethod
    def _symbol(ticker: str) -> str:
        try:
            return _yahoo_symbol(ticker)
        except QuoteError as exc:
            raise HistoricalPriceError(str(exc)) from exc
