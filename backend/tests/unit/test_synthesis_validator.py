import json
from pathlib import Path

import pytest

from src.synthesis.validator import SYNTHESIS_SCHEMA, DraftInvalid, label_for, validate_draft

IDS = {"n1", "n2", "n3"}
GOOD = {
    "title": "NVIDIA blisko rekordu po danych Foxconnu",
    "summary": "Akcje NVIDII zbliżyły się do rekordu po mocnych danych dostawcy Foxconn.",
    "sentiment_score": 0.4,
    "sentiment_label": "positive",
    "key_item_ids": ["n1", "n3"],
    "price_context": None,
}


def dump(**overrides: object) -> str:
    return json.dumps({**GOOD, **overrides}, ensure_ascii=False)


def test_valid_draft_passes() -> None:
    d = validate_draft(dump(), IDS)
    assert d.key_item_ids == ["n1", "n3"] and d.sentiment_label == "positive"


def test_label_thresholds() -> None:
    assert (label_for(0.21), label_for(0.2), label_for(-0.2), label_for(-0.21)) == (
        "positive", "neutral", "neutral", "negative")


def test_unknown_or_duplicate_ids_rejected() -> None:
    with pytest.raises(DraftInvalid, match="n9"):
        validate_draft(dump(key_item_ids=["n1", "n9"]), IDS)
    with pytest.raises(DraftInvalid, match="powtórz"):
        validate_draft(dump(key_item_ids=["n1", "n1"]), IDS)


def test_label_must_match_score() -> None:
    with pytest.raises(DraftInvalid, match="etykieta"):
        validate_draft(dump(sentiment_score=-0.5, sentiment_label="positive"), IDS)


@pytest.mark.parametrize("text", [
    "Warto kupić akcje przed wynikami.",
    "Trzymaj pozycję do publikacji wyników.",
    "We recommend buying the stock.",
    "Ustaw stop-loss poniżej wsparcia.",
])
def test_transaction_language_rejected(text: str) -> None:
    with pytest.raises(DraftInvalid, match="rekomendac"):
        validate_draft(dump(summary=f"Podsumowanie newsów. {text}"), IDS)


def test_descriptive_market_words_allowed() -> None:
    validate_draft(dump(summary="Na rynku trwała wyprzedaż; tech sell-off objął też NVIDIĘ.",
                        sentiment_score=-0.4, sentiment_label="negative"), IDS)


def test_reporting_analyst_actions_allowed() -> None:
    validate_draft(dump(summary="Analitycy podnieśli cel cenowy do 200 USD po wynikach."), IDS)


def test_bad_json_is_invalid() -> None:
    with pytest.raises(DraftInvalid):
        validate_draft("{nie json", IDS)


def test_schema_matches_model_fields() -> None:
    assert SYNTHESIS_SCHEMA["additionalProperties"] is False
    assert set(SYNTHESIS_SCHEMA["required"]) == set(GOOD)


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "llm" / "synthesis_response.json"


def test_real_model_response_validates() -> None:
    # Prawdziwa odpowiedź Haiku 4.5 z pierwszej syntezy (2026-10-06): regresja formatu modelu
    data = json.loads(FIX.read_text(encoding="utf-8"))
    draft = validate_draft(data["response"], set(data["allowed_ids"]))
    assert draft.key_item_ids and set(draft.key_item_ids) <= set(data["allowed_ids"])
