import pytest

from src.core.config import Settings


def test_settings_reads_values_and_splits_cors() -> None:
    settings = Settings(
        supabase_url="http://localhost:54321",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        supabase_jwt_secret="secret",
        api_cors_origins="http://localhost:3000, https://opes.app",
        _env_file=None,
    )
    assert settings.supabase_url == "http://localhost:54321"
    assert settings.cors_origins == ["http://localhost:3000", "https://opes.app"]


def test_settings_defaults() -> None:
    settings = Settings(supabase_url="http://x", supabase_anon_key="a", _env_file=None)
    assert settings.supabase_service_role_key == ""
    assert settings.supabase_jwt_secret == ""
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_engine_settings_defaults() -> None:
    s = Settings(supabase_url="http://x", supabase_anon_key="a", _env_file=None)
    assert s.engine_interval_seconds == 900
    assert s.ingest_lookback_hours == 72
    assert s.rss_feeds == ""
    assert s.gdelt_min_interval_seconds == 6.0
    assert s.finnhub_news_rpm == 30


def test_relevance_and_llm_settings() -> None:
    s = Settings(supabase_url="http://x", supabase_anon_key="a", _env_file=None)
    assert s.relevance_threshold == 0.5
    assert s.weights == (0.5, 0.5)
    assert s.relevance_batch_size == 500
    assert s.embedder == "local"
    assert s.embedding_model == "intfloat/multilingual-e5-small"
    assert (s.cosine_floor, s.cosine_ceiling) == (0.83, 0.86)
    assert s.anthropic_api_key == ""
    assert s.llm_model == "claude-haiku-4-5"
    assert s.pricing["claude-haiku-4-5"] == (1.0, 5.0)


def test_weights_must_be_two_numbers() -> None:
    s = Settings(supabase_url="http://x", supabase_anon_key="a", relevance_weights="1",
                 _env_file=None)
    with pytest.raises(ValueError, match="RELEVANCE_WEIGHTS"):
        _ = s.weights


def test_synthesis_settings_defaults() -> None:
    s = Settings(supabase_url="http://x", supabase_anon_key="a", _env_file=None)
    assert s.llm_daily_budget_usd == 0.60
    assert (s.synth_important_score, s.synth_batch_min, s.synth_daily_hours) == (0.85, 3, 24)
    assert (s.synth_max_per_asset_day, s.synth_min_gap_minutes) == (6, 30)
    assert (s.synth_max_items, s.synth_max_per_cycle, s.synth_cost_reserve_usd) == (10, 10, 0.01)
