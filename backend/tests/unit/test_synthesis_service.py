import json
from datetime import UTC, datetime, timedelta
from typing import Any

from src.sources.base import TrackedAsset
from src.synthesis.provider import LLMError, LLMResult
from src.synthesis.service import SynthesisService
from src.synthesis.trigger import TriggerRules

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
NVDA = TrackedAsset(id="a-nvda", ticker="NVDA", name="NVIDIA Corp.", asset_type="stock")
BTC = TrackedAsset(id="a-btc", ticker="BTC", name="Bitcoin", asset_type="crypto")
RULES = TriggerRules(important_score=0.85, batch_min=3, daily_hours=24, max_per_day=6,
                     min_gap_minutes=30)


def row(i: int, score: float, minutes_ago: int = 10) -> dict[str, Any]:
    when = NOW - timedelta(minutes=minutes_ago)
    return {"item_id": f"uuid-{i}", "score": score, "title": f"News {i} o aktywie",
            "snippet": None, "outlet": "Yahoo", "published_at": when, "fetched_at": when}


def answer(ids: list[str], **over: Any) -> str:
    return json.dumps({"title": "Tytuł insightu o aktywie",
                       "summary": "Streszczenie newsów o aktywie z ostatnich godzin.",
                       "sentiment_score": 0.4, "sentiment_label": "positive",
                       "key_item_ids": ids, "price_context": None, **over}, ensure_ascii=False)


class FakeProvider:
    name = "anthropic"
    model = "claude-haiku-4-5"

    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = replies
        self.users: list[str] = []

    async def complete(self, *, system: str, user: str, max_tokens: int,
                       schema: dict[str, Any]) -> LLMResult:
        self.users.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, provider="anthropic", model=self.model, tokens_in=2500,
                         tokens_out=300, cache_read_tokens=0, latency_ms=1500, cost_usd=0.004)


class FakeRepo:
    def __init__(self, cands: dict[str, list[dict[str, Any]]],
                 activity: dict[str, dict[str, Any]] | None = None, spent: float = 0.0) -> None:
        self.cands = cands
        self.act = activity or {}
        self.spent = spent
        self.runs: list[dict[str, Any]] = []
        self.insights: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.since: dict[str, datetime] = {}

    async def candidates(self, asset_id: str, *, threshold: float, since: datetime,
                         limit: int) -> list[dict[str, Any]]:
        self.since[asset_id] = since
        return [r for r in self.cands.get(asset_id, []) if r["fetched_at"] > since]

    async def activity(self, asset_ids: list[str],
                       day_start: datetime) -> dict[str, dict[str, Any]]:
        return self.act

    async def cost_since(self, since: datetime) -> float:
        return self.spent

    async def profiles(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {"a-nvda": {"profile_text": "Producent GPU.", "market": "us"}}

    async def snapshots(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {}

    async def insert_run(self, r: dict[str, Any]) -> str:
        self.runs.append(r)
        return f"run-{len(self.runs)}"

    async def insert_insight(self, r: dict[str, Any]) -> str:
        self.insights.append(r)
        return f"ins-{len(self.insights)}"

    async def insert_insight_items(self, rows: list[dict[str, Any]]) -> None:
        self.links.extend(rows)


class FakeAssets:
    def __init__(self, assets: list[TrackedAsset]) -> None:
        self.assets = assets

    async def tracked_assets(self) -> list[TrackedAsset]:
        return self.assets


def svc(repo: FakeRepo, assets: list[TrackedAsset], provider: FakeProvider | None,
        budget: float = 0.60, max_per_cycle: int = 10) -> SynthesisService:
    return SynthesisService(repo, FakeAssets(assets), provider, rules=RULES, threshold=0.5,
                            lookback_hours=72, max_items=10, max_per_cycle=max_per_cycle,
                            budget_usd=budget, reserve_usd=0.01, clock=lambda: NOW)


async def test_batch_creates_insight_with_cited_items() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.6), row(2, 0.7), row(3, 0.55)]})
    prov = FakeProvider([answer(["n1", "n3"])])
    stats = await svc(repo, [NVDA], prov).run()
    assert stats.created == 1 and stats.triggered == 1
    ins = repo.insights[0]
    assert (ins["asset_id"], ins["trigger"], ins["llm_run_id"]) == ("a-nvda", "batch", "run-1")
    # n1 = najwyższy score (uuid-2), n3 = najniższy (uuid-3)
    assert [(link["item_id"], link["relevance"]) for link in repo.links] == [
        ("uuid-2", 0.7), ("uuid-3", 0.55)]
    run = repo.runs[0]
    assert (run["purpose"], run["status"], run["cost_usd"]) == ("synthesis", "ok", 0.004)
    assert "Producent GPU." in prov.users[0]
    assert stats.cost_usd == 0.004


async def test_items_older_than_last_insight_are_consumed() -> None:
    act = {"a-nvda": {"last_insight_at": NOW - timedelta(hours=1), "last_summary": "Stare.",
                      "insights_today": 1}}
    repo = FakeRepo({"a-nvda": [row(i, 0.6, minutes_ago=120) for i in range(40)]}, act)
    stats = await svc(repo, [NVDA], FakeProvider([])).run()
    assert stats.created == 0 and repo.since["a-nvda"] == NOW - timedelta(hours=1)
    assert "brak nowych" in stats.waiting["NVDA"]


async def test_waiting_reason_when_below_batch() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.6)]})
    stats = await svc(repo, [NVDA], FakeProvider([])).run()
    assert stats.created == 0 and stats.waiting["NVDA"].startswith("czeka na paczkę")


async def test_repair_once_then_success() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.9)]})
    prov = FakeProvider([answer(["n7"]), answer(["n1"])])
    stats = await svc(repo, [NVDA], prov).run()
    assert stats.created == 1 and len(repo.runs) == 2
    assert repo.runs[0]["status"] == "invalid" and "n7" in repo.runs[0]["error"]
    assert "niepoprawna" in prov.users[1]
    assert repo.insights[0]["trigger"] == "important"


async def test_invalid_twice_logs_invalid_and_no_insight() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.9)]})
    bad = answer(["n1"], summary="Analitycy radzą: kupuj przed wynikami kwartalnymi.")
    stats = await svc(repo, [NVDA], FakeProvider([bad, bad])).run()
    assert stats.invalid == 1 and repo.insights == []
    assert [r["status"] for r in repo.runs] == ["invalid", "invalid"]


async def test_llm_error_logged_and_cycle_continues() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.9)], "a-btc": [row(5, 0.95)]})
    prov = FakeProvider([LLMError("APIConnectionError: brak sieci"), answer(["n1"])])
    stats = await svc(repo, [NVDA, BTC], prov).run()
    assert stats.failed == 1 and stats.created == 1
    assert repo.runs[0]["status"] == "error" and "brak sieci" in repo.runs[0]["error"]
    assert "synthesis:" in next(iter(stats.errors))


async def test_billed_refusal_counts_against_budget() -> None:
    billed = LLMResult(text="", provider="anthropic", model="claude-haiku-4-5", tokens_in=2500,
                       tokens_out=1024, cache_read_tokens=0, latency_ms=9000, cost_usd=0.00762)
    repo = FakeRepo({"a-nvda": [row(1, 0.9)]})
    stats = await svc(repo, [NVDA], FakeProvider([LLMError("stop_reason=max_tokens",
                                                           result=billed)])).run()
    assert stats.failed == 1 and stats.cost_usd == 0.00762
    assert repo.runs[0]["cost_usd"] == 0.00762 and repo.runs[0]["status"] == "error"


async def test_budget_stops_further_syntheses_this_cycle() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.9)], "a-btc": [row(5, 0.6), row(6, 0.6), row(7, 0.6)]},
                    spent=0.588)
    prov = FakeProvider([answer(["n1"])])
    stats = await svc(repo, [NVDA, BTC], prov).run()
    # start: 0.588 + 0.01 <= 0.60; important (NVDA) pierwszy; po nim 0.592 + 0.01 > 0.60
    assert stats.created == 1 and repo.insights[0]["asset_id"] == "a-nvda"
    assert stats.skipped_budget == 1 and stats.budget_exhausted
    assert stats.waiting["BTC"] == "limit dzienny budżetu"


async def test_no_provider_is_reported_not_raised() -> None:
    stats = await svc(FakeRepo({"a-nvda": [row(1, 0.9)]}), [NVDA], None).run()
    assert stats.errors == {"llm": "brak ANTHROPIC_API_KEY"} and stats.created == 0


async def test_max_per_cycle_cap() -> None:
    repo = FakeRepo({"a-nvda": [row(1, 0.9)], "a-btc": [row(5, 0.95), row(6, 0.9)]})
    # oba "important"; BTC ma więcej kandydatów, więc wyższy priorytet
    stats = await svc(repo, [NVDA, BTC], FakeProvider([answer(["n1"])]), max_per_cycle=1).run()
    assert stats.created == 1 and repo.insights[0]["asset_id"] == "a-btc"  # wyższy priorytet
