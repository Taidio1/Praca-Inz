"""Worker notowań: co MARKET_REFRESH_SECONDS zapisuje snapshoty cen do Supabase.

Uruchomienie: cd backend && python -m src.marketdata.runner
Wymaga w .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, opcjonalnie FINNHUB_API_KEY.
"""

import asyncio

import httpx
import structlog
from supabase import acreate_client

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.marketdata.providers import BybitProvider, stock_quote_provider
from src.marketdata.repository import MarketDataRepository
from src.marketdata.service import MarketDataService

log = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY jest wymagany do zapisu snapshotów")
    client = await acreate_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    async with httpx.AsyncClient(timeout=10.0) as http:
        service = MarketDataService(
            crypto=BybitProvider(http),
            stocks=stock_quote_provider(http, settings.finnhub_api_key),
            repo=MarketDataRepository(client),
        )
        log.info("marketdata_worker_started", interval=settings.market_refresh_seconds)
        while True:
            try:
                written = await service.refresh_all()
                log.info("snapshots_written", count=written)
            except Exception:  # noqa: BLE001 — worker ma przeżyć każdy cykl
                log.exception("refresh_cycle_failed")
            await asyncio.sleep(settings.market_refresh_seconds)


if __name__ == "__main__":
    asyncio.run(main())
