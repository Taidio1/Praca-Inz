"""Worker silnika informacyjnego: co ENGINE_INTERVAL_SECONDS cykl ingest -> ocena trafności.

Uruchomienie: cd backend && python -m src.engine.runner
Wymaga w .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; opcjonalnie FINNHUB_API_KEY
i ANTHROPIC_API_KEY (bez niego profile aktywów są zapasowe, z nazwy i aliasów).
"""

import asyncio

import anthropic
import httpx
import structlog
from supabase import acreate_client

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.engine.cycle import Stage, run_loop
from src.engine.ingest import IngestService
from src.relevance.embedder import build_embedder
from src.relevance.profiles import ProfileBuilder
from src.relevance.service import RelevanceService
from src.repositories.engine import EngineRepository
from src.repositories.ingest import IngestRepository
from src.repositories.relevance import RelevanceRepository
from src.sources.registry import build_sources
from src.synthesis.provider import AnthropicProvider

log = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY jest wymagany do zapisu itemów")
    client = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        ingest_repo = IngestRepository(client)
        relevance_repo = RelevanceRepository(client)
        provider = (
            AnthropicProvider(
                anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key),
                settings.llm_model,
                settings.pricing,
            )
            if settings.anthropic_api_key
            else None
        )
        if provider is None:
            log.warning("llm_disabled", reason="brak ANTHROPIC_API_KEY, profile zapasowe")
        relevance = RelevanceService(
            relevance_repo,
            ingest_repo,
            ProfileBuilder(provider, relevance_repo),
            build_embedder(settings.embedder, settings.embedding_model),
            threshold=settings.relevance_threshold,
            weights=settings.weights,
            floor=settings.cosine_floor,
            ceiling=settings.cosine_ceiling,
            batch_size=settings.relevance_batch_size,
            lookback_hours=settings.ingest_lookback_hours,
        )
        stages: list[tuple[str, Stage]] = [
            ("ingest", IngestService(build_sources(http, settings), ingest_repo)),
            ("relevance", relevance),
        ]
        log.info("engine_worker_started", interval=settings.engine_interval_seconds)
        await run_loop(stages, EngineRepository(client), settings.engine_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
