"""Suma kosztów LLM od danej chwili (budżet dzienny, koszt miesiąca w statusie silnika)."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from supabase import AsyncClient

PAGE = 1000  # domyślny limit wierszy odpowiedzi PostgREST w Supabase

FetchPage = Callable[[int, int], Awaitable[Sequence[dict[str, Any]]]]


async def sum_paged(fetch: FetchPage, page_size: int = PAGE) -> float:
    total = 0.0
    start = 0
    while True:
        rows = await fetch(start, start + page_size - 1)
        total += sum(float(r.get("cost_usd") or 0) for r in rows)
        if len(rows) < page_size:
            return total
        start += page_size


async def llm_cost_since(client: AsyncClient, since: datetime) -> float:
    async def fetch(start: int, end: int) -> Sequence[dict[str, Any]]:
        res = await (
            client.table("llm_runs")
            .select("cost_usd")
            .gte("created_at", since.isoformat())
            .order("created_at")
            .range(start, end)
            .execute()
        )
        return list(res.data)

    return await sum_paged(fetch)
