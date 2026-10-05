import json
from typing import Any

from src.relevance.profiles import (
    PROFILE_SCHEMA,
    ProfileBuilder,
    ProfileDraft,
    fallback_profile,
    profile_from_row,
    profile_user_message,
)
from src.sources.base import TrackedAsset
from src.synthesis.provider import LLMError, LLMResult

CDR = TrackedAsset(id="a-cdr", ticker="CDR.WA", name="CD PROJEKT S.A.", asset_type="stock",
                   aliases=("CD Projekt",))
BTC = TrackedAsset(id="a-btc", ticker="BTC", name="Bitcoin", asset_type="crypto")
GOOD = {
    "names": ["CD Projekt", " CD Projektu ", "CD Projekt", ""],
    "ticker_patterns": ["CDR"],
    "negative_terms": [],
    "keywords": ["gry wideo", "Wiedźmin", "Cyberpunk 2077"],
    "profile_text": "Polski producent gier wideo, twórca serii Wiedźmin i Cyberpunk 2077.",
}


def test_fallback_profile_from_name_and_aliases() -> None:
    p = fallback_profile(CDR)
    assert p.names == ("CD PROJEKT", "CD Projekt")
    assert p.ticker_patterns == ("CDR",)
    assert p.market == "gpw" and p.embedding is None and p.generated_by == "fallback"


def test_fallback_skips_ambiguous_short_ticker() -> None:
    ge = TrackedAsset(id="a-ge", ticker="GE", name="General Electric", asset_type="stock")
    assert fallback_profile(ge).ticker_patterns == ()


def test_draft_cleans_lists() -> None:
    d = ProfileDraft.model_validate(GOOD)
    assert d.names == ["CD Projekt", "CD Projektu"]


def test_schema_requires_all_fields_and_forbids_extra() -> None:
    assert PROFILE_SCHEMA["additionalProperties"] is False
    assert set(PROFILE_SCHEMA["required"]) == set(ProfileDraft.model_fields)


def test_user_message_carries_asset_facts() -> None:
    msg = profile_user_message(CDR)
    assert "CDR.WA" in msg and "CD PROJEKT S.A." in msg and "gpw" in msg and "CD Projekt" in msg


class FakeProvider:
    name = "anthropic"
    model = "claude-haiku-4-5"

    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error

    async def complete(self, *, system: str, user: str, max_tokens: int,
                       schema: dict[str, Any]) -> LLMResult:
        if self.error:
            raise self.error
        assert self.text is not None
        return LLMResult(text=self.text, provider="anthropic", model=self.model, tokens_in=300,
                         tokens_out=150, cache_read_tokens=0, latency_ms=900, cost_usd=0.00105)


class FakeRuns:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert_run(self, row: dict[str, Any]) -> str:
        self.rows.append(row)
        return f"run-{len(self.rows)}"


async def test_build_returns_draft_and_logs_ok_run() -> None:
    runs = FakeRuns()
    built = await ProfileBuilder(FakeProvider(json.dumps(GOOD)), runs).build(CDR)
    assert built is not None
    draft, run_id = built
    assert run_id == "run-1" and draft.ticker_patterns == ["CDR"]
    row = runs.rows[0]
    assert (row["purpose"], row["status"], row["asset_id"]) == ("profile", "ok", "a-cdr")
    assert row["cost_usd"] == 0.00105 and "CDR.WA" in row["prompt"]


async def test_build_returns_none_and_logs_error_run() -> None:
    runs = FakeRuns()
    assert await ProfileBuilder(FakeProvider(error=LLMError("stop_reason=refusal")),
                                runs).build(BTC) is None
    assert runs.rows[0]["status"] == "error" and "refusal" in runs.rows[0]["error"]


async def test_build_invalid_json_logged_as_invalid() -> None:
    runs = FakeRuns()
    assert await ProfileBuilder(FakeProvider('{"names": []}'), runs).build(BTC) is None
    assert runs.rows[0]["status"] == "invalid" and runs.rows[0]["response"] == '{"names": []}'


async def test_no_provider_means_fallback_without_run() -> None:
    runs = FakeRuns()
    assert await ProfileBuilder(None, runs).build(BTC) is None
    assert runs.rows == []


def test_profile_from_row_parses_pgvector_text() -> None:
    row = {"asset_id": "a-btc", "names": ["Bitcoin"], "ticker_patterns": ["BTC"],
           "negative_terms": [], "keywords": ["kryptowaluta"], "market": "crypto",
           "profile_text": "Kryptowaluta.", "embedding": "[0.5,0.25]", "generated_by": "llm"}
    p = profile_from_row(row)
    assert p.embedding == (0.5, 0.25) and p.generated_by == "llm"


def test_llm_short_tickers_are_dropped() -> None:
    # "F" albo "GE" łapałyby co drugie słowo pisane wielką literą
    d = ProfileDraft.model_validate({**GOOD, "ticker_patterns": ["F", "NVDA", "GE"]})
    assert d.ticker_patterns == ["NVDA"]


def test_verbose_model_output_is_trimmed_not_rejected() -> None:
    # Odrzucenie zbyt długiego profilu = płatne wywołanie co cykl; przycinamy zamiast tego
    d = ProfileDraft.model_validate({**GOOD, "keywords": [f"k{i}" for i in range(30)],
                                     "profile_text": "x" * 900})
    assert len(d.keywords) == 20 and len(d.profile_text) == 800


async def test_billed_error_is_logged_with_cost() -> None:
    billed = LLMResult(text="", provider="anthropic", model="claude-haiku-4-5", tokens_in=640,
                       tokens_out=1024, cache_read_tokens=0, latency_ms=4000, cost_usd=0.00576)
    runs = FakeRuns()
    err = LLMError("stop_reason=max_tokens", result=billed)
    assert await ProfileBuilder(FakeProvider(error=err), runs).build(BTC) is None
    assert runs.rows[0]["cost_usd"] == 0.00576 and runs.rows[0]["tokens_out"] == 1024
