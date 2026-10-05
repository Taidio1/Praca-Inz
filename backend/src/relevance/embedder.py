"""Embeddingi do oceny trafności (spec §4 pkt 2): e5-small lokalnie na CPU."""

import asyncio
import math
from collections.abc import Sequence
from typing import Any, Protocol

_SNIPPET_CHARS = 400
# e5 wymaga prefiksu; dla podobieństwa symetrycznego (item vs profil) oba teksty jako "query:"
_E5_PREFIX = "query: "


class Embedder(Protocol):
    model_name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def item_text(title: str, snippet: str | None) -> str:
    if not snippet:
        return title
    return f"{title}. {snippet[:_SNIPPET_CHARS]}"


class LocalEmbedder:
    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.model_name = model_name
        self._batch = batch_size
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(
            [_E5_PREFIX + t for t in texts],
            batch_size=self._batch,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in v] for v in vectors]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, list(texts))


def build_embedder(kind: str, model_name: str) -> Embedder:
    if kind == "local":
        return LocalEmbedder(model_name)
    raise ValueError(f"EMBEDDER={kind}: obsługiwany jest tylko 'local'")
