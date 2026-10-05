"""Profil aktywa dla filtra trafności (spec §4): generowany raz przez LLM, z zapasem."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

from src.repositories.relevance import from_pgvector, to_pgvector
from src.sources.base import Market, TrackedAsset
from src.sources.gdelt import gdelt_term
from src.synthesis.provider import LLMError, LLMProvider

_MIN_TICKER = 3  # krótsze tickery (GE, F) są zbyt wieloznaczne w tekście


@dataclass(frozen=True)
class AssetProfile:
    asset_id: str
    names: tuple[str, ...]
    ticker_patterns: tuple[str, ...]
    negative_terms: tuple[str, ...]
    keywords: tuple[str, ...]
    market: Market
    profile_text: str
    embedding: tuple[float, ...] | None
    generated_by: Literal["llm", "manual", "fallback"]


def _clean(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = " ".join(v.split())
        if v and v not in out:
            out.append(v)
    return out


_LIMITS = {"names": 12, "ticker_patterns": 6, "negative_terms": 10, "keywords": 20}
_PROFILE_TEXT_MAX = 800


class ProfileDraft(BaseModel):
    """Wynik LLM. Zbyt długie listy i opis przycinamy zamiast odrzucać: odrzucenie
    oznaczałoby płatne ponowienie w każdym cyklu."""

    names: list[str] = Field(min_length=1)
    ticker_patterns: list[str]
    negative_terms: list[str]
    keywords: list[str]
    profile_text: str = Field(min_length=20)

    @field_validator("names", "ticker_patterns", "negative_terms", "keywords", mode="after")
    @classmethod
    def _dedupe_and_cap(cls, v: list[str], info: ValidationInfo) -> list[str]:
        cleaned = _clean(v)
        if info.field_name == "ticker_patterns":
            cleaned = [t for t in cleaned if len(t) >= _MIN_TICKER]
        return cleaned[: _LIMITS[str(info.field_name)]]

    @field_validator("names", mode="after")
    @classmethod
    def _names_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("names nie może być puste")
        return v

    @field_validator("profile_text", mode="after")
    @classmethod
    def _cap_text(cls, v: str) -> str:
        return v.strip()[:_PROFILE_TEXT_MAX]


_STR_LIST = {"type": "array", "items": {"type": "string"}}
PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "names": _STR_LIST,
        "ticker_patterns": _STR_LIST,
        "negative_terms": _STR_LIST,
        "keywords": _STR_LIST,
        "profile_text": {"type": "string"},
    },
    "required": ["names", "ticker_patterns", "negative_terms", "keywords", "profile_text"],
    "additionalProperties": False,
}

PROFILE_SYSTEM = """Budujesz profil aktywa finansowego dla filtra trafności newsów.
Zwróć wyłącznie JSON zgodny ze schematem:
- names: oficjalna nazwa i nazwy potoczne; dla spółek z GPW także odmiany przez przypadki
  spotykane w polskich nagłówkach (np. "Orlen", "Orlenu", "Orlenem").
- ticker_patterns: tickery i symbole, które w tekście jednoznacznie oznaczają to aktywo,
  pisane wielkimi literami; pomiń krótkie i wieloznaczne.
- negative_terms: TYLKO wyrażenia zawierające nazwę lub ticker, które oznaczają INNY podmiot
  albo rzecz niezwiązaną z aktywem (np. "Ethernet" dla ETH, "Bitcoin Cash" dla BTC).
  Nigdy nie wpisuj tu produktów, marek, usług ani spółek zależnych samego aktywa:
  news o nich dotyczy aktywa. Jeśli nie ma takich wyrażeń, zwróć pustą listę.
- keywords: branża, produkty, kluczowe osoby; dla ETF: indeks, region, klasa aktywów.
- profile_text: 2-3 zdania opisu po polsku i po angielsku.
Nie wymyślaj faktów, których nie jesteś pewien. Nie oceniaj inwestycyjnie."""


def profile_user_message(asset: TrackedAsset) -> str:
    aliases = ", ".join(asset.aliases) or "brak"
    return (
        f"Aktywo: {asset.name}\nTicker: {asset.ticker}\nTyp: {asset.asset_type}\n"
        f"Rynek: {asset.market}\nZnane aliasy: {aliases}"
    )


def _base_ticker(ticker: str) -> str:
    return ticker.split(".", 1)[0].upper()


def fallback_profile(asset: TrackedAsset) -> AssetProfile:
    names = _clean([gdelt_term(asset.name) or asset.name, *asset.aliases])
    base = _base_ticker(asset.ticker)
    return AssetProfile(
        asset_id=asset.id,
        names=tuple(names),
        ticker_patterns=(base,) if len(base) >= _MIN_TICKER else (),
        negative_terms=(),
        keywords=(),
        market=asset.market,
        profile_text=asset.name,
        embedding=None,
        generated_by="fallback",
    )


def profile_from_row(row: dict[str, Any]) -> AssetProfile:
    return AssetProfile(
        asset_id=row["asset_id"],
        names=tuple(row["names"]),
        ticker_patterns=tuple(row["ticker_patterns"]),
        negative_terms=tuple(row["negative_terms"]),
        keywords=tuple(row["keywords"]),
        market=row["market"],
        profile_text=row["profile_text"],
        embedding=from_pgvector(row.get("embedding")),
        generated_by=row["generated_by"],
    )


def profile_to_row(
    asset: TrackedAsset,
    draft: ProfileDraft,
    embedding: Sequence[float] | None,
    embedding_model: str | None,
    llm_run_id: str,
) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "names": draft.names,
        "ticker_patterns": draft.ticker_patterns,
        "negative_terms": draft.negative_terms,
        "keywords": draft.keywords,
        "market": asset.market,
        "profile_text": draft.profile_text,
        "embedding": to_pgvector(embedding) if embedding is not None else None,
        "embedding_model": embedding_model if embedding is not None else None,
        "generated_by": "llm",
        "llm_run_id": llm_run_id,
    }


class LlmRunsRepo(Protocol):
    async def insert_run(self, row: dict[str, Any]) -> str: ...


class ProfileBuilder:
    def __init__(self, provider: LLMProvider | None, runs: LlmRunsRepo) -> None:
        self._provider = provider
        self._runs = runs

    async def build(self, asset: TrackedAsset) -> tuple[ProfileDraft, str] | None:
        if self._provider is None:
            return None  # brak klucza LLM: profil zapasowy
        user = profile_user_message(asset)
        prompt = f"{PROFILE_SYSTEM}\n\n{user}"
        base = {"asset_id": asset.id, "provider": self._provider.name,
                "model": self._provider.model, "prompt": prompt, "purpose": "profile"}
        try:
            result = await self._provider.complete(
                system=PROFILE_SYSTEM, user=user, max_tokens=1024, schema=PROFILE_SCHEMA
            )
        except LLMError as exc:
            billed = exc.result
            usage_row = (
                {"tokens_in": billed.tokens_in, "tokens_out": billed.tokens_out,
                 "cache_read_tokens": billed.cache_read_tokens,
                 "latency_ms": billed.latency_ms, "cost_usd": billed.cost_usd}
                if billed else {}
            )
            await self._runs.insert_run({**base, **usage_row,
                                         "response": billed.text if billed else "",
                                         "status": "error", "error": str(exc)})
            return None
        usage = {"tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
                 "cache_read_tokens": result.cache_read_tokens,
                 "latency_ms": result.latency_ms, "cost_usd": result.cost_usd}
        try:
            draft = ProfileDraft.model_validate_json(result.text)
        except ValidationError as exc:
            await self._runs.insert_run({**base, **usage, "response": result.text,
                                         "status": "invalid", "error": str(exc)[:500]})
            return None
        run_id = await self._runs.insert_run({**base, **usage, "response": result.text,
                                              "status": "ok"})
        return draft, run_id
