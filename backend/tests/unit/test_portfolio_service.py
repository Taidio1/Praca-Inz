from datetime import date

import pytest

from src.core.errors import NotFoundError, ValidationError
from src.marketdata.fx import FxRate, FxRateError
from src.schemas.portfolio import PositionCreate, TransactionUpdate
from src.services.portfolio import PortfolioService

ASSET_BTC = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "ticker": "BTC",
    "name": "Bitcoin",
    "asset_type": "crypto",
    "currency": "USD",
}
USER_ID = "11111111-1111-1111-1111-111111111111"


class FakeAssetsRepo:
    def __init__(self, assets: list[dict]) -> None:  # type: ignore[type-arg]
        self._assets = assets

    async def find_by_ticker(self, ticker: str, asset_type: str) -> dict | None:  # type: ignore[type-arg]
        for a in self._assets:
            if a["ticker"].lower() == ticker.lower() and a["asset_type"] == asset_type:
                return a
        return None

    async def get(self, asset_id: str) -> dict | None:  # type: ignore[type-arg]
        return next((a for a in self._assets if a["id"] == asset_id), None)


class FakeAssetsWriter:
    async def create(
        self, ticker: str, name: str, asset_type: str, aliases: list[str], currency: str
    ) -> dict:  # type: ignore[type-arg]
        return {
            "id": "aaaaaaaa-0000-0000-0000-000000000099",
            "ticker": ticker,
            "name": name,
            "asset_type": asset_type,
            "currency": currency,
        }


class FakeAssetSearch:
    async def lookup(self, ticker: str, asset_type: str) -> None:
        return None  # nieznane tickery — wymusza ValidationError


class FakePortfolioRepo:
    def __init__(self) -> None:
        self.positions: list[dict] = []  # type: ignore[type-arg]
        self.transactions: list[dict] = []  # type: ignore[type-arg]

    async def list_positions(self) -> list[dict]:  # type: ignore[type-arg]
        return self.positions

    async def get_position(self, position_id: str) -> dict | None:  # type: ignore[type-arg]
        return next((p for p in self.positions if p["id"] == position_id), None)

    async def find_position(self, user_id: str, asset_id: str) -> dict | None:  # type: ignore[type-arg]
        return next(
            (p for p in self.positions if p["user_id"] == user_id and p["asset_id"] == asset_id),
            None,
        )

    async def create_position(
        self, user_id: str, asset_id: str, quantity: float, avg_buy_price: float | None
    ) -> dict:  # type: ignore[type-arg]
        row = {
            "id": f"eeeeeeee-0000-0000-0000-{len(self.positions) + 1:012d}",
            "user_id": user_id,
            "asset_id": asset_id,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
        }
        self.positions.append(row)
        return row

    async def update_position_aggregate(
        self, position_id: str, quantity: float, avg_buy_price: float | None
    ) -> dict:  # type: ignore[type-arg]
        row = next(p for p in self.positions if p["id"] == position_id)
        row["quantity"] = quantity
        row["avg_buy_price"] = avg_buy_price
        return row

    async def add_transaction(
        self,
        position_id: str,
        user_id: str,
        quantity: float,
        price: float | None,
        purchased_at: str,
        currency: str,
        fx_rate: float,
        fx_rate_date: str,
    ) -> dict:  # type: ignore[type-arg]
        row = {
            "currency": currency,
            "fx_rate": fx_rate,
            "fx_rate_date": fx_rate_date,
            "id": f"ffffffff-0000-0000-0000-{len(self.transactions) + 1:012d}",
            "position_id": position_id,
            "user_id": user_id,
            "quantity": quantity,
            "price": price,
            "purchased_at": purchased_at,
            "created_at": "2026-07-04T10:00:00Z",
        }
        self.transactions.append(row)
        return row

    async def list_transactions(self, position_id: str) -> list[dict]:  # type: ignore[type-arg]
        return [t for t in self.transactions if t["position_id"] == position_id]

    async def list_all_transactions(self) -> list[dict]:  # type: ignore[type-arg]
        return list(self.transactions)

    async def get_transaction(self, position_id: str, tx_id: str) -> dict | None:  # type: ignore[type-arg]
        return next(
            (t for t in self.transactions if t["position_id"] == position_id and t["id"] == tx_id),
            None,
        )

    async def update_transaction(
        self,
        position_id: str,
        tx_id: str,
        quantity: float,
        price: float | None,
        purchased_at: str,
        currency: str,
        fx_rate: float,
        fx_rate_date: str,
    ) -> dict:  # type: ignore[type-arg]
        row = next(t for t in self.transactions if t["id"] == tx_id)
        row["quantity"] = quantity
        row["price"] = price
        row["purchased_at"] = purchased_at
        row["currency"] = currency
        row["fx_rate"] = fx_rate
        row["fx_rate_date"] = fx_rate_date
        return row

    async def delete_transaction(self, position_id: str, tx_id: str) -> bool:
        before = len(self.transactions)
        self.transactions = [t for t in self.transactions if t["id"] != tx_id]
        return len(self.transactions) < before

    async def delete(self, position_id: str) -> bool:
        before = len(self.positions)
        self.positions = [p for p in self.positions if p["id"] != position_id]
        return len(self.positions) < before


class FakeSnapshotsRepo:
    def __init__(self, by_asset: dict[str, dict] | None = None) -> None:  # type: ignore[type-arg]
        self._by_asset = by_asset or {}

    async def latest_for_assets(self, asset_ids: list[str]) -> dict[str, dict]:  # type: ignore[type-arg]
        return {k: v for k, v in self._by_asset.items() if k in asset_ids}


class FakeInsightsRepo:
    def __init__(self, latest: dict[str, dict] | None = None) -> None:  # type: ignore[type-arg]
        self._latest = latest or {}

    async def latest_per_asset(self, asset_ids: list[str]) -> dict[str, dict]:  # type: ignore[type-arg]
        return {k: v for k, v in self._latest.items() if k in asset_ids}


class FakeCurrencies:
    async def quote_currency(self, ticker: str, asset_type: str) -> str:
        return "USD"


class FakeFx:
    """Kursy per para: stała albo słownik dzień → kurs. Brak pary = FxRateError."""

    def __init__(
        self, rates: dict[tuple[str, str], float | dict[date, float]] | None = None
    ) -> None:
        self._rates = rates or {}
        self.calls: list[tuple[str, str, date]] = []

    def _get(self, base: str, quote: str, on: date) -> FxRate:
        if base == quote:
            return FxRate(rate=1.0, rate_date=on, source="identity")
        if (base, quote) not in self._rates:
            raise FxRateError(f"brak {base}/{quote}")
        table = self._rates[(base, quote)]
        rate = table if isinstance(table, float) else table[on]
        return FxRate(rate=rate, rate_date=on, source="nbp")

    async def rate_on(self, base: str, quote: str, on: date) -> FxRate:
        self.calls.append((base, quote, on))
        return self._get(base, quote, on)

    async def rates_on(self, base: str, quote: str, days: list[date]) -> dict[date, FxRate]:
        return {d: self._get(base, quote, d) for d in days}


class FakeSettings:
    def __init__(self, base_currency: str | None = "USD") -> None:
        self._base = base_currency

    async def get(self) -> dict | None:  # type: ignore[type-arg]
        return {"base_currency": self._base} if self._base else None


def make_service(
    portfolio: FakePortfolioRepo | None = None,
) -> tuple[PortfolioService, FakePortfolioRepo]:
    repo = portfolio or FakePortfolioRepo()
    svc = PortfolioService(
        assets=FakeAssetsRepo([ASSET_BTC]),
        assets_writer=FakeAssetsWriter(),
        asset_search=FakeAssetSearch(),
        portfolio=repo,
        snapshots=FakeSnapshotsRepo(
            {
                ASSET_BTC["id"]: {
                    "price": 67000.0,
                    "change_24h": -2.8,
                    "indicators": None,
                    "funding": None,
                    "captured_at": "2026-07-03T10:00:00Z",
                }
            }
        ),
        insights=FakeInsightsRepo(
            {ASSET_BTC["id"]: {"sentiment_score": -0.3, "sentiment_label": "negative"}}
        ),
        currencies=FakeCurrencies(),
        fx=FakeFx(),
        settings=FakeSettings("USD"),
    )
    return svc, repo


async def test_add_position_resolves_ticker_case_insensitive() -> None:
    svc, repo = make_service()
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="btc", asset_type="crypto", quantity=0.5)
    )
    assert out.asset.ticker == "BTC"
    assert out.quantity == 0.5
    assert out.snapshot is not None and out.snapshot.price == 67000.0
    assert out.latest_sentiment_label == "negative"
    assert repo.positions[0]["user_id"] == USER_ID


async def test_add_position_unknown_ticker_raises_validation_error() -> None:
    svc, _ = make_service()
    with pytest.raises(ValidationError):
        await svc.add_position(
            USER_ID, PositionCreate(ticker="XXX", asset_type="crypto", quantity=1)
        )


async def test_list_positions_enriches_with_snapshot_and_sentiment() -> None:
    svc, repo = make_service()
    repo.positions = [
        {"id": "eeeeeeee-0000-0000-0000-000000000001", "quantity": 0.5, "assets": ASSET_BTC}
    ]
    out = await svc.list_positions()
    assert len(out) == 1
    assert out[0].asset.name == "Bitcoin"
    assert out[0].snapshot is not None and out[0].snapshot.change_24h == -2.8
    assert out[0].latest_sentiment_score == -0.3


async def test_remove_missing_position_raises_not_found() -> None:
    svc, _ = make_service()
    with pytest.raises(NotFoundError):
        await svc.remove_position("eeeeeeee-0000-0000-0000-000000000099")


async def test_add_position_computes_value_and_pnl() -> None:
    svc, _ = make_service()
    out = await svc.add_position(
        USER_ID,
        PositionCreate(ticker="BTC", asset_type="crypto", quantity=0.5, price=50000.0),
    )
    assert out.avg_buy_price == 50000.0
    assert out.current_value == pytest.approx(33500.0)
    assert out.profit_loss_value == pytest.approx(8500.0)
    assert out.profit_loss_pct == pytest.approx(34.0)


async def test_position_without_buy_price_has_no_pnl() -> None:
    svc, _ = make_service()
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=0.5)
    )
    assert out.avg_buy_price is None
    assert out.current_value == pytest.approx(33500.0)
    assert out.profit_loss_value is None
    assert out.profit_loss_pct is None


async def test_position_without_snapshot_has_no_value() -> None:
    svc = PortfolioService(
        assets=FakeAssetsRepo([ASSET_BTC]),
        assets_writer=FakeAssetsWriter(),
        asset_search=FakeAssetSearch(),
        portfolio=FakePortfolioRepo(),
        snapshots=FakeSnapshotsRepo(),
        insights=FakeInsightsRepo(),
        currencies=FakeCurrencies(),
        fx=FakeFx(),
        settings=FakeSettings("USD"),
    )
    out = await svc.add_position(
        USER_ID,
        PositionCreate(ticker="BTC", asset_type="crypto", quantity=0.5, price=50000.0),
    )
    assert out.current_value is None
    assert out.profit_loss_pct is None


async def test_second_purchase_merges_into_weighted_average() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=70000.0)
    )
    assert len(repo.positions) == 1  # nadal jedna pozycja (agregat)
    assert len(repo.transactions) == 2  # dwie transakcje
    assert out.quantity == 2
    assert out.avg_buy_price == pytest.approx(60000.0)


async def test_transactions_without_price_are_skipped_in_average() -> None:
    svc, _ = make_service()
    await svc.add_position(USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1))
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=70000.0)
    )
    assert out.quantity == 2
    assert out.avg_buy_price == pytest.approx(70000.0)


async def test_position_with_only_priceless_transactions_has_null_average() -> None:
    svc, _ = make_service()
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1)
    )
    assert out.avg_buy_price is None


async def test_first_purchase_creates_position_and_transaction() -> None:
    svc, repo = make_service()
    out = await svc.add_position(
        USER_ID,
        PositionCreate(ticker="btc", asset_type="crypto", quantity=0.5, price=50000.0),
    )
    assert out.asset.ticker == "BTC"
    assert len(repo.positions) == 1
    assert len(repo.transactions) == 1
    assert repo.transactions[0]["position_id"] == repo.positions[0]["id"]
    assert repo.transactions[0]["purchased_at"]  # data ISO przekazana do repo


async def test_list_transactions_returns_rows() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    position_id = repo.positions[0]["id"]
    txs = await svc.list_transactions(position_id)
    assert len(txs) == 1
    assert txs[0].quantity == 1
    assert txs[0].price == 50000.0


async def test_list_transactions_unknown_position_raises_not_found() -> None:
    svc, _ = make_service()
    with pytest.raises(NotFoundError):
        await svc.list_transactions("eeeeeeee-0000-0000-0000-000000000099")


async def test_update_transaction_recomputes_aggregate() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    position_id = repo.positions[0]["id"]
    tx_id = repo.transactions[0]["id"]
    out = await svc.update_transaction(
        position_id,
        tx_id,
        TransactionUpdate(quantity=2, price=60000.0, purchased_at=date(2026, 7, 1)),
    )
    assert out.quantity == 2
    assert out.avg_buy_price == pytest.approx(60000.0)
    assert repo.transactions[0]["purchased_at"] == "2026-07-01"


async def test_update_transaction_unknown_position_raises_not_found() -> None:
    svc, _ = make_service()
    with pytest.raises(NotFoundError):
        await svc.update_transaction(
            "eeeeeeee-0000-0000-0000-000000000099",
            "ffffffff-0000-0000-0000-000000000001",
            TransactionUpdate(quantity=1, price=1.0, purchased_at=date(2026, 7, 1)),
        )


async def test_update_transaction_unknown_tx_raises_not_found() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    position_id = repo.positions[0]["id"]
    with pytest.raises(NotFoundError):
        await svc.update_transaction(
            position_id,
            "ffffffff-0000-0000-0000-000000000099",
            TransactionUpdate(quantity=1, price=1.0, purchased_at=date(2026, 7, 1)),
        )


async def test_delete_transaction_recomputes_aggregate_when_others_remain() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=70000.0)
    )
    position_id = repo.positions[0]["id"]
    first_tx_id = repo.transactions[0]["id"]
    result = await svc.delete_transaction(position_id, first_tx_id)
    assert result.position_removed is False
    assert len(repo.positions) == 1
    assert repo.positions[0]["quantity"] == 1
    assert repo.positions[0]["avg_buy_price"] == pytest.approx(70000.0)


async def test_delete_last_transaction_removes_position() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    position_id = repo.positions[0]["id"]
    tx_id = repo.transactions[0]["id"]
    result = await svc.delete_transaction(position_id, tx_id)
    assert result.position_removed is True
    assert repo.positions == []


async def test_delete_transaction_unknown_position_raises_not_found() -> None:
    svc, _ = make_service()
    with pytest.raises(NotFoundError):
        await svc.delete_transaction(
            "eeeeeeee-0000-0000-0000-000000000099", "ffffffff-0000-0000-0000-000000000001"
        )


async def test_delete_transaction_unknown_tx_raises_not_found() -> None:
    svc, repo = make_service()
    await svc.add_position(
        USER_ID, PositionCreate(ticker="BTC", asset_type="crypto", quantity=1, price=50000.0)
    )
    position_id = repo.positions[0]["id"]
    with pytest.raises(NotFoundError):
        await svc.delete_transaction(position_id, "ffffffff-0000-0000-0000-000000000099")


# ─── Wiele walut: waluta transakcji, waluta notowania, waluta bazowa ─────────

ASSET_AAPL = {
    "id": "aaaaaaaa-0000-0000-0000-000000000002",
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "asset_type": "stock",
    "currency": "USD",
}
TODAY = date.today()
D1 = date(2026, 3, 2)
D2 = date(2026, 6, 1)


def make_fx_service(
    fx: FakeFx, base: str = "PLN", price: float = 110.0
) -> tuple[PortfolioService, FakePortfolioRepo]:
    repo = FakePortfolioRepo()
    svc = PortfolioService(
        assets=FakeAssetsRepo([ASSET_AAPL]),
        assets_writer=FakeAssetsWriter(),
        asset_search=FakeAssetSearch(),
        portfolio=repo,
        snapshots=FakeSnapshotsRepo({ASSET_AAPL["id"]: {"price": price}}),
        insights=FakeInsightsRepo(),
        currencies=FakeCurrencies(),
        fx=fx,
        settings=FakeSettings(base),
    )
    return svc, repo


async def test_value_uses_current_rate_and_cost_uses_purchase_day_rate() -> None:
    fx = FakeFx({("USD", "PLN"): {D1: 4.0, TODAY: 3.9}})
    svc, _ = make_fx_service(fx)
    out = await svc.add_position(
        USER_ID,
        PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=100.0,
                       purchased_at=D1),
    )
    assert out.currency == "USD"
    assert out.base_currency == "PLN"
    assert out.avg_buy_price == pytest.approx(100.0)  # w walucie notowania
    assert out.current_value_quote == pytest.approx(110.0)
    assert out.current_value == pytest.approx(429.0)  # 110 USD × 3,9
    assert out.cost_basis == pytest.approx(400.0)  # 100 USD × 4,0 z dnia zakupu
    assert out.profit_loss_value == pytest.approx(29.0)
    assert out.profit_loss_pct == pytest.approx(7.25)
    # rozbicie: +10 USD ceny po kursie zakupu, −0,1 PLN/USD na 110 USD
    assert out.profit_loss_price == pytest.approx(40.0)
    assert out.profit_loss_fx == pytest.approx(-11.0)
    assert out.fx_rate == pytest.approx(3.9)


async def test_cost_stays_fixed_when_current_rate_changes() -> None:
    fx = FakeFx({("USD", "PLN"): {D1: 4.0, TODAY: 3.9}})
    svc, repo = make_fx_service(fx)
    await svc.add_position(
        USER_ID,
        PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=100.0,
                       purchased_at=D1),
    )
    repo.positions[0]["assets"] = ASSET_AAPL
    fx._rates[("USD", "PLN")] = {D1: 4.0, TODAY: 4.5}
    out = (await svc.list_positions())[0]
    assert out.cost_basis == pytest.approx(400.0)
    assert out.current_value == pytest.approx(495.0)


async def test_transaction_currency_defaults_to_quote_currency() -> None:
    fx = FakeFx({("USD", "PLN"): 4.0})
    svc, repo = make_fx_service(fx)
    await svc.add_position(
        USER_ID, PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=100.0)
    )
    tx = repo.transactions[0]
    assert tx["currency"] == "USD"
    assert tx["fx_rate"] == 1.0


async def test_position_with_transactions_in_two_currencies() -> None:
    fx = FakeFx(
        {
            ("EUR", "USD"): {D2: 1.1},
            ("USD", "PLN"): {D1: 4.0, D2: 3.8, TODAY: 3.9},
        }
    )
    svc, repo = make_fx_service(fx)
    await svc.add_position(
        USER_ID,
        PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=100.0,
                       currency="USD", purchased_at=D1),
    )
    out = await svc.add_position(
        USER_ID,
        PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=90.0,
                       currency="EUR", purchased_at=D2),
    )
    eur_tx = repo.transactions[1]
    assert eur_tx["currency"] == "EUR"
    assert eur_tx["price"] == 90.0  # zapisana kwota w walucie transakcji
    assert eur_tx["fx_rate"] == pytest.approx(1.1)  # kurs z dnia zakupu, nie bieżący
    assert ("EUR", "USD", D2) in fx.calls
    assert out.quantity == 2
    assert out.avg_buy_price == pytest.approx(99.5)  # (100 + 90 × 1,1) / 2 USD
    assert out.cost_basis == pytest.approx(100 * 4.0 + 99 * 3.8)
    assert out.current_value == pytest.approx(2 * 110 * 3.9)
    assert out.profit_loss_value == pytest.approx(858.0 - 776.2)
    assert out.profit_loss_price + out.profit_loss_fx == pytest.approx(  # type: ignore[operator]
        out.profit_loss_value
    )


async def test_missing_historical_rate_rejects_transaction() -> None:
    svc, repo = make_fx_service(FakeFx({("USD", "PLN"): 4.0}))
    with pytest.raises(ValidationError, match="Brak kursu CHF/USD"):
        await svc.add_position(
            USER_ID,
            PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=100.0,
                           currency="CHF"),
        )
    assert repo.transactions == []


async def test_unavailable_base_rate_keeps_quote_values() -> None:
    svc, _ = make_fx_service(FakeFx({}), base="PLN")
    out = await svc.add_position(
        USER_ID, PositionCreate(ticker="AAPL", asset_type="stock", quantity=2, price=100.0)
    )
    assert out.current_value_quote == pytest.approx(220.0)
    assert out.current_value is None  # nie sumujemy USD jako PLN
    assert out.cost_basis is None
    assert out.profit_loss_value is None


async def test_update_keeps_currency_and_takes_rate_from_new_date() -> None:
    fx = FakeFx({("EUR", "USD"): {D1: 1.05, D2: 1.1}, ("USD", "PLN"): 4.0})
    svc, repo = make_fx_service(fx)
    await svc.add_position(
        USER_ID,
        PositionCreate(ticker="AAPL", asset_type="stock", quantity=1, price=90.0,
                       currency="EUR", purchased_at=D1),
    )
    out = await svc.update_transaction(
        repo.positions[0]["id"],
        repo.transactions[0]["id"],
        TransactionUpdate(quantity=1, price=90.0, purchased_at=D2),
    )
    assert repo.transactions[0]["currency"] == "EUR"
    assert repo.transactions[0]["fx_rate"] == pytest.approx(1.1)
    assert out.avg_buy_price == pytest.approx(99.0)


async def test_legacy_usd_rows_keep_their_values_in_usd_base() -> None:
    """Dane sprzed migracji: currency='USD', fx_rate=1 — wynik identyczny jak dawny wzór."""
    svc, repo = make_fx_service(FakeFx(), base="USD", price=110.0)
    repo.positions = [
        {"id": "eeeeeeee-0000-0000-0000-000000000001", "user_id": USER_ID,
         "asset_id": ASSET_AAPL["id"], "quantity": 3, "avg_buy_price": 100.0,
         "assets": ASSET_AAPL}
    ]
    repo.transactions = [
        {"id": "ffffffff-0000-0000-0000-000000000001",
         "position_id": "eeeeeeee-0000-0000-0000-000000000001", "quantity": 3,
         "price": 100.0, "currency": "USD", "fx_rate": 1, "fx_rate_date": "2026-07-01",
         "purchased_at": "2026-07-01", "created_at": "2026-07-01T10:00:00Z"}
    ]
    out = (await svc.list_positions())[0]
    assert out.current_value == pytest.approx(3 * 110.0)
    assert out.profit_loss_value == pytest.approx((110.0 - 100.0) * 3)
    assert out.profit_loss_pct == pytest.approx(10.0)
    assert out.profit_loss_fx == pytest.approx(0.0)
    txs = await svc.list_transactions("eeeeeeee-0000-0000-0000-000000000001")
    assert txs[0].currency == "USD"
    assert txs[0].price_in_quote == pytest.approx(100.0)
