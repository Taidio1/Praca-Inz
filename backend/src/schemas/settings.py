from typing import Any, Literal

from pydantic import BaseModel, Field

BaseCurrency = Literal["PLN", "USD", "EUR"]


class SettingsOut(BaseModel):
    relevance_threshold: float
    notifications: dict[str, Any]
    base_currency: BaseCurrency = "PLN"


class SettingsUpdate(BaseModel):
    relevance_threshold: float | None = Field(default=None, ge=0, le=1)
    notifications: dict[str, Any] | None = None
    base_currency: BaseCurrency | None = None
