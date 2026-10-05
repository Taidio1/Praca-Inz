import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Dane rynkowe: Finnhub (akcje/ETF); Bybit v5 nie wymaga klucza
    finnhub_api_key: str = ""
    market_refresh_seconds: int = 60
    # Analiza spółek: SEC EDGAR wymaga User-Agent z danymi kontaktowymi operatora
    sec_user_agent: str = "Opes research tool (praca inzynierska) opes-research@example.com"
    # Silnik informacyjny (spec 2026-10-05): cykl ingestu newsów
    engine_interval_seconds: int = 900
    ingest_lookback_hours: int = 72
    # JSON {"crypto": [url, ...], "gpw": [...], ...} per rynek; pusty => domyślne feedy
    rss_feeds: str = ""
    # GDELT DOC API odrzuca częstsze zapytania niż 1/5 s
    gdelt_min_interval_seconds: float = 6.0
    # Finnhub free: 60 req/min łącznie z workerem notowań
    finnhub_news_rpm: int = 30
    # Filtr trafności (spec §4)
    relevance_threshold: float = 0.5
    relevance_weights: str = "0.5,0.5"  # waga dopasowania, waga embeddingu
    relevance_batch_size: int = 500
    embedder: str = "local"
    embedding_model: str = "intfloat/multilingual-e5-small"
    # e5 daje wysokie podobieństwa bazowe: cosinus skalujemy z [floor, ceiling] do [0, 1].
    # Kalibracja 2026-10-06 (scripts/calibrate_relevance.py): p90 losowych par 0.826,
    # p90 trafień w tytule 0.864.
    cosine_floor: float = 0.83
    cosine_ceiling: float = 0.86
    # LLM (profile aktywów; w etapie 3 synteza)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"
    # USD za 1M tokenów [wejście, wyjście], stan cennika 2026-09-25
    llm_pricing: str = '{"claude-haiku-4-5": [1.0, 5.0], "claude-sonnet-5-5": [2.0, 10.0]}'

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def weights(self) -> tuple[float, float]:
        parts = [p.strip() for p in self.relevance_weights.split(",") if p.strip()]
        if len(parts) != 2:
            raise ValueError("RELEVANCE_WEIGHTS: oczekiwane dwie liczby, np. 0.5,0.5")
        return float(parts[0]), float(parts[1])

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        data = json.loads(self.llm_pricing)
        return {model: (float(v[0]), float(v[1])) for model, v in data.items()}


@lru_cache
def get_settings() -> Settings:
    # Wymagane pola przychodzą ze zmiennych środowiskowych / .env
    return Settings()  # type: ignore[call-arg]
