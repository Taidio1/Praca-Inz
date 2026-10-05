"""Repozytorium filtra trafności + serializacja wektorów pgvector."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from supabase import AsyncClient


def to_pgvector(vector: Sequence[float]) -> str:
    # PostgREST zamieniłby listę JSON na tablicę Postgresa '{...}'; pgvector chce '[...]'
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def from_pgvector(value: Any) -> tuple[float, ...] | None:
    if value is None:
        return None
    data = json.loads(value) if isinstance(value, str) else value
    return tuple(float(x) for x in data)


Row = dict[str, Any]
_ITEM_COLUMNS = "id, source, url, title, snippet, raw, duplicate_of, best_score, embedding"
_CHUNK = 100


def group_by_keys(rows: list[Row]) -> list[list[Row]]:
    groups: dict[tuple[str, ...], list[Row]] = {}
    for row in rows:
        groups.setdefault(tuple(sorted(row)), []).append(row)
    return list(groups.values())


class RelevanceRepository:
    """Zapis ocen trafności i profili: wymaga klienta service_role (RLS)."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def pending_items(self, limit: int) -> list[Row]:
        res = await (
            self._client.table("source_items")
            .select(_ITEM_COLUMNS)
            .is_("relevance_done_at", "null")
            .order("fetched_at")
            .limit(limit)
            .execute()
        )
        return list(res.data)

    async def recent_items(self, since: datetime, limit: int) -> list[Row]:
        res = await (
            self._client.table("source_items")
            .select(_ITEM_COLUMNS)
            .not_.is_("relevance_done_at", "null")
            .is_("duplicate_of", "null")
            .gte("fetched_at", since.isoformat())
            .order("fetched_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data)

    async def previous_tracked(self) -> set[str] | None:
        res = await (
            self._client.table("engine_cycles")
            .select("stats")
            .not_.is_("finished_at", "null")
            .order("started_at", desc=True)
            .limit(5)
            .execute()
        )
        for row in res.data:
            tracked = ((row.get("stats") or {}).get("relevance") or {}).get("tracked")
            if isinstance(tracked, list):
                return {str(t) for t in tracked}
        return None  # brak historii (np. pierwszy cykl po wdrożeniu)

    async def recent_profile_failures(self, asset_ids: list[str], since: datetime) -> set[str]:
        """Aktywa, których ostatnia próba profilu od `since` się nie udała."""
        if not asset_ids:
            return set()
        res = await (
            self._client.table("llm_runs")
            .select("asset_id, status, created_at")
            .eq("purpose", "profile")
            .in_("asset_id", asset_ids)
            .gte("created_at", since.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
        latest: dict[str, str] = {}
        for r in res.data:
            latest.setdefault(str(r["asset_id"]), r["status"])
        return {a for a, status in latest.items() if status != "ok"}

    async def load_profiles(self, asset_ids: list[str]) -> list[Row]:
        if not asset_ids:
            return []
        res = await (
            self._client.table("asset_profiles").select("*").in_("asset_id", asset_ids).execute()
        )
        return list(res.data)

    async def save_profile(self, row: Row) -> None:
        await self._client.table("asset_profiles").upsert(row, on_conflict="asset_id").execute()

    async def insert_run(self, row: Row) -> str:
        res = await self._client.table("llm_runs").insert(row).execute()
        return str(res.data[0]["id"])

    async def upsert_relevance(self, rows: list[Row]) -> None:
        for start in range(0, len(rows), _CHUNK):
            await (
                self._client.table("item_relevance")
                .upsert(rows[start : start + _CHUNK], on_conflict="item_id,asset_id")
                .execute()
            )

    async def update_items(self, rows: list[Row]) -> None:
        # Upsert po id: wiersze muszą mieć source/url/title (NOT NULL części INSERT)
        for group in group_by_keys(rows):
            for start in range(0, len(group), _CHUNK):
                await (
                    self._client.table("source_items")
                    .upsert(group[start : start + _CHUNK], on_conflict="id")
                    .execute()
                )
