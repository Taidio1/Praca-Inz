from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]

_TX_FIELDS = (
    "id, quantity, price, currency, fx_rate, fx_rate_date, physical_form, purchased_at, created_at"
)


class PortfolioRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_positions(self) -> list[Row]:
        res = await (
            self._client.table("portfolio_positions")
            .select("id, quantity, avg_buy_price, created_at, assets(*)")
            .order("created_at")
            .execute()
        )
        return list(res.data)

    async def get_position(self, position_id: str) -> Row | None:
        res = await (
            self._client.table("portfolio_positions")
            .select("id, user_id, asset_id, quantity, avg_buy_price")
            .eq("id", position_id)
            .execute()
        )
        return dict(res.data[0]) if res.data else None

    async def find_position(self, user_id: str, asset_id: str) -> Row | None:
        res = await (
            self._client.table("portfolio_positions")
            .select("id, user_id, asset_id, quantity, avg_buy_price")
            .eq("user_id", user_id)
            .eq("asset_id", asset_id)
            .execute()
        )
        return dict(res.data[0]) if res.data else None

    async def create_position(
        self, user_id: str, asset_id: str, quantity: float, avg_buy_price: float | None
    ) -> Row:
        res = await (
            self._client.table("portfolio_positions")
            .insert(
                {
                    "user_id": user_id,
                    "asset_id": asset_id,
                    "quantity": quantity,
                    "avg_buy_price": avg_buy_price,
                }
            )
            .execute()
        )
        return dict(res.data[0])

    async def update_position_aggregate(
        self, position_id: str, quantity: float, avg_buy_price: float | None
    ) -> Row:
        res = await (
            self._client.table("portfolio_positions")
            .update({"quantity": quantity, "avg_buy_price": avg_buy_price})
            .eq("id", position_id)
            .execute()
        )
        return dict(res.data[0])

    async def add_transaction(
        self,
        position_id: str,
        user_id: str,
        quantity: float,
        price: float | None,
        purchased_at: str,
        currency: str,
        fx_rate: float,
        fx_rate_date: str,
        physical_form: str | None = None,
    ) -> Row:
        res = await (
            self._client.table("portfolio_transactions")
            .insert(
                {
                    "position_id": position_id,
                    "user_id": user_id,
                    "quantity": quantity,
                    "price": price,
                    "purchased_at": purchased_at,
                    "currency": currency,
                    "fx_rate": fx_rate,
                    "fx_rate_date": fx_rate_date,
                    "physical_form": physical_form,
                }
            )
            .execute()
        )
        return dict(res.data[0])

    async def list_transactions(self, position_id: str) -> list[Row]:
        res = await (
            self._client.table("portfolio_transactions")
            .select(_TX_FIELDS)
            .eq("position_id", position_id)
            .order("purchased_at", desc=True)
            .order("created_at", desc=True)
            .execute()
        )
        return list(res.data)

    async def list_all_transactions(self) -> list[Row]:
        """Transakcje wszystkich pozycji użytkownika (RLS) — pod wycenę historyczną."""
        res = await (
            self._client.table("portfolio_transactions")
            .select("position_id, quantity, price, currency, fx_rate, purchased_at")
            .order("purchased_at")
            .execute()
        )
        return list(res.data)

    async def get_transaction(self, position_id: str, tx_id: str) -> Row | None:
        res = await (
            self._client.table("portfolio_transactions")
            .select(_TX_FIELDS)
            .eq("position_id", position_id)
            .eq("id", tx_id)
            .execute()
        )
        return dict(res.data[0]) if res.data else None

    async def update_transaction(
        self,
        position_id: str,
        tx_id: str,
        quantity: float,
        price: float | None,
        purchased_at: str,
        currency: str,
        fx_rate: float,
        fx_rate_date: str,
    ) -> Row:
        res = await (
            self._client.table("portfolio_transactions")
            .update(
                {
                    "quantity": quantity,
                    "price": price,
                    "purchased_at": purchased_at,
                    "currency": currency,
                    "fx_rate": fx_rate,
                    "fx_rate_date": fx_rate_date,
                }
            )
            .eq("position_id", position_id)
            .eq("id", tx_id)
            .execute()
        )
        return dict(res.data[0])

    async def delete_transaction(self, position_id: str, tx_id: str) -> bool:
        res = await (
            self._client.table("portfolio_transactions")
            .delete()
            .eq("position_id", position_id)
            .eq("id", tx_id)
            .execute()
        )
        return bool(res.data)

    async def delete(self, position_id: str) -> bool:
        res = await (
            self._client.table("portfolio_positions")
            .delete()
            .eq("id", position_id)
            .execute()
        )
        # RLS: cudzej pozycji nie widać, więc delete zwraca pustą listę
        return bool(res.data)
