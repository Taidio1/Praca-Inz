from typing import Any, Protocol

from src.schemas.settings import SettingsOut, SettingsUpdate

Row = dict[str, Any]


class SettingsRepo(Protocol):
    async def get(self) -> Row | None: ...
    async def create_defaults(self, user_id: str) -> Row: ...
    async def update(self, user_id: str, fields: Row) -> Row: ...


class SettingsService:
    def __init__(self, settings: SettingsRepo) -> None:
        self._settings = settings

    async def get(self, user_id: str) -> SettingsOut:
        row = await self._settings.get()
        if row is None:
            row = await self._settings.create_defaults(user_id)
        return self._to_out(row)

    async def update(self, user_id: str, payload: SettingsUpdate) -> SettingsOut:
        current = await self.get(user_id)  # gwarantuje istnienie wiersza
        fields = payload.model_dump(exclude_none=True)
        if not fields:
            return current
        row = await self._settings.update(user_id, fields)
        return self._to_out(row)

    @staticmethod
    def _to_out(row: Row) -> SettingsOut:
        return SettingsOut(
            relevance_threshold=row["relevance_threshold"],
            notifications=row["notifications"],
            base_currency=row.get("base_currency") or "PLN",
        )
