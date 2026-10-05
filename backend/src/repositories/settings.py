from typing import Any

from supabase import AsyncClient

Row = dict[str, Any]


class SettingsRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get(self) -> Row | None:
        # RLS ogranicza wynik do wiersza zalogowanego użytkownika
        res = await self._client.table("user_settings").select("*").limit(1).execute()
        return res.data[0] if res.data else None

    async def create_defaults(self, user_id: str) -> Row:
        res = await (
            self._client.table("user_settings").insert({"user_id": user_id}).execute()
        )
        return dict(res.data[0])

    async def update(self, user_id: str, fields: Row) -> Row:
        res = await (
            self._client.table("user_settings")
            .update(fields)
            .eq("user_id", user_id)
            .execute()
        )
        return dict(res.data[0])
