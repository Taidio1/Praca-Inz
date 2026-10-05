from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import CurrentUser, get_current_user, get_settings_service
from src.schemas.settings import SettingsOut, SettingsUpdate
from src.services.settings import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingsOut:
    return await service.get(user.id)


@router.put("")
async def update_settings(
    payload: SettingsUpdate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingsOut:
    return await service.update(user.id, payload)
