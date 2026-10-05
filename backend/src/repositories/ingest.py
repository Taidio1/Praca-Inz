from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from src.sources.base import SourceState, TrackedAsset

Row = dict[str, Any]


class IngestRepository:
    """Zapis itemów źródłowych i stanu źródeł: wymaga klienta service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def tracked_assets(self) -> list[TrackedAsset]:
        res = await (
            self._client.table("portfolio_positions")
            .select("assets(id, ticker, name, asset_type, aliases)")
            .execute()
        )
        unique: dict[str, TrackedAsset] = {}
        for row in res.data:
            a = row.get("assets")
            if a and a["id"] not in unique:
                unique[a["id"]] = TrackedAsset(
                    id=a["id"], ticker=a["ticker"], name=a["name"],
                    asset_type=a["asset_type"], aliases=tuple(a.get("aliases") or ()),
                )
        return list(unique.values())

    async def load_states(self) -> dict[str, SourceState]:
        res = await self._client.table("source_state").select("*").execute()
        return {
            r["source_key"]: SourceState(
                key=r["source_key"],
                last_fetched_at=datetime.fromisoformat(r["last_fetched_at"])
                if r["last_fetched_at"] else None,
                etag=r["etag"],
                last_modified=r["last_modified"],
                consecutive_failures=r["consecutive_failures"],
                last_error=r["last_error"],
            )
            for r in res.data
        }

    async def save_states(self, states: list[SourceState]) -> None:
        rows = [
            {
                "source_key": s.key,
                "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
                "etag": s.etag,
                "last_modified": s.last_modified,
                "consecutive_failures": s.consecutive_failures,
                "last_error": s.last_error,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            for s in states
        ]
        await self._client.table("source_state").upsert(rows, on_conflict="source_key").execute()

    async def existing_title_hashes(self, hashes: list[str], since: datetime) -> dict[str, str]:
        if not hashes:
            return {}
        found: dict[str, str] = {}
        for start in range(0, len(hashes), 200):  # długość URL zapytania PostgREST
            res = await (
                self._client.table("source_items")
                .select("id, title_hash")
                .in_("title_hash", hashes[start : start + 200])
                .is_("duplicate_of", "null")
                .gte("fetched_at", since.isoformat())
                .execute()
            )
            for r in res.data:
                found.setdefault(r["title_hash"], r["id"])
        return found

    async def insert_items(self, rows: list[Row]) -> list[Row]:
        if not rows:
            return []
        # VERIFY-DOCS: upsert z ignore_duplicates => ON CONFLICT DO NOTHING; zwraca tylko
        # faktycznie wstawione wiersze (PostgREST resolution=ignore-duplicates)
        res = await (
            self._client.table("source_items")
            .upsert(rows, on_conflict="source,url", ignore_duplicates=True)
            .execute()
        )
        return list(res.data)
