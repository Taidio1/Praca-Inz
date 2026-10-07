from src.relevance.evaluation import EvaluationLabel, calculate_metrics


def test_calculate_metrics_builds_confusion_matrix_and_scores() -> None:
    metrics = calculate_metrics(
        [
            EvaluationLabel(relevant=True, score=0.8),  # TP
            EvaluationLabel(relevant=False, score=0.7),  # FP
            EvaluationLabel(relevant=True, score=0.2),  # FN
            EvaluationLabel(relevant=False, score=None),  # TN
        ],
        threshold=0.5,
    )

    assert (metrics.labeled_pairs, metrics.true_positive, metrics.false_positive) == (4, 1, 1)
    assert (metrics.false_negative, metrics.true_negative) == (1, 1)
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5


def test_calculate_metrics_returns_no_scores_without_labels() -> None:
    metrics = calculate_metrics([], threshold=0.5)

    assert metrics.labeled_pairs == 0
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.f1 is None


def test_calculate_metrics_uses_threshold_for_prediction() -> None:
    metrics = calculate_metrics([EvaluationLabel(relevant=True, score=0.5)], threshold=0.5)

    assert (metrics.true_positive, metrics.false_negative) == (1, 0)
