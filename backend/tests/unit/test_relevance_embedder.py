import math

import pytest

from src.relevance.embedder import LocalEmbedder, build_embedder, cosine, item_text


def test_cosine_basic_cases() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 2.0]) == 0.0
    assert math.isclose(cosine([1.0, 1.0], [1.0, 0.0]), 1 / math.sqrt(2))
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0  # zerowy wektor: brak podobieństwa


def test_item_text_truncates_snippet() -> None:
    assert item_text("Tytuł", None) == "Tytuł"
    assert item_text("Tytuł", "x" * 1000) == "Tytuł. " + "x" * 400


def test_unknown_embedder_kind_rejected() -> None:
    with pytest.raises(ValueError, match="EMBEDDER"):
        build_embedder("openai", "m")


@pytest.mark.model
async def test_real_model_separates_related_from_unrelated() -> None:
    # Prawdziwy model e5: news o bitcoinie bliżej profilu BTC niż news o Orlenie.
    emb = LocalEmbedder("intfloat/multilingual-e5-small")
    profile, btc, orlen = await emb.embed([
        "Bitcoin to zdecentralizowana kryptowaluta. Bitcoin is a decentralized cryptocurrency.",
        "Metaplanet added 1,000 bitcoin net in the third quarter bringing holdings to 44,000 BTC",
        "Orlen, KGHM i PKO szarpnęły indeksem blue chipów",
    ])
    assert len(profile) == 384
    assert cosine(profile, btc) > cosine(profile, orlen)
