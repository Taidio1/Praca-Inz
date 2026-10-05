"""Mapowanie tickerów na symbole źródeł oraz normalizacja walut notowania.

Tickery zapisujemy w konwencji Finnhub/Yahoo: spółki z USA bez sufiksu (AAPL, BRK.B),
pozostałe giełdy z sufiksem rynku (CDR.WA — GPW, VOD.L — Londyn).
"""

# Sufiksy rynków w Yahoo/Finnhub. Kropka z innym sufiksem to klasa akcji (BRK.B → BRK-B).
EXCHANGE_SUFFIXES: frozenset[str] = frozenset(
    {
        "WA", "L", "IL", "DE", "F", "PA", "AS", "BR", "MI", "MC", "SW", "VI", "ST",
        "OL", "CO", "HE", "LS", "IR", "PR", "BD", "AT", "IS", "TO", "V", "NE", "CN",
        "AX", "NZ", "HK", "T", "KS", "KQ", "SS", "SZ", "NS", "BO", "SI", "TW", "SA",
        "MX", "TA", "JO",
    }
)

# Yahoo podaje część rynków w jednostkach drobnych (pensy, agory, centy).
_MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01),
    "GBX": ("GBP", 0.01),
    "ILA": ("ILS", 0.01),
    "ZAc": ("ZAR", 0.01),
    "ZAC": ("ZAR", 0.01),
}


def exchange_suffix(ticker: str) -> str | None:
    if "." not in ticker:
        return None
    suffix = ticker.rsplit(".", 1)[1].upper()
    return suffix if suffix in EXCHANGE_SUFFIXES else None


def yahoo_symbol(ticker: str) -> str:
    t = ticker.strip().upper()
    if exchange_suffix(t) is not None:
        return t
    return t.replace(".", "-")  # BRK.B → BRK-B


def normalize_currency(raw: str | None) -> tuple[str | None, float]:
    """Kod ISO waluty + mnożnik ceny (np. GBp → GBP, ×0.01). Nieznany format → (None, 1)."""
    if not raw:
        return None, 1.0
    if raw in _MINOR_UNITS:
        return _MINOR_UNITS[raw]
    code = raw.strip().upper()
    if len(code) != 3 or not code.isalpha():
        return None, 1.0
    return code, 1.0
