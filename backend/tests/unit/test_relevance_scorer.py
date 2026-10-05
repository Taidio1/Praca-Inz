from src.relevance.matcher import MatchResult
from src.relevance.scorer import score_pair

TITLE = MatchResult(score=1.0, hits=('ticker "CDR" w tytule',))
KW = MatchResult(score=0.4, hits=("słowa kluczowe: gry, Wiedźmin",))
ARGS = {"weights": (0.5, 0.5), "floor": 0.70, "ceiling": 0.90}


def test_combined_score_scales_cosine() -> None:
    p = score_pair(TITLE, 0.81, **ARGS)
    assert p.method == "combined"
    assert p.score == 0.775  # 0.5*1.0 + 0.5*((0.81-0.70)/0.20)
    assert p.embedding_score == 0.81 and p.match_score == 1.0
    assert p.reason == 'ticker "CDR" w tytule (1.00); podobieństwo 0.81 → 0.55; wynik 0.78'


def test_cosine_is_clipped() -> None:
    assert score_pair(KW, 0.60, **ARGS).score == 0.2
    assert score_pair(KW, 0.99, **ARGS).score == 0.7


def test_without_embedding_score_is_match_only() -> None:
    p = score_pair(KW, None, **ARGS)
    assert (p.method, p.score, p.embedding_score) == ("ticker_match", 0.4, None)
    assert "brak embeddingu" in p.reason
