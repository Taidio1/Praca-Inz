from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SourceItemOut(BaseModel):
    item_id: UUID
    title: str
    source: str
    url: str
    published_at: datetime | None = None
    score: float
    method: str
    reason: str | None = None


class AssessmentOut(BaseModel):
    asset_id: UUID
    ticker: str
    score: float
    method: str
    reason: str | None = None
    match_score: float | None = None
    embedding_score: float | None = None


class RawSourceItemOut(BaseModel):
    item_id: UUID
    source: str
    url: str
    title: str
    snippet: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    duplicate_of: UUID | None = None
    relevance_done: bool = False
    assessments: list[AssessmentOut] = []
    outlet: str | None = None  # wydawca (Finnhub) lub domena (GDELT); RSS: brak


class SourcePage(BaseModel):
    items: list[RawSourceItemOut]
    next_cursor: str | None = None  # keyset: fetched_at|id


class EngineCycleOut(BaseModel):
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict[str, Any]
    errors: dict[str, str]


class SourceHealthOut(BaseModel):
    key: str
    last_fetched_at: datetime | None = None
    consecutive_failures: int
    last_error: str | None = None


class EngineStatusOut(BaseModel):
    last_cycle: EngineCycleOut | None = None
    failing_sources: list[SourceHealthOut]


class FunnelOut(BaseModel):
    hours: int
    threshold: float
    fetched: int
    duplicates: int
    scored: int
    candidates: int
    passed: int
    rejected: int
    unmatched: int
    sent_to_llm: int
    insights: int
    cost_usd: float
