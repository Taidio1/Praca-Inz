from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InsightSourceOut(BaseModel):
    title: str
    source: str
    url: str
    relevance: float


class InsightOut(BaseModel):
    id: UUID
    asset_id: UUID
    asset_ticker: str | None = None
    title: str
    summary: str
    sentiment_score: float
    sentiment_label: str
    price_context: str | None = None
    created_at: datetime
    key_items: list[InsightSourceOut]


class TraceOut(BaseModel):
    provider: str
    model: str
    prompt: str
    response: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    created_at: datetime
