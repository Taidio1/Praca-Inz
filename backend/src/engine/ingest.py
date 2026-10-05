"""Etap 1 cyklu silnika: pobranie newsów ze źródeł, deduplikacja, zapis i stan źródeł."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog

from src.sources.base import NewsSource, RawItem, SourceState, TrackedAsset
from src.sources.dedup import normalize_url, title_hash

log = structlog.get_logger(__name__)

Row = dict[str, Any]
DUPLICATE_WINDOW = timedelta(hours=48)


class IngestRepo(Protocol):
    async def tracked_assets(self) -> list[TrackedAsset]: ...
    async def load_states(self) -> dict[str, SourceState]: ...
    async def save_states(self, states: list[SourceState]) -> None: ...
    async def existing_title_hashes(self, hashes: list[str], since: datetime) -> dict[str, str]: ...
    async def insert_items(self, rows: list[Row]) -> list[Row]: ...


@dataclass
class IngestStats:
    tracked_assets: int = 0
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "tracked_assets": self.tracked_assets,
            "fetched": self.fetched,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "per_source": self.per_source,
        }


def _to_row(item: RawItem) -> Row:
    return {
        "source": item.source,
        "url": normalize_url(item.url),
        "title": item.title,
        "snippet": item.snippet,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "raw": {**item.raw, "hint_asset_ids": list(item.hint_asset_ids)},
        "title_hash": title_hash(item.title),
    }


def _merge_by_url(rows: Iterable[Row]) -> list[Row]:
    """Jeden wiersz na (source, url); wskazówki aktywów z powtórzeń są scalane."""
    merged: dict[tuple[str, str], Row] = {}
    for row in rows:
        key = (row["source"], row["url"])
        if key not in merged:
            merged[key] = row
            continue
        hints = merged[key]["raw"]["hint_asset_ids"]
        for asset_id in row["raw"]["hint_asset_ids"]:
            if asset_id not in hints:
                hints.append(asset_id)
    return list(merged.values())


class IngestService:
    def __init__(
        self,
        sources: Sequence[NewsSource],
        repo: IngestRepo,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sources = sources
        self._repo = repo
        self._clock = clock

    async def run(self) -> IngestStats:
        now = self._clock()
        stats = IngestStats()
        assets = await self._repo.tracked_assets()
        stats.tracked_assets = len(assets)
        if not assets:
            return stats
        states = await self._repo.load_states()

        raw: list[RawItem] = []
        updates: dict[str, SourceState] = {}
        for source in self._sources:
            try:
                result = await source.fetch(assets, states, now)
            except Exception as exc:  # noqa: BLE001 (jedno źródło nie może zatrzymać cyklu)
                log.exception("source_crashed", source=source.name)
                message = f"{type(exc).__name__}: {exc}"
                stats.errors[source.name] = message
                # Klucz zbiorczy źródła: awaria widoczna w source_state i w UI.
                crash_key = f"{source.name}:*"
                prev = states.get(crash_key, SourceState(key=crash_key))
                updates[crash_key] = replace(
                    prev,
                    consecutive_failures=prev.consecutive_failures + 1,
                    last_error=message,
                )
                continue
            raw.extend(result.items)
            stats.per_source[source.name] = len(result.items)
            for key, (etag, modified) in result.ok.items():
                updates[key] = SourceState(
                    key=key, last_fetched_at=now, etag=etag, last_modified=modified
                )
            for key, message in result.errors.items():
                prev = states.get(key, SourceState(key=key))
                updates[key] = replace(
                    prev,
                    consecutive_failures=prev.consecutive_failures + 1,
                    last_error=message,
                )
                stats.errors[key] = message
        stats.fetched = len(raw)

        rows = _merge_by_url(map(_to_row, raw))
        existing = await self._repo.existing_title_hashes(
            sorted({r["title_hash"] for r in rows}), now - DUPLICATE_WINDOW
        )
        originals: list[Row] = []
        duplicates: list[Row] = []
        seen: set[str] = set()
        for row in rows:
            h = row["title_hash"]
            if h in existing or h in seen:
                duplicates.append(row)
            else:
                originals.append(row)
                seen.add(h)

        inserted = await self._repo.insert_items(originals) if originals else []
        ids = {**existing, **{r["title_hash"]: r["id"] for r in inserted}}
        linked = [{**r, "duplicate_of": ids[r["title_hash"]]} for r in duplicates
                  if r["title_hash"] in ids]
        # Oryginał spoza okna 48 h (konflikt URL) nie ma id: zapisujemy jako zwykły item.
        orphans = [r for r in duplicates if r["title_hash"] not in ids]
        inserted_dups = await self._repo.insert_items(linked) if linked else []
        inserted_orphans = await self._repo.insert_items(orphans) if orphans else []
        stats.inserted = len(inserted) + len(inserted_orphans)
        stats.duplicates = len(inserted_dups)

        if updates:
            await self._repo.save_states(list(updates.values()))
        log.info("ingest_done", **stats.as_json(), errors=len(stats.errors))
        return stats
