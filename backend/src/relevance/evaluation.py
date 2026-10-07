"""Metryki jakości filtra na ręcznie oznaczonych parach item–aktywo."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationLabel:
    relevant: bool
    score: float | None


@dataclass(frozen=True)
class EvaluationMetrics:
    labeled_pairs: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float | None
    recall: float | None
    f1: float | None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def calculate_metrics(labels: Iterable[EvaluationLabel], *, threshold: float) -> EvaluationMetrics:
    """Porównuje decyzję score >= threshold z ręczną etykietą trafności."""
    tp = fp = fn = tn = 0
    for label in labels:
        predicted_relevant = label.score is not None and label.score >= threshold
        if label.relevant and predicted_relevant:
            tp += 1
        elif not label.relevant and predicted_relevant:
            fp += 1
        elif label.relevant:
            fn += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return EvaluationMetrics(
        labeled_pairs=tp + fp + fn + tn,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        precision=precision,
        recall=recall,
        f1=f1,
    )
