from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from src.synthesis.provider import AnthropicProvider, LLMError, cost_usd

PRICING = {"claude-haiku-4-5": (1.0, 5.0)}


def test_cost_counts_input_output_and_cache_reads() -> None:
    # 1000 we × 1 USD + 200 wy × 5 USD + 2000 cache × 0.1 USD, wszystko na 1M tokenów
    assert cost_usd(PRICING, "claude-haiku-4-5", 1000, 200, 2000) == 0.0022


def test_unknown_model_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="cenniku"):
        AnthropicProvider(client=object(), model="claude-x", pricing=PRICING)


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def response(text: str, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0),
    )


def provider(messages: FakeMessages) -> AnthropicProvider:
    ticks = iter([10.0, 10.25])
    return AnthropicProvider(SimpleNamespace(messages=messages), "claude-haiku-4-5", PRICING,
                             clock=lambda: next(ticks))


async def test_complete_sends_schema_and_maps_usage() -> None:
    msgs = FakeMessages(response('{"ok": true}'))
    result = await provider(msgs).complete(system="S", user="U", max_tokens=512,
                                           schema={"type": "object"})
    assert msgs.kwargs["output_config"] == {"format": {"type": "json_schema",
                                                      "schema": {"type": "object"}}}
    assert msgs.kwargs["system"] == "S"
    assert msgs.kwargs["messages"] == [{"role": "user", "content": "U"}]
    assert result.text == '{"ok": true}'
    assert (result.tokens_in, result.tokens_out, result.latency_ms) == (1000, 200, 250)
    assert result.cost_usd == 0.002
    assert (result.provider, result.model) == ("anthropic", "claude-haiku-4-5")


async def test_refusal_and_truncation_are_errors() -> None:
    for stop in ("refusal", "max_tokens"):
        with pytest.raises(LLMError, match=stop):
            await provider(FakeMessages(response("{}", stop))).complete(
                system="S", user="U", max_tokens=10, schema={})


async def test_api_error_wrapped() -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    with pytest.raises(LLMError, match="APIConnectionError"):
        await provider(FakeMessages(error=err)).complete(system="S", user="U", max_tokens=10,
                                                         schema={})


async def test_refusal_error_carries_billed_usage() -> None:
    # Odmowa i ucięcie są płatne: koszt musi trafić do llm_runs i budżetu
    with pytest.raises(LLMError) as info:
        await provider(FakeMessages(response("{}", "max_tokens"))).complete(
            system="S", user="U", max_tokens=10, schema={})
    assert info.value.result is not None
    assert (info.value.result.tokens_in, info.value.result.cost_usd) == (1000, 0.002)


async def test_api_error_has_no_usage() -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    with pytest.raises(LLMError) as info:
        await provider(FakeMessages(error=anthropic.APIConnectionError(request=req))).complete(
            system="S", user="U", max_tokens=10, schema={})
    assert info.value.result is None
