from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient, acreate_client  # VERIFY-DOCS: eksporty supabase-py v2

from src.analysis.service import CompanyAnalysisService
from src.analysis.sources import (
    FinnhubCompanyClient,
    SecClient,
    WikipediaClient,
    YahooChartClient,
)
from src.core.config import Settings, get_settings
from src.core.errors import AuthError
from src.marketdata.fx import FxService, default_fx_provider
from src.marketdata.fx_repository import FxRepository
from src.marketdata.historical import (
    BybitKlineProvider,
    HistoricalPriceService,
    stock_price_provider,
)
from src.marketdata.providers import (
    BybitProvider,
    QuoteCurrencyResolver,
    YahooQuoteProvider,
    stock_quote_provider,
)
from src.marketdata.repository import MarketDataRepository
from src.marketdata.service import MarketDataService
from src.marketdata.symbol_search import (
    AssetSearchService,
    BybitSymbolSearch,
    FinnhubSymbolSearch,
)
from src.repositories.assets import AssetsRepository
from src.repositories.engine import EngineRepository
from src.repositories.insights import InsightsRepository
from src.repositories.portfolio import PortfolioRepository
from src.repositories.settings import SettingsRepository
from src.repositories.snapshots import SnapshotsRepository
from src.repositories.source_items import SourceItemsRepository
from src.repositories.sources import SourcesRepository
from src.services.assets import AssetService
from src.services.feed import FeedService
from src.services.insights import InsightService
from src.services.portfolio import PortfolioService
from src.services.portfolio_history import PortfolioHistoryService
from src.services.settings import SettingsService
from src.services.sources import SourcesService


@dataclass(frozen=True)
class CurrentUser:
    id: str
    token: str


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")


def _decode_token(token: str, settings: Settings) -> dict[str, Any]:
    # Supabase podpisuje JWT symetrycznie (HS256, legacy) lub asymetrycznie
    # (ES256/RS256, JWKS) — wybór ścieżki po nagłówku tokenu.
    alg = jwt.get_unverified_header(token).get("alg", "")
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidKeyError("Token HS256, a SUPABASE_JWT_SECRET nie ustawiony")
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    signing_key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience="authenticated",
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    if credentials is None:
        raise AuthError("Brak tokenu uwierzytelniającego")
    try:
        claims = _decode_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise AuthError("Token nieprawidłowy lub wygasły") from exc
    return CurrentUser(id=str(claims["sub"]), token=credentials.credentials)


async def get_supabase(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncClient:
    client = await acreate_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(user.token)  # VERIFY-DOCS: RLS jako zalogowany użytkownik
    return client


async def _service_client(settings: Settings) -> AsyncClient:
    # Zapis do tabel globalnych (assets, fx_rates) wymaga service_role (RLS).
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_portfolio_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[PortfolioService]:
    assets = AssetsRepository(client)
    writer_client = await _service_client(settings)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        yield PortfolioService(
            assets=assets,
            assets_writer=AssetsRepository(writer_client),
            asset_search=AssetSearchService(
                local=assets,
                crypto=BybitSymbolSearch(http),
                stocks=FinnhubSymbolSearch(http, settings.finnhub_api_key),
            ),
            portfolio=PortfolioRepository(client),
            snapshots=SnapshotsRepository(client),
            insights=InsightsRepository(client),
            currencies=QuoteCurrencyResolver(YahooQuoteProvider(http)),
            fx=FxService(default_fx_provider(http), FxRepository(writer_client)),
            settings=SettingsRepository(client),
        )


async def get_portfolio_history_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[PortfolioHistoryService]:
    writer_client = await _service_client(settings)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        yield PortfolioHistoryService(
            portfolio=PortfolioRepository(client),
            prices=HistoricalPriceService(
                crypto=BybitKlineProvider(http), stocks=stock_price_provider(http)
            ),
            fx=FxService(default_fx_provider(http), FxRepository(writer_client)),
            settings=SettingsRepository(client),
        )


async def get_asset_search_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AssetSearchService]:
    async with httpx.AsyncClient(timeout=10.0) as http:
        yield AssetSearchService(
            local=AssetsRepository(client),
            crypto=BybitSymbolSearch(http),
            stocks=FinnhubSymbolSearch(http, settings.finnhub_api_key),
        )


async def get_feed_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
) -> FeedService:
    return FeedService(
        portfolio=PortfolioRepository(client), insights=InsightsRepository(client)
    )


async def get_asset_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
) -> AssetService:
    return AssetService(
        assets=AssetsRepository(client),
        snapshots=SnapshotsRepository(client),
        insights=InsightsRepository(client),
        sources=SourcesRepository(client),
    )


async def get_sources_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
) -> SourcesService:
    return SourcesService(
        audit=SourceItemsRepository(client),
        engine=EngineRepository(client),
        portfolio=PortfolioRepository(client),
        settings=SettingsRepository(client),
    )


async def get_insight_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
) -> InsightService:
    return InsightService(insights=InsightsRepository(client))


async def get_settings_service(
    client: Annotated[AsyncClient, Depends(get_supabase)],
) -> SettingsService:
    return SettingsService(settings=SettingsRepository(client))


async def get_historical_price_service() -> AsyncIterator[HistoricalPriceService]:
    # Stooq (zapasowe źródło) odpowiada przekierowaniem przy niektórych zapytaniach.
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        yield HistoricalPriceService(
            crypto=BybitKlineProvider(http), stocks=stock_price_provider(http)
        )


async def get_fx_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[FxService]:
    client = await _service_client(settings)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        yield FxService(default_fx_provider(http), FxRepository(client))


async def get_market_data_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[MarketDataService]:
    # Zapis snapshotów wymaga service_role (RLS); endpoint i tak jest za auth.
    client = await _service_client(settings)
    async with httpx.AsyncClient(timeout=10.0) as http:
        yield MarketDataService(
            crypto=BybitProvider(http),
            stocks=stock_quote_provider(http, settings.finnhub_api_key),
            repo=MarketDataRepository(client),
        )


async def get_company_analysis_service(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[CompanyAnalysisService]:
    # Dane publiczne (SEC/Yahoo/Wikipedia) — auth tylko po to, by API nie było otwartym proxy.
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http:
        yield CompanyAnalysisService(
            sec=SecClient(http, settings.sec_user_agent),
            yahoo=YahooChartClient(http),
            wiki=WikipediaClient(http),
            finnhub=FinnhubCompanyClient(http, settings.finnhub_api_key),
        )
