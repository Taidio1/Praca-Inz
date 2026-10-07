from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.deps import CurrentUser
from src.core.errors import NotFoundError, ValidationError
from src.marketdata.fx import FxRate, FxRateError
from src.marketdata.historical import HistoricalPrice, HistoricalPriceError
from src.schemas.assets import AssetOut
from src.schemas.feed import FeedPage
from src.schemas.portfolio import (
    PortfolioPositionOut,
    PositionCreate,
    TransactionDeleteResult,
    TransactionOut,
    TransactionUpdate,
)
from src.schemas.sources import (
    EngineStatusOut,
    EvaluationMetricsOut,
    FunnelOut,
    RawSourceItemOut,
    SourcePage,
)

USER = CurrentUser(id="11111111-1111-1111-1111-111111111111", token="t")
ASSET = AssetOut(
    id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    ticker="BTC",
    name="Bitcoin",
    asset_type="crypto",
    currency="USD",
)
POSITION = PortfolioPositionOut(
    id=UUID("eeeeeeee-0000-0000-0000-000000000001"), asset=ASSET, quantity=0.5
)


class FakePortfolioService:
    async def list_positions(self) -> list[PortfolioPositionOut]:
        return [POSITION]

    async def add_position(self, user_id: str, payload: PositionCreate) -> PortfolioPositionOut:
        if payload.ticker == "XXX":
            raise ValidationError("Nieznany ticker: XXX (crypto)")
        return POSITION

    async def remove_position(self, position_id: str) -> None:
        raise NotFoundError("Pozycja nie istnieje")

    async def list_transactions(self, position_id: str) -> list[TransactionOut]:
        if position_id == "eeeeeeee-0000-0000-0000-000000000099":
            raise NotFoundError("Pozycja nie istnieje")
        return [
            TransactionOut(
                id=UUID("ffffffff-0000-0000-0000-000000000001"),
                quantity=0.5,
                price=50000.0,
                currency="USD",
                fx_rate=1.0,
                fx_rate_date=date(2026, 7, 1),
                purchased_at=date(2026, 7, 1),
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            )
        ]

    async def update_transaction(
        self, position_id: str, tx_id: str, payload: TransactionUpdate
    ) -> PortfolioPositionOut:
        if tx_id == "ffffffff-0000-0000-0000-000000000099":
            raise NotFoundError("Transakcja nie istnieje")
        return POSITION

    async def delete_transaction(self, position_id: str, tx_id: str) -> TransactionDeleteResult:
        if tx_id == "ffffffff-0000-0000-0000-000000000099":
            raise NotFoundError("Transakcja nie istnieje")
        removed = tx_id == "ffffffff-0000-0000-0000-000000000001"
        return TransactionDeleteResult(position_removed=removed)


class FakeFeedService:
    async def get_feed(self, *, asset_id, sentiment, cursor, limit):  # type: ignore[no-untyped-def]
        return FeedPage(items=[], next_cursor=datetime(2026, 7, 3, tzinfo=UTC))


class FakeMarketDataService:
    async def refresh_all(self) -> int:
        return 3


class FakeHistoricalPriceService:
    async def price_on(self, ticker: str, asset_type: str, on: date) -> HistoricalPrice:
        if ticker == "XXXX":
            raise HistoricalPriceError(f"Stooq: brak notowań dla {ticker.lower()}.us")
        return HistoricalPrice(price=215.75, price_date=on, source="stooq", currency="USD")

    async def price_series(self, ticker: str, asset_type: str, days: int) -> list[HistoricalPrice]:
        if ticker == "XXXX":
            raise HistoricalPriceError(f"Stooq: brak notowań dla {ticker.lower()}.us")
        return [
            HistoricalPrice(
                price=213.0, price_date=date(2026, 7, 2), source="stooq", currency="USD"
            ),
            HistoricalPrice(
                price=215.75, price_date=date(2026, 7, 3), source="stooq", currency="USD"
            ),
        ]


class FakeFxService:
    async def rate_on(self, base: str, quote: str, on: date) -> FxRate:
        if quote == "CHF":
            raise FxRateError("brak kursu")
        # sobota 2026-10-03 → kurs z piątku
        return FxRate(rate=3.8881, rate_date=date(2026, 10, 2), source="nbp")


def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_no_auth(app: FastAPI) -> None:
    async with client_for(app) as client:
        res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_missing_token_gives_401_error_shape(app: FastAPI) -> None:
    async with client_for(app) as client:
        res = await client.get("/api/v1/portfolio")
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "auth_error"


async def test_get_portfolio_returns_positions(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.get("/api/v1/portfolio")
    assert res.status_code == 200
    assert res.json()[0]["asset"]["ticker"] == "BTC"


async def test_post_portfolio_unknown_ticker_gives_422(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.post(
            "/api/v1/portfolio",
            json={"ticker": "XXX", "asset_type": "crypto", "quantity": 1},
        )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


async def test_delete_missing_position_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.delete("/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000099")
    assert res.status_code == 404


async def test_get_position_transactions_returns_list(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001/transactions"
        )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["price"] == 50000.0
    assert body[0]["purchased_at"] == "2026-07-01"


async def test_get_transactions_missing_position_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000099/transactions"
        )
    assert res.status_code == 404


async def test_price_on_date_returns_price(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-on-date",
            params={"ticker": "AAPL", "asset_type": "stock", "date": "2026-07-01"},
        )
    assert res.status_code == 200
    assert res.json() == {
        "price": 215.75,
        "price_date": "2026-07-01",
        "source": "stooq",
        "currency": "USD",
    }


async def test_price_on_date_unknown_ticker_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-on-date",
            params={"ticker": "XXXX", "asset_type": "stock", "date": "2026-07-01"},
        )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


async def test_patch_transaction_returns_updated_position(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.patch(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001"
            "/transactions/ffffffff-0000-0000-0000-000000000001",
            json={"quantity": 1, "price": 60000.0, "purchased_at": "2026-07-01"},
        )
    assert res.status_code == 200
    assert res.json()["asset"]["ticker"] == "BTC"


async def test_patch_transaction_unknown_tx_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.patch(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001"
            "/transactions/ffffffff-0000-0000-0000-000000000099",
            json={"quantity": 1, "price": 60000.0, "purchased_at": "2026-07-01"},
        )
    assert res.status_code == 404


async def test_patch_transaction_future_date_gives_422(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.patch(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001"
            "/transactions/ffffffff-0000-0000-0000-000000000001",
            json={"quantity": 1, "price": 60000.0, "purchased_at": "2100-01-01"},
        )
    assert res.status_code == 422


async def test_delete_transaction_returns_position_removed_flag(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.delete(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001"
            "/transactions/ffffffff-0000-0000-0000-000000000001"
        )
    assert res.status_code == 200
    assert res.json() == {"position_removed": True}


async def test_delete_transaction_unknown_tx_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_portfolio_service] = FakePortfolioService
    async with client_for(app) as client:
        res = await client.delete(
            "/api/v1/portfolio/eeeeeeee-0000-0000-0000-000000000001"
            "/transactions/ffffffff-0000-0000-0000-000000000099"
        )
    assert res.status_code == 404


async def test_price_series_returns_points(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-series",
            params={"ticker": "AAPL", "asset_type": "stock", "days": 90},
        )
    assert res.status_code == 200
    assert res.json() == {
        "points": [
            {"price_date": "2026-07-02", "price": 213.0},
            {"price_date": "2026-07-03", "price": 215.75},
        ],
        "currency": "USD",
    }


async def test_price_series_source_error_returns_empty_points(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-series",
            params={"ticker": "XXXX", "asset_type": "stock", "days": 90},
        )
    assert res.status_code == 200
    assert res.json() == {"points": [], "currency": None}


async def test_price_series_rejects_days_out_of_range(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-series",
            params={"ticker": "AAPL", "asset_type": "stock", "days": 400},
        )
    assert res.status_code == 422


async def test_price_on_date_future_date_gives_422(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_historical_price_service] = FakeHistoricalPriceService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/price-on-date",
            params={"ticker": "AAPL", "asset_type": "stock", "date": "2100-01-01"},
        )
    assert res.status_code == 422


async def test_refresh_prices_returns_count(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_market_data_service] = FakeMarketDataService
    async with client_for(app) as client:
        res = await client.post("/api/v1/portfolio/refresh")
    assert res.status_code == 200
    assert res.json() == {"refreshed": 3}


async def test_feed_endpoint_serializes_page(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_feed_service] = FakeFeedService
    async with client_for(app) as client:
        res = await client.get("/api/v1/feed?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["next_cursor"].startswith("2026-07-03")


async def test_feed_rejects_bad_limit(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_feed_service] = FakeFeedService
    async with client_for(app) as client:
        res = await client.get("/api/v1/feed?limit=0")
    assert res.status_code == 422


async def test_fx_rate_returns_rate_with_publication_date(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_fx_service] = FakeFxService
    async with client_for(app) as client:
        res = await client.get(
            "/api/v1/marketdata/fx-rate",
            params={"from": "usd", "to": "PLN", "date": "2026-10-03"},
        )
    assert res.status_code == 200
    assert res.json() == {
        "base": "USD",
        "quote": "PLN",
        "rate": 3.8881,
        "rate_date": "2026-10-02",
        "requested_date": "2026-10-03",
        "source": "nbp",
    }


async def test_fx_rate_unsupported_currency_gives_422(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_fx_service] = FakeFxService
    async with client_for(app) as client:
        res = await client.get("/api/v1/marketdata/fx-rate", params={"from": "XYZ", "to": "PLN"})
    assert res.status_code == 422


async def test_fx_rate_missing_rate_gives_404(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_fx_service] = FakeFxService
    async with client_for(app) as client:
        res = await client.get("/api/v1/marketdata/fx-rate", params={"from": "USD", "to": "CHF"})
    assert res.status_code == 404


class FakeSourcesService:
    async def list_items(self, *, status, asset_id, cursor, limit):  # type: ignore[no-untyped-def]
        return SourcePage(
            items=[
                RawSourceItemOut(
                    item_id=UUID("bbbbbbbb-0000-0000-0000-000000000001"),
                    source="rss",
                    url="https://www.bankier.pl/x.html",
                    title="Orlen",
                    fetched_at=datetime(2026, 10, 6),
                )
            ],
            next_cursor=None,
        )

    async def engine_status(self) -> EngineStatusOut:
        return EngineStatusOut(last_cycle=None, failing_sources=[])

    async def funnel(self, *, hours):  # type: ignore[no-untyped-def]
        return FunnelOut(
            hours=hours,
            threshold=0.5,
            fetched=10,
            duplicates=1,
            scored=9,
            candidates=4,
            passed=2,
            rejected=2,
            unmatched=5,
            sent_to_llm=0,
            insights=0,
            cost_usd=0.0,
        )

    async def evaluation(self) -> EvaluationMetricsOut:
        return EvaluationMetricsOut(
            threshold=0.5,
            labeled_pairs=4,
            true_positive=1,
            false_positive=1,
            false_negative=1,
            true_negative=1,
            precision=0.5,
            recall=0.5,
            f1=0.5,
        )

    async def label(self, user_id: str, item_id: str, asset_id: str, *, relevant: bool) -> None:
        self.labelled = (user_id, item_id, asset_id, relevant)


async def test_sources_endpoint_lists_items(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/sources?limit=5")
    assert res.status_code == 200
    assert res.json()["items"][0]["title"] == "Orlen"


async def test_sources_rejects_bad_limit(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/sources?limit=0")
    assert res.status_code == 422


async def test_engine_status_endpoint(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/engine/status")
    assert res.status_code == 200
    body = res.json()
    assert body["last_cycle"] is None and body["failing_sources"] == []
    assert body["budget_exhausted"] is False and "cost_today_usd" in body


async def test_sources_rejects_unknown_status(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/sources?status=maybe")
    assert res.status_code == 422


async def test_sources_funnel_endpoint(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/sources/funnel?hours=48")
    assert res.status_code == 200
    assert res.json()["hours"] == 48 and res.json()["passed"] == 2


async def test_sources_evaluation_endpoint_returns_metrics(app: FastAPI) -> None:
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = FakeSourcesService
    async with client_for(app) as client:
        res = await client.get("/api/v1/sources/evaluation")
    assert res.status_code == 200
    assert res.json() == {
        "threshold": 0.5,
        "labeled_pairs": 4,
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }


async def test_sources_label_endpoint_saves_manual_assessment(app: FastAPI) -> None:
    fake = FakeSourcesService()
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_sources_service] = lambda: fake
    async with client_for(app) as client:
        res = await client.put(
            "/api/v1/sources/bbbbbbbb-0000-0000-0000-000000000001/labels/"
            "aaaaaaaa-0000-0000-0000-000000000001",
            json={"relevant": True},
        )
    assert res.status_code == 204
    assert fake.labelled == (
        USER.id,
        "bbbbbbbb-0000-0000-0000-000000000001",
        "aaaaaaaa-0000-0000-0000-000000000001",
        True,
    )
