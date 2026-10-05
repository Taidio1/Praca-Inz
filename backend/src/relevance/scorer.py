"""Łączny wynik trafności pary item-aktywo (spec §4 pkt 3)."""

from dataclasses import dataclass
from typing import Literal

from src.relevance.matcher import MatchResult


@dataclass(frozen=True)
class PairScore:
    score: float
    method: Literal["ticker_match", "combined"]
    reason: str
    match_score: float
    embedding_score: float | None  # surowy cosinus (do kalibracji progów)


def score_pair(
    match: MatchResult,
    cos: float | None,
    *,
    weights: tuple[float, float],
    floor: float,
    ceiling: float,
) -> PairScore:
    hits = ", ".join(match.hits)
    if cos is None:
        return PairScore(
            score=round(match.score, 4),
            method="ticker_match",
            reason=f"{hits} ({match.score:.2f}); brak embeddingu, wynik = dopasowanie",
            match_score=match.score,
            embedding_score=None,
        )
    norm = min(1.0, max(0.0, (cos - floor) / (ceiling - floor)))
    score = round(weights[0] * match.score + weights[1] * norm, 4)
    return PairScore(
        score=score,
        method="combined",
        reason=(
            f"{hits} ({match.score:.2f}); podobieństwo {cos:.2f} → {norm:.2f}; "
            f"wynik {score:.2f}"
        ),
        match_score=match.score,
        embedding_score=round(cos, 4),
    )
