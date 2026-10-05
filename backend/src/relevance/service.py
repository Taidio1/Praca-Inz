"""Etap 2 cyklu silnika: ocena trafności item × aktywo (spec §4)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog

from src.relevance.embedder import Embedder, cosine, item_text
from src.relevance.matcher import Matcher, MatchResult
from src.relevance.profiles import (
    AssetProfile,
    ProfileDraft,
    fallback_profile,
    profile_from_row,
    profile_to_row,
)
from src.relevance.scorer import score_pair
from src.repositories.relevance import from_pgvector, to_pgvector
from src.sources.base import TrackedAsset

log = structlog.get_logger(__name__)
Row = dict[str, Any]
# Po nieudanej generacji profilu nie płacimy za ponowienie w każdym cyklu
PROFILE_RETRY_AFTER = timedelta(hours=6)


class RelevanceRepo(Protocol):
    async def pending_items(self, limit: int) -> list[Row]: ...
    async def recent_items(self, since: datetime, limit: int) -> list[Row]: ...
    async def load_profiles(self, asset_ids: list[str]) -> list[Row]: ...
    async def save_profile(self, row: Row) -> None: ...
    async def upsert_relevance(self, rows: list[Row]) -> None: ...
    async def update_items(self, rows: list[Row]) -> None: ...
    async def previous_tracked(self) -> set[str] | None: ...
    async def recent_profile_failures(self, asset_ids: list[str], since: datetime) -> set[str]: ...


class TrackedAssetsRepo(Protocol):
    async def tracked_assets(self) -> list[TrackedAsset]: ...


class ProfileSource(Protocol):
    async def build(self, asset: TrackedAsset) -> tuple[ProfileDraft, str] | None: ...


@dataclass
class RelevanceStats:
    pending: int = 0
    scored: int = 0
    duplicates: int = 0
    candidates: int = 0
    passed: int = 0
    profiles_created: int = 0
    rescored: int = 0
    tracked: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "pending": self.pending, "scored": self.scored, "duplicates": self.duplicates,
            "candidates": self.candidates, "passed": self.passed,
            "profiles_created": self.profiles_created, "rescored": self.rescored,
            # zestaw śledzonych aktywów: kolejny cykl wykrywa po nim aktywa nowe w portfelu
            "tracked": self.tracked,
        }


class RelevanceService:
    def __init__(
        self,
        repo: RelevanceRepo,
        assets: TrackedAssetsRepo,
        builder: ProfileSource,
        embedder: Embedder | None,
        *,
        threshold: float,
        weights: tuple[float, float],
        floor: float,
        ceiling: float,
        batch_size: int,
        lookback_hours: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._assets = assets
        self._builder = builder
        self._embedder = embedder
        self._threshold = threshold
        self._weights = weights
        self._floor = floor
        self._ceiling = ceiling
        self._batch = batch_size
        self._lookback = timedelta(hours=lookback_hours)
        self._clock = clock

    async def run(self) -> RelevanceStats:
        stats = RelevanceStats()
        now = self._clock()
        assets = await self._assets.tracked_assets()
        if not assets:
            return stats
        stats.tracked = sorted(a.id for a in assets)
        profiles, new_ids = await self._profiles(assets, stats)
        previous = await self._repo.previous_tracked()
        if previous is not None:
            # Aktywo nowe w portfelu (także z zapisanym albo zapasowym profilem) dostaje
            # ocenę newsów z okna wstecz, nie tylko tych pobranych od teraz.
            new_ids |= {a.id for a in assets} - previous

        pending = await self._repo.pending_items(self._batch)
        stats.pending = len(pending)
        await self._score(pending, assets, profiles, stats, now=now, initial=True)

        if new_ids:
            recent = await self._repo.recent_items(now - self._lookback, 2 * self._batch)
            # Itemy z pending tego cyklu oceniono już z nowymi profilami.
            scored_now = {i["id"] for i in pending}
            recent = [i for i in recent if i["id"] not in scored_now]
            stats.rescored = len(recent)
            new_assets = [a for a in assets if a.id in new_ids]
            await self._score(recent, new_assets, profiles, stats, now=now, initial=False)
        log.info("relevance_done", **stats.as_json(), errors=len(stats.errors))
        return stats

    async def _profiles(
        self, assets: list[TrackedAsset], stats: RelevanceStats
    ) -> tuple[dict[str, AssetProfile], set[str]]:
        rows = await self._repo.load_profiles([a.id for a in assets])
        profiles: dict[str, AssetProfile] = {}
        new_ids: set[str] = set()
        for row in rows:
            if await self._needs_embedding(row, stats):
                vector = await self._embed_one(row["profile_text"], stats)
                if vector is not None and self._embedder is not None:
                    # Profil bez wektora albo z innego modelu: dosztukowanie bez wywołania LLM
                    row = {**row, "embedding": to_pgvector(vector),
                           "embedding_model": self._embedder.model_name}
                    await self._repo.save_profile(row)
                    new_ids.add(row["asset_id"])
            profiles[row["asset_id"]] = profile_from_row(row)
        missing = [a for a in assets if a.id not in profiles]
        backoff = (
            await self._repo.recent_profile_failures(
                [a.id for a in missing], self._clock() - PROFILE_RETRY_AFTER
            )
            if missing
            else set()
        )
        for asset in missing:
            key = f"profile:{asset.ticker}"
            if asset.id in backoff:
                profiles[asset.id] = fallback_profile(asset)
                stats.errors[key] = "profil zapasowy (ponowienie generacji po 6 h od błędu)"
                continue
            try:
                built = await self._builder.build(asset)
            except Exception as exc:  # noqa: BLE001 (błąd profilu nie zatrzymuje oceny)
                log.exception("profile_failed", asset=asset.ticker)
                stats.errors[key] = f"profil zapasowy: {type(exc).__name__}: {exc}"
                built = None
            if built is None:
                profiles[asset.id] = fallback_profile(asset)
                stats.errors.setdefault(key, "profil zapasowy (brak profilu z LLM)")
                continue
            draft, run_id = built
            vector = await self._embed_one(draft.profile_text, stats)
            model = self._embedder.model_name if self._embedder and vector else None
            row = profile_to_row(asset, draft, vector, model, run_id)
            await self._repo.save_profile(row)
            profiles[asset.id] = profile_from_row(row)
            new_ids.add(asset.id)
            stats.profiles_created += 1
        return profiles, new_ids

    async def _needs_embedding(self, row: Row, stats: RelevanceStats) -> bool:
        if self._embedder is None or "embedder" in stats.errors:
            return False
        if row.get("embedding") is None:
            return True
        model = row.get("embedding_model")
        return model is not None and model != self._embedder.model_name

    async def _embed_one(self, text: str, stats: RelevanceStats) -> list[float] | None:
        if self._embedder is None:
            return None
        try:
            return (await self._embedder.embed([text]))[0]
        except Exception as exc:  # noqa: BLE001 (np. model nie załadowany)
            stats.errors["embedder"] = f"{type(exc).__name__}: {exc}"
            return None

    async def _score(
        self,
        items: list[Row],
        assets: list[TrackedAsset],
        profiles: dict[str, AssetProfile],
        stats: RelevanceStats,
        *,
        now: datetime,
        initial: bool,
    ) -> None:
        originals = [i for i in items if not i.get("duplicate_of")]
        matchers = {a.id: Matcher(profiles[a.id]) for a in assets}
        pairs: list[tuple[Row, TrackedAsset, MatchResult]] = []
        for it in originals:
            hints = set((it.get("raw") or {}).get("hint_asset_ids") or [])
            for asset in assets:
                m = matchers[asset.id].match(it["title"], it.get("snippet"), asset.id in hints)
                if m.score > 0:
                    pairs.append((it, asset, m))
        stats.candidates += len(pairs)

        vectors: dict[str, tuple[float, ...]] = {}
        for it, _, _ in pairs:
            stored = from_pgvector(it.get("embedding"))
            if stored is not None:
                vectors[it["id"]] = stored
        need = {it["id"]: it for it, _, _ in pairs if it["id"] not in vectors}
        fresh: dict[str, list[float]] = {}
        if need and self._embedder is not None and "embedder" not in stats.errors:
            try:
                texts = [item_text(i["title"], i.get("snippet")) for i in need.values()]
                for item_id, vec in zip(need, await self._embedder.embed(texts), strict=True):
                    fresh[item_id] = vec
                    vectors[item_id] = tuple(vec)
            except Exception as exc:  # noqa: BLE001 (ocena idzie dalej samym matchingiem)
                log.exception("embedder_failed")
                stats.errors["embedder"] = f"{type(exc).__name__}: {exc}"

        rel_rows: list[Row] = []
        best: dict[str, float] = {}
        for it, asset, m in pairs:
            profile_vec = profiles[asset.id].embedding
            item_vec = vectors.get(it["id"])
            cos = cosine(item_vec, profile_vec) if item_vec and profile_vec else None
            ps = score_pair(m, cos, weights=self._weights, floor=self._floor,
                            ceiling=self._ceiling)
            rel_rows.append({
                "item_id": it["id"], "asset_id": asset.id, "score": ps.score,
                "method": ps.method, "reason": ps.reason, "match_score": ps.match_score,
                "embedding_score": ps.embedding_score,
            })
            best[it["id"]] = max(best.get(it["id"], 0.0), ps.score)
            if ps.score >= self._threshold:
                stats.passed += 1
        if rel_rows:
            await self._repo.upsert_relevance(rel_rows)

        updates: list[Row] = []
        for it in items:
            row: Row = {"id": it["id"], "source": it["source"], "url": it["url"],
                        "title": it["title"]}
            is_dup = bool(it.get("duplicate_of"))
            if initial:
                row["relevance_done_at"] = now.isoformat()
                row["best_score"] = None if is_dup else best.get(it["id"], 0.0)
            else:
                old = float(it.get("best_score") or 0.0)
                new = max(old, best.get(it["id"], 0.0))
                if new == old and it["id"] not in fresh:
                    continue
                row["best_score"] = new
            if it["id"] in fresh:
                row["embedding"] = to_pgvector(fresh[it["id"]])
                row["embedding_model"] = self._embedder.model_name if self._embedder else None
            updates.append(row)
        if updates:
            await self._repo.update_items(updates)
        if initial:
            stats.scored += len(originals)
            stats.duplicates += len(items) - len(originals)
