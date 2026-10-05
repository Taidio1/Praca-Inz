"""Dostawca LLM za wspólnym interfejsem (spec §5). Etap 2: profile aktywów; etap 3: synteza."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

# Odczyt z cache promptu kosztuje 0.1 stawki wejściowej
_CACHE_READ_FACTOR = 0.1


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cache_read_tokens: int
    latency_ms: int
    cost_usd: float


class LLMError(Exception):
    """Wywołanie LLM nie dało użytecznej odpowiedzi (błąd API, odmowa, ucięcie).

    `result` niesie zużycie i koszt, gdy wywołanie zostało rozliczone (odmowa, ucięcie).
    """

    def __init__(self, message: str, result: "LLMResult | None" = None) -> None:
        super().__init__(message)
        self.result = result


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(
        self, *, system: str, user: str, max_tokens: int, schema: dict[str, Any]
    ) -> LLMResult: ...


def cost_usd(
    pricing: Mapping[str, tuple[float, float]],
    model: str,
    tokens_in: int,
    tokens_out: int,
    cache_read_tokens: int = 0,
) -> float:
    price_in, price_out = pricing[model]
    total = (
        tokens_in * price_in
        + cache_read_tokens * price_in * _CACHE_READ_FACTOR
        + tokens_out * price_out
    )
    return round(total / 1_000_000, 6)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        client: Any,
        model: str,
        pricing: Mapping[str, tuple[float, float]],
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if model not in pricing:
            # Bez ceny nie da się pilnować budżetu: błąd konfiguracji, nie ciche 0 USD
            raise ValueError(f"Model {model} nie ma ceny w cenniku LLM_PRICING")
        self._client = client
        self.model = model
        self._pricing = pricing
        self._clock = clock

    async def complete(
        self, *, system: str, user: str, max_tokens: int, schema: dict[str, Any]
    ) -> LLMResult:
        started = self._clock()
        try:
            msg = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        latency_ms = round((self._clock() - started) * 1000)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        usage = msg.usage
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        result = LLMResult(
            text=text,
            provider=self.name,
            model=self.model,
            tokens_in=int(usage.input_tokens),
            tokens_out=int(usage.output_tokens),
            cache_read_tokens=cache_read,
            latency_ms=latency_ms,
            cost_usd=cost_usd(
                self._pricing, self.model, usage.input_tokens, usage.output_tokens, cache_read
            ),
        )
        if msg.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"stop_reason={msg.stop_reason}", result=result)
        return result
