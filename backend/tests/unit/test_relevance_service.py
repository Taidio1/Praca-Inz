import json
from datetime import UTC, datetime, timedelta
from typing import Any

from src.relevance.profiles import ProfileDraft
from src.relevance.service import RelevanceService
from src.sources.base import TrackedAsset

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
BTC = TrackedAsset(id="a-btc", ticker="BTC", name="Bitcoin", asset_type="crypto")
NVDA = TrackedAsset(id="a-nvda", ticker="NVDA", name="NVIDIA", asset_type="stock")
BTC_ROW = {"asset_id": "a-btc", "names": ["Bitcoin"], "ticker_patterns": ["BTC"],
           "negative_terms": [], "keywords": [], "market": "crypto",
           "profile_text": "Bitcoin to kryptowaluta.", "embedding": "[1.0,0.0]",
           "generated_by": "llm"}


def item(i: int, title: str, *, dup: str | None = None, hints: tuple[str, ...] = (),
         embedding: str | None = None, best: float | None = None) -> dict[str, Any]:
    return {"id": f"i{i}", "source": "rss", "url": f"https://x.test/{i}", "title": title,
            "snippet": None, "raw": {"hint_asset_ids": list(hints)}, "duplicate_of": dup,
            "best_score": best, "embedding": embedding}


class FakeRepo:
    def __init__(self, pending: list[dict[str, Any]], profiles: list[dict[str, Any]],
                 recent: list[dict[str, Any]] | None = None) -> None:
        self.pending = pending
        self.profiles = profiles
        self.recent = recent or []
        self.saved_profiles: list[dict[str, Any]] = []
        self.relevance: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.recent_since: datetime | None = None

    async def pending_items(self, limit: int) -> list[dict[str, Any]]:
        return self.pending[:limit]

    async def recent_items(self, since: datetime, limit: int) -> list[dict[str, Any]]:
        self.recent_since = since
        return self.recent

    async def load_profiles(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        return [p for p in self.profiles if p["asset_id"] in asset_ids]

    async def save_profile(self, row: dict[str, Any]) -> None:
        self.saved_profiles.append(row)

    async def upsert_relevance(self, rows: list[dict[str, Any]]) -> None:
        self.relevance.extend(rows)

    async def update_items(self, rows: list[dict[str, Any]]) -> None:
        self.updates.extend(rows)

    async def previous_tracked(self) -> set[str] | None:
        return None  # brak historii cykli: bez uzupełniania wstecz

    async def recent_profile_failures(self, asset_ids: list[str],
                                      since: datetime) -> set[str]:
        return set(getattr(self, "failed_profiles", set())) & set(asset_ids)


class FakeAssets:
    def __init__(self, assets: list[TrackedAsset]) -> None:
        self.assets = assets

    async def tracked_assets(self) -> list[TrackedAsset]:
        return self.assets


class FakeBuilder:
    def __init__(self, draft: ProfileDraft | None = None) -> None:
        self.draft = draft
        self.calls: list[str] = []

    async def build(self, asset: TrackedAsset) -> tuple[ProfileDraft, str] | None:
        self.calls.append(asset.id)
        return (self.draft, "run-1") if self.draft else None


class FakeEmbedder:
    model_name = "test-e5"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("model nie załadowany")
        self.calls.append(list(texts))
        # deterministyczne wektory: "bitcoin" -> blisko [1,0], reszta -> [0,1]
        return [[1.0, 0.0] if "bitcoin" in t.lower() else [0.0, 1.0] for t in texts]


def service(repo: FakeRepo, assets: list[TrackedAsset], builder: FakeBuilder | None = None,
            embedder: FakeEmbedder | None = None) -> RelevanceService:
    return RelevanceService(repo, FakeAssets(assets), builder or FakeBuilder(),
                            embedder, threshold=0.5, weights=(0.5, 0.5), floor=0.70,
                            ceiling=0.90, batch_size=500, lookback_hours=72, clock=lambda: NOW)


async def test_scores_candidates_and_marks_all_done() -> None:
    repo = FakeRepo([item(1, "Metaplanet added 1,000 bitcoin, now 44,000 BTC"),
                     item(2, "Orlen, KGHM i PKO szarpnęły indeksem")], [BTC_ROW])
    emb = FakeEmbedder()
    stats = await service(repo, [BTC], embedder=emb).run()
    assert [(r["item_id"], r["asset_id"], r["method"]) for r in repo.relevance] == [
        ("i1", "a-btc", "combined")]
    assert repo.relevance[0]["score"] == 1.0 and repo.relevance[0]["embedding_score"] == 1.0
    assert emb.calls == [["Metaplanet added 1,000 bitcoin, now 44,000 BTC"]]  # tylko kandydat
    by_id = {u["id"]: u for u in repo.updates}
    assert by_id["i1"]["best_score"] == 1.0 and by_id["i1"]["embedding"] == "[1.000000,0.000000]"
    assert by_id["i2"]["best_score"] == 0.0 and "embedding" not in by_id["i2"]
    assert all(u["relevance_done_at"] == NOW.isoformat() for u in repo.updates)
    assert (stats.pending, stats.scored, stats.candidates, stats.passed) == (2, 2, 1, 1)


async def test_duplicates_marked_done_without_pairs() -> None:
    repo = FakeRepo([item(1, "Bitcoin rośnie", dup="i0")], [BTC_ROW])
    stats = await service(repo, [BTC], embedder=FakeEmbedder()).run()
    assert repo.relevance == []
    assert repo.updates[0]["relevance_done_at"] == NOW.isoformat()
    assert repo.updates[0]["best_score"] is None
    assert stats.duplicates == 1 and stats.scored == 0


async def test_hint_creates_candidate_and_stored_embedding_is_reused() -> None:
    repo = FakeRepo([item(1, "Chip stocks rally", hints=("a-btc",), embedding="[0.0,1.0]")],
                    [BTC_ROW])
    emb = FakeEmbedder()
    await service(repo, [BTC], embedder=emb).run()
    assert emb.calls == []  # wektor z bazy, bez ponownego liczenia
    assert repo.relevance[0]["match_score"] == 0.4 and repo.relevance[0]["score"] == 0.2


async def test_missing_profile_uses_fallback_and_retries_next_cycle() -> None:
    repo = FakeRepo([item(1, "NVIDIA beats estimates")], [])
    builder = FakeBuilder(None)
    svc = service(repo, [NVDA], builder=builder, embedder=FakeEmbedder())
    await svc.run()
    await svc.run()
    assert builder.calls == ["a-nvda", "a-nvda"]  # profil zapasowy nie jest zapisywany
    assert repo.saved_profiles == []
    assert repo.relevance[0]["method"] == "ticker_match"  # profil zapasowy nie ma embeddingu


async def test_new_profile_rescores_recent_items_for_that_asset_only() -> None:
    draft = ProfileDraft.model_validate({
        "names": ["NVIDIA", "Nvidia"], "ticker_patterns": ["NVDA"], "negative_terms": [],
        "keywords": ["GPU"], "profile_text": "Amerykański producent procesorów graficznych."})
    recent = [item(7, "Nvidia stock nears record highs", best=0.3),
              item(8, "Bitcoin ETF inflows", best=0.9)]
    repo = FakeRepo([], [BTC_ROW], recent=recent)
    stats = await service(repo, [BTC, NVDA], builder=FakeBuilder(draft),
                          embedder=FakeEmbedder()).run()
    assert repo.saved_profiles[0]["asset_id"] == "a-nvda"
    assert repo.saved_profiles[0]["embedding"] == "[0.000000,1.000000]"
    assert [(r["item_id"], r["asset_id"]) for r in repo.relevance] == [("i7", "a-nvda")]
    assert repo.recent_since == NOW - timedelta(hours=72)
    upd = {u["id"]: u for u in repo.updates}
    assert set(upd) == {"i7"} and "relevance_done_at" not in upd["i7"]
    assert upd["i7"]["best_score"] == repo.relevance[0]["score"]
    assert stats.profiles_created == 1 and stats.rescored == 2


async def test_embedder_failure_falls_back_to_match_only() -> None:
    repo = FakeRepo([item(1, "Bitcoin hits record")], [BTC_ROW])
    stats = await service(repo, [BTC], embedder=FakeEmbedder(fail=True)).run()
    assert repo.relevance[0]["method"] == "ticker_match"
    assert "embedder" in stats.errors
    assert repo.updates[0]["relevance_done_at"] == NOW.isoformat()


async def test_no_tracked_assets_is_noop() -> None:
    repo = FakeRepo([item(1, "Bitcoin")], [BTC_ROW])
    stats = await service(repo, []).run()
    assert stats.pending == 0 and repo.updates == []


def test_stats_json_has_no_errors() -> None:
    from src.relevance.service import RelevanceStats
    assert "errors" not in RelevanceStats(errors={"x": "y"}).as_json()
    json.dumps(RelevanceStats().as_json())


async def test_rescore_skips_items_scored_in_this_cycle() -> None:
    # Nowy profil był już użyty przy ocenie pending; ponowna ocena dublowała pary.
    draft = ProfileDraft.model_validate({
        "names": ["NVIDIA"], "ticker_patterns": ["NVDA"], "negative_terms": [],
        "keywords": [], "profile_text": "Amerykański producent procesorów graficznych."})
    fresh = item(1, "NVIDIA beats estimates")
    repo = FakeRepo([fresh], [], recent=[{**fresh, "best_score": 1.0}])
    stats = await service(repo, [NVDA], builder=FakeBuilder(draft),
                          embedder=FakeEmbedder()).run()
    assert [(r["item_id"], r["asset_id"]) for r in repo.relevance] == [("i1", "a-nvda")]
    assert stats.candidates == 1 and stats.rescored == 0


class TrackedHistoryRepo(FakeRepo):
    def __init__(self, *args: Any, previous: set[str] | None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.previous = previous

    async def previous_tracked(self) -> set[str] | None:
        return self.previous


async def test_newly_tracked_asset_with_stored_profile_gets_backfill() -> None:
    # (a) profil już istnieje (np. ktoś miał BTC wcześniej), ale aktywo właśnie wróciło do portfela
    recent = [item(7, "Bitcoin hits record high", best=0.0)]
    repo = TrackedHistoryRepo([], [BTC_ROW], recent=recent, previous=set())
    stats = await service(repo, [BTC], embedder=FakeEmbedder()).run()
    assert [(r["item_id"], r["asset_id"]) for r in repo.relevance] == [("i7", "a-btc")]
    assert stats.rescored == 1 and stats.as_json()["tracked"] == ["a-btc"]


async def test_newly_tracked_asset_on_fallback_profile_gets_backfill() -> None:
    # (b) brak klucza LLM: profil zapasowy też musi dostać ocenę newsów z ostatnich 72 h
    recent = [item(8, "NVIDIA beats estimates", best=0.0)]
    repo = TrackedHistoryRepo([], [], recent=recent, previous={"a-btc"})
    await service(repo, [NVDA], builder=FakeBuilder(None), embedder=FakeEmbedder()).run()
    assert [(r["item_id"], r["asset_id"]) for r in repo.relevance] == [("i8", "a-nvda")]


async def test_already_tracked_asset_is_not_backfilled_again() -> None:
    recent = [item(7, "Bitcoin hits record high", best=0.0)]
    repo = TrackedHistoryRepo([], [BTC_ROW], recent=recent, previous={"a-btc"})
    stats = await service(repo, [BTC], embedder=FakeEmbedder()).run()
    assert repo.relevance == [] and stats.rescored == 0


async def test_profile_without_embedding_is_reembedded_and_rescored() -> None:
    # Profil zapisany, gdy model embeddingów nie działał: po powrocie modelu dostaje wektor.
    row = {**BTC_ROW, "embedding": None, "embedding_model": None}
    recent = [item(7, "Bitcoin hits record high", best=0.0)]
    repo = FakeRepo([], [row], recent=recent)
    await service(repo, [BTC], embedder=FakeEmbedder()).run()
    assert repo.saved_profiles[0]["embedding"] == "[1.000000,0.000000]"
    assert repo.saved_profiles[0]["embedding_model"] == "test-e5"
    assert repo.relevance[0]["method"] == "combined"


async def test_profile_from_other_embedding_model_is_reembedded() -> None:
    row = {**BTC_ROW, "embedding_model": "inny-model"}
    repo = FakeRepo([], [row])
    await service(repo, [BTC], embedder=FakeEmbedder()).run()
    assert repo.saved_profiles[0]["embedding_model"] == "test-e5"


async def test_recent_profile_failure_backs_off_without_llm_call() -> None:
    repo = FakeRepo([item(1, "NVIDIA beats estimates")], [])
    repo.failed_profiles = {"a-nvda"}
    builder = FakeBuilder(None)
    stats = await service(repo, [NVDA], builder=builder, embedder=FakeEmbedder()).run()
    assert builder.calls == []  # bez płatnego wywołania w oknie po błędzie
    assert "profil zapasowy" in stats.errors["profile:NVDA"]
    assert repo.relevance[0]["method"] == "ticker_match"


async def test_fallback_after_failed_build_is_visible_in_errors() -> None:
    repo = FakeRepo([], [])
    stats = await service(repo, [NVDA], builder=FakeBuilder(None), embedder=FakeEmbedder()).run()
    assert "profil zapasowy" in stats.errors["profile:NVDA"]
