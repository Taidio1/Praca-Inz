from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]


class MarketDataRepository:
    """Zapis snapshotów rynkowych — wymaga klienta z kluczem service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def assets_in_portfolios(self) -> list[Row]:
        """Aktywa występujące w dowolnym portfelu (bez duplikatów)."""
        res = await (
            self._client.table("portfolio_positions")
            .select("assets(id, ticker, asset_type)")
            .execute()
        )
        unique: dict[str, Row] = {}
        for row in res.data:
            asset = row.get("assets")
            if asset:
                unique.setdefault(asset["id"], asset)
        return list(unique.values())

    async def insert_snapshot(
        self, asset_id: str, price: float, change_24h: float | None
    ) -> None:
        await (
            self._client.table("market_snapshots")
            .insert({"asset_id": asset_id, "price": price, "change_24h": change_24h})
            .execute()
        )
