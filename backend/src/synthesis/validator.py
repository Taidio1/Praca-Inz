"""Walidacja syntezy (spec §5): format, ugruntowanie cytowań, brak rekomendacji."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

Label = Literal["positive", "neutral", "negative"]
_POS, _NEG = 0.2, -0.2  # zgodnie z filtrem sentymentu InsightsRepository

# Zakaz sformułowań doradczych; relacjonowanie newsów (cel cenowy analityków) jest dozwolone.
_TRANSACTION = re.compile(
    r"\bkupuj\b|\bsprzedaj\b|\btrzymaj\b|\bsprzedawaj\w*"
    r"|\bwarto (kupić|sprzedać|kupować|sprzedawać|trzymać)|\bpolecamy\b"
    r"|\bwe recommend|\byou should (buy|sell|hold)|\bstop[- ]?loss|\btake[- ]?profit"
    r"|\b(buy|sell|hold) signal",
    re.IGNORECASE,
)

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "sentiment_score": {"type": "number"},
        "sentiment_label": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "key_item_ids": {"type": "array", "items": {"type": "string"}},
        "price_context": {"type": ["string", "null"]},
    },
    "required": ["title", "summary", "sentiment_score", "sentiment_label", "key_item_ids",
                 "price_context"],
    "additionalProperties": False,
}


class DraftInvalid(Exception):
    """Odpowiedź modelu nie spełnia kontraktu; komunikat trafia do próby naprawy."""


class SynthesisDraft(BaseModel):
    title: str = Field(min_length=5, max_length=140)
    summary: str = Field(min_length=20, max_length=1200)
    sentiment_score: float = Field(ge=-1, le=1)
    sentiment_label: Label
    key_item_ids: list[str] = Field(min_length=1)
    price_context: str | None = None


def label_for(score: float) -> Label:
    if score > _POS:
        return "positive"
    if score < _NEG:
        return "negative"
    return "neutral"


def validate_draft(text: str, allowed_ids: set[str]) -> SynthesisDraft:
    try:
        draft = SynthesisDraft.model_validate_json(text)
    except ValidationError as exc:
        raise DraftInvalid(f"niezgodny format JSON: {exc.errors()[:3]}") from exc
    unknown = [i for i in draft.key_item_ids if i not in allowed_ids]
    if unknown:
        raise DraftInvalid(f"key_item_ids spoza przekazanych newsów: {unknown}")
    if len(set(draft.key_item_ids)) != len(draft.key_item_ids):
        raise DraftInvalid("key_item_ids nie mogą się powtórzyć")
    expected = label_for(draft.sentiment_score)
    if draft.sentiment_label != expected:
        raise DraftInvalid(
            f"etykieta {draft.sentiment_label} niezgodna z wynikiem "
            f"{draft.sentiment_score:+.2f} (powinna być {expected})"
        )
    for field in (draft.title, draft.summary, draft.price_context or ""):
        hit = _TRANSACTION.search(field)
        if hit:
            raise DraftInvalid(
                f"język rekomendacji transakcyjnej jest zabroniony: {hit.group(0)!r}"
            )
    return draft
