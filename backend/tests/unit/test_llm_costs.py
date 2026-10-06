from src.repositories.llm_costs import sum_paged


async def test_sum_spans_more_than_one_page() -> None:
    # PostgREST oddaje domyślnie max 1000 wierszy: suma miesiąca nie może się na tym urwać
    rows = [{"cost_usd": 0.001} for _ in range(2500)]
    calls: list[tuple[int, int]] = []

    async def fetch(start: int, end: int) -> list[dict[str, float]]:
        calls.append((start, end))
        return rows[start : end + 1]

    total = await sum_paged(fetch, page_size=1000)
    assert round(total, 6) == 2.5
    assert calls == [(0, 999), (1000, 1999), (2000, 2999)]


async def test_null_costs_count_as_zero() -> None:
    async def fetch(start: int, end: int) -> list[dict[str, float | None]]:
        return [{"cost_usd": None}, {"cost_usd": 0.5}] if start == 0 else []

    assert await sum_paged(fetch, page_size=1000) == 0.5
