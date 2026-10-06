from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from src.schemas.insights import InsightOut

AssetType = Literal["crypto", "stock", "etf", "commodity"]


class AssetOut(BaseModel):
    id: UUID
    ticker: str
    name: str
    asset_type: AssetType
    currency: str  # waluta notowania (ISO 4217)


class AssetSearchResultOut(BaseModel):
    ticker: str
    name: str
    asset_type: AssetType


class SnapshotOut(BaseModel):
    price: float | None = None
    change_24h: float | None = None
    indicators: dict[str, Any] | None = None
    funding: dict[str, Any] | None = None
    captured_at: datetime | None = None


class AssetDetailOut(BaseModel):
    asset: AssetOut
    snapshot: SnapshotOut | None
    latest_insights: list[InsightOut]
