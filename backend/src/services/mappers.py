from typing import Any

from src.schemas.assets import AssetOut, SnapshotOut
from src.schemas.insights import InsightOut, InsightSourceOut


def asset_from_row(row: dict[str, Any]) -> AssetOut:
    return AssetOut(
        id=row["id"],
        ticker=row["ticker"],
        name=row["name"],
        asset_type=row["asset_type"],
        currency=row["currency"],
    )


def snapshot_from_row(row: dict[str, Any] | None) -> SnapshotOut | None:
    if row is None:
        return None
    return SnapshotOut(
        price=row.get("price"),
        change_24h=row.get("change_24h"),
        indicators=row.get("indicators"),
        funding=row.get("funding"),
        captured_at=row.get("captured_at"),
    )


def insight_from_row(row: dict[str, Any]) -> InsightOut:
    key_items = [
        InsightSourceOut(
            title=link["source_items"]["title"],
            source=link["source_items"]["source"],
            url=link["source_items"]["url"],
            relevance=link["relevance"],
        )
        for link in row.get("insight_items") or []
    ]
    asset = row.get("assets") or {}
    return InsightOut(
        id=row["id"],
        asset_id=row["asset_id"],
        asset_ticker=asset.get("ticker"),
        title=row["title"],
        summary=row["summary"],
        sentiment_score=row["sentiment_score"],
        sentiment_label=row["sentiment_label"],
        price_context=row.get("price_context"),
        created_at=row["created_at"],
        key_items=key_items,
        trigger=row.get("trigger"),
    )
