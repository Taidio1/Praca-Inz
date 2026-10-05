from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_market_data_service,
    get_portfolio_history_service,
    get_portfolio_service,
)
from src.marketdata.service import MarketDataService
from src.schemas.portfolio import (
    PortfolioHistoryOut,
    PortfolioPositionOut,
    PositionCreate,
    TransactionDeleteResult,
    TransactionOut,
    TransactionUpdate,
)
from src.services.portfolio import PortfolioService
from src.services.portfolio_history import PortfolioHistoryService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
async def list_positions(
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> list[PortfolioPositionOut]:
    return await service.list_positions()


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_position(
    payload: PositionCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> PortfolioPositionOut:
    return await service.add_position(user.id, payload)


@router.post("/refresh")
async def refresh_prices(
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> dict[str, int]:
    """Odśwież notowania aktywów ze wszystkich portfeli (na żądanie z UI)."""
    return {"refreshed": await service.refresh_all()}


@router.get("/history")
async def portfolio_history(
    days: Annotated[int, Query(ge=2, le=365)],
    service: Annotated[PortfolioHistoryService, Depends(get_portfolio_history_service)],
) -> PortfolioHistoryOut:
    """Dzienna wycena portfela vs kapitał zainwestowany — pod wykres wartości."""
    return await service.history(days)


@router.get("/{position_id}/transactions")
async def list_transactions(
    position_id: UUID,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> list[TransactionOut]:
    """Historia zakupów pozycji (dokupienia) — do widoku szczegółów aktywa."""
    return await service.list_transactions(str(position_id))


@router.patch("/{position_id}/transactions/{tx_id}")
async def update_transaction(
    position_id: UUID,
    tx_id: UUID,
    payload: TransactionUpdate,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> PortfolioPositionOut:
    return await service.update_transaction(str(position_id), str(tx_id), payload)


@router.delete("/{position_id}/transactions/{tx_id}")
async def delete_transaction(
    position_id: UUID,
    tx_id: UUID,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> TransactionDeleteResult:
    return await service.delete_transaction(str(position_id), str(tx_id))


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_position(
    position_id: UUID,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> None:
    await service.remove_position(str(position_id))
