from src.repositories.relevance import from_pgvector, group_by_keys, to_pgvector


def test_pgvector_roundtrip() -> None:
    text = to_pgvector([0.5, -0.25, 1.0])
    assert text == "[0.500000,-0.250000,1.000000]"
    assert from_pgvector(text) == (0.5, -0.25, 1.0)
    assert from_pgvector(None) is None
    assert from_pgvector([1, 2]) == (1.0, 2.0)


def test_update_items_groups_rows_by_keys() -> None:
    a = {"id": "1", "best_score": 0.5, "embedding": "[1]"}
    b = {"id": "2", "best_score": 0.2}
    c = {"id": "3", "best_score": 0.9, "embedding": "[2]"}
    groups = group_by_keys([a, b, c])
    assert groups == [[a, c], [b]]
