from typing import Any, cast

from supabase import AsyncClient

Row = dict[str, Any]


class AssetsRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def find_by_ticker(self, ticker: str, asset_type: str) -> Row | None:
        res = await (
            self._client.table("assets")
            .select("*")
            .ilike("ticker", ticker)
            .eq("asset_type", asset_type)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    async def search_local(self, q: str, limit: int) -> list[Row]:
        query = q.strip().replace("%", "").replace(",", " ")
        if not query:
            return []
        res = await (
            self._client.table("assets")
            .select("*")
            .or_(f"ticker.ilike.{query}%,name.ilike.%{query}%")
            .limit(limit)
            .execute()
        )
        return list(res.data or [])

    async def create(
        self, ticker: str, name: str, asset_type: str, aliases: list[str], currency: str
    ) -> Row:
        clean_aliases = list(
            dict.fromkeys(alias.strip().lower() for alias in aliases if alias.strip())
        )
        res = await (
            self._client.table("assets")
            .upsert(
                {
                    "ticker": ticker.upper(),
                    "name": name,
                    "asset_type": asset_type,
                    "aliases": clean_aliases,
                    "currency": currency,
                },
                on_conflict="ticker,asset_type",
                ignore_duplicates=False,
            )
            .execute()
        )
        return cast(Row, res.data[0])

    async def get(self, asset_id: str) -> Row | None:
        res = await (
            self._client.table("assets").select("*").eq("id", asset_id).limit(1).execute()
        )
        return res.data[0] if res.data else None
