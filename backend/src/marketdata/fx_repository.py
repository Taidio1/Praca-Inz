from datetime import date
from typing import Any

from supabase import AsyncClient

from src.marketdata.fx import FxRate

Row = dict[str, Any]


class FxRepository:
    """Cache kursów historycznych w tabeli fx_rates — zapis wymaga klienta service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_rates(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]:
        if not days:
            return {}
        res = await (
            self._client.table("fx_rates")
            .select("rate_date, rate, effective_date, source")
            .eq("base", base)
            .eq("quote", quote)
            .gte("rate_date", min(days).isoformat())
            .lte("rate_date", max(days).isoformat())
            .execute()
        )
        wanted = set(days)
        out: dict[date, FxRate] = {}
        for row in res.data or []:
            day = date.fromisoformat(str(row["rate_date"]))
            if day in wanted:
                out[day] = FxRate(
                    rate=float(row["rate"]),
                    rate_date=date.fromisoformat(str(row["effective_date"])),
                    source=str(row["source"]),
                )
        return out

    async def save_rates(self, base: str, quote: str, rates: dict[date, FxRate]) -> None:
        rows: list[Row] = [
            {
                "base": base,
                "quote": quote,
                "rate_date": day.isoformat(),
                "rate": fx.rate,
                "effective_date": fx.rate_date.isoformat(),
                "source": fx.source,
            }
            for day, fx in rates.items()
        ]
        await (
            self._client.table("fx_rates")
            .upsert(rows, on_conflict="base,quote,rate_date")
            .execute()
        )
