from datetime import datetime

from pydantic import BaseModel

from src.schemas.insights import InsightOut


class FeedPage(BaseModel):
    items: list[InsightOut]
    next_cursor: datetime | None = None
